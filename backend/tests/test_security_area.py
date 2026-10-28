"""Area keamanan: enkripsi v2, token SSE sekali pakai, logout/revokasi, backup terenkripsi.

Tes murni (tanpa DB) selalu jalan. Tes DB (daftar revoked/consumed di tabel
settings) memakai pola skip yang sama dengan test_graph_data: skip bila
Postgres tidak terjangkau di sandbox ini, jalan di mesin yang ada DB-nya.
Tidak ada tes live (NEXFIBER_LIVE_TEST tidak pernah diset di sini).
"""

import base64
import time

import pytest
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.core.security import (
    SSE_TOKEN_SECONDS,
    _fernet_legacy,
    create_access_token,
    create_sse_token,
    decode_access_token,
    decode_sse_token,
    decrypt_secret,
    encrypt_secret,
)
from app.services import auth_service
from app.services.sync_service import decrypt_backup_config


async def _db_up() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def test_encrypt_v2_roundtrip_dan_salt_acak():
    a = encrypt_secret("s3cret-cli")
    b = encrypt_secret("s3cret-cli")
    assert a.startswith(b"v2:") and b.startswith(b"v2:")
    assert a != b  # salt acak per nilai: ciphertext yang sama tidak terulang
    assert decrypt_secret(a) == "s3cret-cli"
    assert decrypt_secret(b) == "s3cret-cli"


def test_decrypt_masih_membaca_skema_lama():
    # Baris lama di DB: token Fernet dari derivasi SHA-256 polos, tanpa awalan.
    legacy = _fernet_legacy().encrypt(b"komunitas-lama")
    assert decrypt_secret(legacy) == "komunitas-lama"


def test_decrypt_token_rusak_gagal_bukan_plaintext():
    from cryptography.fernet import InvalidToken
    token = encrypt_secret("rahasia")
    rusak = token[:-4] + b"AAAA"
    with pytest.raises(InvalidToken):
        decrypt_secret(rusak)


def test_token_akses_punya_jti_unik():
    a = create_access_token(1, "admin", "hash-x")
    b = create_access_token(1, "admin", "hash-x")
    ja, jb = decode_access_token(a)["jti"], decode_access_token(b)["jti"]
    assert ja and jb and ja != jb


def test_token_sse_berumur_pendek_dan_bukan_token_akses():
    token = create_sse_token(1, "admin", "hash-x")
    payload = decode_sse_token(token)
    assert payload["typ"] == "sse"
    assert payload["exp"] - int(time.time()) <= SSE_TOKEN_SECONDS
    # Token akses biasa ditolak sebagai token SSE (tanpa klaim typ=sse).
    with pytest.raises(ValueError):
        decode_sse_token(create_access_token(1, "admin", "hash-x"))


def test_backup_terenkripsi_dan_legacy_passthrough():
    stored = "enc:" + encrypt_secret("running-config isi kredensial").decode()
    assert "kredensial" not in stored
    assert decrypt_backup_config(stored) == "running-config isi kredensial"
    # Baris backup lama (plaintext) tetap terbaca, bukan gagal dekripsi.
    assert decrypt_backup_config("hostname OLT-LAMA") == "hostname OLT-LAMA"


@pytest.mark.asyncio
async def test_daftar_revoked_dan_consumed_di_settings():
    if not await _db_up():
        pytest.skip("Postgres unreachable")
    jti = "test-jti-area-keamanan"
    exp = time.time() + 3600
    async with SessionLocal() as db:
        assert not await auth_service.is_token_jti_recorded(
            db, auth_service.REVOKED_TOKENS_KEY, jti)
        await auth_service.record_token_jti(db, auth_service.REVOKED_TOKENS_KEY, jti, exp)
        await db.commit()
        assert await auth_service.is_token_jti_recorded(
            db, auth_service.REVOKED_TOKENS_KEY, jti)
        # Kunci lain tidak ikut tercemar; entri kedaluwarsa dianggap tidak ada.
        assert not await auth_service.is_token_jti_recorded(
            db, auth_service.CONSUMED_SSE_TOKENS_KEY, jti)
        await auth_service.record_token_jti(
            db, auth_service.CONSUMED_SSE_TOKENS_KEY, "kadaluarsa", time.time() - 10)
        await db.commit()
        assert not await auth_service.is_token_jti_recorded(
            db, auth_service.CONSUMED_SSE_TOKENS_KEY, "kadaluarsa")
    # Bersihkan baris tes sendiri (nilai dict ditulis ulang tanpa jti tes).
    async with SessionLocal() as db:
        from app.models.setting import Setting
        for key, drop in ((auth_service.REVOKED_TOKENS_KEY, jti),
                          (auth_service.CONSUMED_SSE_TOKENS_KEY, "kadaluarsa")):
            row = await db.get(Setting, key)
            if row is not None and drop in (row.value or {}):
                value = dict(row.value)
                del value[drop]
                row.value = value
        await db.commit()
