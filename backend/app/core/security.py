import base64
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings

_hasher = PasswordHasher()

# Token SSE sekali pakai: cukup lama untuk EventSource sempat tersambung,
# cukup pendek sehingga token yang bocor ke log/proxy cepat tidak berguna.
SSE_TOKEN_SECONDS = 120


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except (VerifyMismatchError, InvalidHash):
        # Hash korup = bukan password yang benar, bukan 500.
        return False


def password_token_claim(password_hash: str) -> str:
    """Klaim revokasi tanpa kolom DB baru: digest dari password_hash saat ini.

    Token yang diterbitkan setelah perubahan ini membawa klaim "ph"; deps menolak
    token yang klaimnya tidak lagi cocok dengan hash saat ini, sehingga reset/ganti
    password otomatis mencabut semua token lama. Token lama tanpa klaim "ph" (yang
    diterbitkan sebelum perubahan ini) tetap diterima sampai kedaluwarsa — itu
    batasan kompatibilitas yang disengaja, bukan revokasi retroaktif penuh.
    Digest ini bukan password dan bukan hash yang bisa dipakai untuk login: ia
    hanya bisa diverifikasi oleh server yang sudah memegang password_hash.
    """
    return hashlib.sha256(password_hash.encode()).hexdigest()


def create_access_token(user_id: int, role: str, password_hash: str | None = None) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_minutes)
    # "jti" = id unik per token, dipakai logout (daftar revokasi) — token lama
    # tanpa jti tetap diterima sampai kedaluwarsa, tapi tidak bisa dicabut
    # satu-per-satu (hanya lewat ganti password, klaim "ph").
    payload: dict[str, object] = {"sub": str(user_id), "role": role, "exp": expires,
                                  "jti": uuid.uuid4().hex}
    if password_hash is not None:
        payload["ph"] = password_token_claim(password_hash)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def create_sse_token(user_id: int, role: str, password_hash: str | None = None) -> str:
    """Token SSE sekali pakai, terpisah dari token akses.

    EventSource tidak bisa mengirim header Authorization, jadi token harus lewat
    query string (masuk access log/proxy) — token akses 8 jam tidak boleh
    dipakai di sana. Token ini hanya berlaku SSE_TOKEN_SECONDS detik, membawa
    klaim "typ": "sse", dan ditandai terpakai saat koneksi pertama dibuka
    (lihat jobs.py + auth_service.record_token_jti), sehingga pemakaian kedua
    dengan token yang sama ditolak. Bukan token akses: decode_access_token
    biasa tidak memeriksa "typ", jadi stream WAJIB memakai decode_sse_token.
    """
    expires = datetime.now(UTC) + timedelta(seconds=SSE_TOKEN_SECONDS)
    payload: dict[str, object] = {"sub": str(user_id), "role": role, "exp": expires,
                                  "typ": "sse", "jti": uuid.uuid4().hex}
    if password_hash is not None:
        payload["ph"] = password_token_claim(password_hash)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_sse_token(token: str) -> dict:
    """Decode token SSE; menolak token akses biasa (tanpa klaim typ=sse)."""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != "sse":
        raise ValueError("Bukan token SSE")
    return payload


def _fernet_legacy() -> Fernet:
    # Derivasi LAMA (sebelum perbaikan ini): SHA-256 polos tanpa salt/KDF dari
    # app_secret_key. Dipertahankan HANYA untuk membaca kredensial yang sudah
    # tersimpan dengan skema itu — jangan dipakai untuk enkripsi baru.
    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet_v2(salt: bytes) -> Fernet:
    # Derivasi BARU: PBKDF2-HMAC-SHA256, salt acak per nilai, 600.000 iterasi
    # (angka rekomendasi OWASP untuk PBKDF2-HMAC-SHA256). Salt disimpan bersama
    # ciphertext, jadi tidak ada secret tambahan yang harus dikelola.
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(settings.app_secret_key.encode())))


def encrypt_secret(plain: str) -> bytes:
    """Encrypt OLT CLI/SNMP credentials before storing (PRD 4.1: Fernet, APP_SECRET_KEY).

    Format baru (v2): b"v2:" + base64url(salt 16 byte) + b":" + token Fernet.
    Migrasi dua tahap yang aman (tanpa downtime, tanpa kehilangan kredensial):
    tahap 1 (kode ini) — tulis baru memakai v2, baca mendukung v2 DAN skema
    lama; tahap 2 — baris lama berubah menjadi v2 secara oportunis tiap kali
    kredensial OLT itu disimpan ulang lewat form (olt_service memakai
    encrypt_secret yang sama), jadi tidak ada migrasi data massal yang bisa
    merusak kredensial bila secret salah. Baris lama yang belum pernah
    disimpan ulang tetap terbaca lewat jalur legacy sampai kapan pun.
    """
    salt = os.urandom(16)
    token = _fernet_v2(salt).encrypt(plain.encode())
    return b"v2:" + base64.urlsafe_b64encode(salt) + b":" + token


def decrypt_secret(ciphertext: bytes) -> str:
    """Dekripsi kredensial: v2 (salt + PBKDF2) bila berawalan b"v2:", kalau
    tidak, skema lama SHA-256 (kompatibilitas baris lama). Token yang rusak
    atau kunci yang salah tetap gagal (InvalidToken) — tidak pernah ditebak
    menjadi plaintext."""
    if isinstance(ciphertext, str):
        ciphertext = ciphertext.encode()
    if ciphertext.startswith(b"v2:"):
        try:
            _, salt_b64, token = ciphertext.split(b":", 2)
            salt = base64.urlsafe_b64decode(salt_b64)
        except ValueError as exc:
            raise InvalidToken("Format v2 tidak valid") from exc
        return _fernet_v2(salt).decrypt(token).decode()
    return _fernet_legacy().decrypt(ciphertext).decode()
