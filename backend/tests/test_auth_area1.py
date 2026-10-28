"""Tes unit area Auth/RBAC (tanpa Postgres): token malformed -> 401,
revokasi token lewat klaim "ph", redaksi job.result untuk non-manager,
dan kategori log delete/login. Tidak menyentuh DB sama sekali."""
import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.core.deps import _user_from_token
from app.core.security import create_access_token, hash_password
from app.models.job import Job
from app.models.user import User
from app.repositories.activity_log_repo import _category_condition
from app.schemas.activity_log import category_of
from app.services.job_service import redact_job


class FakeDb:
    def __init__(self, user):
        self._user = user

    async def get(self, model, user_id):
        return self._user


def _user(role="user", password_hash="hash-lama"):
    return User(id=7, username="u", full_name="U", password_hash=password_hash,
                role=role, admin_id=None, is_active=True)


def test_malformed_token_is_401_not_500():
    # Token valid signature tapi tanpa sub: sebelumnya int(payload["sub"])
    # melempar KeyError -> 500. Sekarang harus 401.
    import jwt
    from app.core.config import settings
    token = jwt.encode({"role": "user"}, settings.jwt_secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_user_from_token(FakeDb(_user()), token))
    assert exc.value.status_code == 401


def test_token_revoked_after_password_change():
    old_hash = hash_password("password-lama-123")
    user = _user(password_hash=old_hash)
    token = create_access_token(user.id, user.role, old_hash)
    # Sebelum ganti password: token diterima.
    assert asyncio.run(_user_from_token(FakeDb(user), token)).id == 7
    # Setelah ganti password (hash berubah): token lama ditolak 401.
    user.password_hash = hash_password("password-baru-456")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_user_from_token(FakeDb(user), token))
    assert exc.value.status_code == 401


def test_token_without_ph_claim_still_accepted():
    # Kompatibilitas: token yang diterbitkan sebelum perubahan ini (tanpa klaim
    # "ph") dan token test tetap diterima sampai kedaluwarsa.
    user = _user()
    token = create_access_token(user.id, user.role)
    assert asyncio.run(_user_from_token(FakeDb(user), token)).id == 7


def _job(job_type, result):
    job = Job(job_type=job_type, status="success", payload={}, result=result,
              olt_id=1, onu_id=2, created_by=1)
    job.id = 99
    job.priority = 100
    job.attempts = 1
    job.max_attempts = 3
    job.created_at = datetime.now(UTC)
    return job


def test_redact_running_config_for_user_keeps_other_fields():
    job = _job("refresh_onu_detail", {"running_config": "secret", "phase_state": "online"})
    out = redact_job(job, _user(role="user"))
    assert out.result["phase_state"] == "online"
    assert "running_config" not in out.result


def test_redact_diagnostic_running_output_for_user():
    job = _job("read_onu_running_config", {"view": "running", "output": "secret"})
    out = redact_job(job, _user(role="user"))
    assert out.result["output"] is None
    assert out.result["view"] == "running"


def test_manager_still_sees_running_config():
    job = _job("refresh_onu_detail", {"running_config": "secret"})
    out = redact_job(job, _user(role="admin"))
    assert out.result["running_config"] == "secret"


def test_category_delete_and_login():
    assert category_of("olt.delete") == "delete"
    assert category_of("user.delete") == "delete"
    assert category_of("vlan.delete") == "delete"
    assert category_of("user.login") == "login"
    assert category_of("olt.create") == "olt"
    # Kondisi SQL-nya tidak boleh melempar ValueError untuk "login" lagi.
    assert _category_condition("login") is not None
    assert _category_condition("delete") is not None
