import base64
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from cryptography.fernet import Fernet

from app.core.config import settings

_hasher = PasswordHasher()


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
    payload: dict[str, object] = {"sub": str(user_id), "role": role, "exp": expires}
    if password_hash is not None:
        payload["ph"] = password_token_claim(password_hash)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def _fernet() -> Fernet:
    # app_secret_key may be any string; derive a valid 32-byte urlsafe-base64 Fernet key from it.
    digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> bytes:
    """Encrypt OLT CLI/SNMP credentials before storing (PRD 4.1: Fernet, APP_SECRET_KEY)."""
    return _fernet().encrypt(plain.encode())


def decrypt_secret(ciphertext: bytes) -> str:
    return _fernet().decrypt(ciphertext).decode()
