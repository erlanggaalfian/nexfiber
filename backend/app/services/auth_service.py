import time
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError, ValidationAppError
from app.core.rbac import SUPERADMIN
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.activity_log_repo import log_activity

MAX_FAILS = 5
WINDOW_S = 15 * 60
# Batas darurat agar dict lockout tidak tumbuh tanpa batas bila ada yang mem-probe
# banyak username/IP: entri kedaluwarsa dibersihkan di setiap login. Bila dict
# sudah penuh, percobaan gagal BARU TIDAK dicatat (dilupakan), bukan mengusir
# entri lockout aktif demi kunci baru — mengusir entri aktif sama saja
# membatalkan lockout akun yang sedang dikunci. Konsekuensinya: saat dict penuh,
# penyerang yang mem-probe username baru tidak ikut terkunci, tetapi tidak ada
# lockout aktif yang bisa dibatalkan dari luar. Pindah ke tabel DB adalah
# perbaikan yang benar bila batas ini sering tercapai (lihat pilihan di laporan).
_MAX_FAIL_KEYS = 5000
# Hash argon2 format valid yang dipakai sebagai "pengganti" saat user tidak ada
# atau nonaktif: verify_password tetap dijalankan dengan biaya yang sama,
# supaya waktu respons tidak membocorkan ada/tidaknya akun (timing oracle).
# Dibuat sekali saat import, bukan per login, dan bukan hash akun nyata mana pun.
_DUMMY_HASH = hash_password("nexfiber-dummy-password-yang-bukan-akun-nyata")

# ponytail: in-memory, valid for the single uvicorn process install.sh runs; move to a DB
# table if the API ever runs multiple workers. Keterbatasan yang tersisa: lockout
# hilang saat restart, dan di balik satu proxy semua user berbagi IP yang sama
# (kunci (ip, username) tetap membatasi per username, tapi penyerang bisa mengunci
# akun korban yang berbagi IP egress). Ini bukan pengganti rate-limit per akun di DB.
_fails: dict[tuple[str, str], list[float]] = {}

class TooManyAttempts(AppError):
    status_code = 429

def _prune_fails() -> None:
    """Buang HANYA entri kedaluwarsa dari SEMUA kunci.

    Sengaja tidak lagi mengusir kunci tertua saat dict penuh: entri yang masih
    dalam jendela adalah lockout aktif, dan mengusirnya membatalkan lockout.
    Pembatasan ukuran kini ditangani di titik pencatatan (login gagal): kunci
    baru tidak dicatat bila dict sudah penuh.
    """
    cutoff = time.monotonic() - WINDOW_S
    for key in list(_fails):
        kept = [t for t in _fails[key] if t > cutoff]
        if kept:
            _fails[key] = kept
        else:
            del _fails[key]

def _recent_fails(key: tuple[str, str]) -> list[float]:
    _prune_fails()
    return _fails.get(key, [])

async def _log_login(db: AsyncSession, *, username: str, user: User | None,
                     success: bool, ip: str | None) -> None:
    """Login (berhasil/gagal) dicatat tanpa password. Commit dilakukan pemanggil
    sebelum raise/return supaya log tidak ikut rollback saat sesi ditutup."""
    await log_activity(
        db, action="user.login", entity_type="user",
        entity_id=str(user.id) if user else username, success=success,
        user_id=user.id if user else None, ip_address=ip,
        after={"username": username} if not success else None,
    )

async def login(db: AsyncSession, username: str, password: str, ip: str) -> str:
    key = (ip, username)
    if len(_recent_fails(key)) >= MAX_FAILS:
        await _log_login(db, username=username, user=None, success=False, ip=ip)
        await db.commit()
        raise TooManyAttempts("Terlalu banyak percobaan gagal. Coba lagi dalam 15 menit")
    user = await db.scalar(
        select(User).where(User.username == username, User.deleted_at.is_(None))
    )
    if user is None or not user.is_active:
        # Timing oracle: jalankan verify_password dengan biaya argon2 yang sama
        # terhadap hash dummy, supaya "user tidak ada / nonaktif" tidak lebih
        # cepat dari "password salah". Pesan gagalnya pun sama persis.
        verify_password(password, _DUMMY_HASH)
        if key not in _fails and len(_fails) >= _MAX_FAIL_KEYS:
            pass  # Dict penuh: lupakan percobaan baru, jangan usir lockout aktif.
        else:
            _fails.setdefault(key, []).append(time.monotonic())
        await _log_login(db, username=username, user=user, success=False, ip=ip)
        await db.commit()
        raise ValidationAppError("Username atau password salah")
    if not verify_password(password, user.password_hash):
        if key not in _fails and len(_fails) >= _MAX_FAIL_KEYS:
            pass  # Dict penuh: lupakan percobaan baru, jangan usir lockout aktif.
        else:
            _fails.setdefault(key, []).append(time.monotonic())
        await _log_login(db, username=username, user=user, success=False, ip=ip)
        await db.commit()
        raise ValidationAppError("Username atau password salah")
    _fails.pop(key, None)
    user.last_login_at = datetime.now(UTC)
    await _log_login(db, username=username, user=user, success=True, ip=ip)
    await db.commit()
    return create_access_token(user.id, user.role, user.password_hash)

async def change_password(db: AsyncSession, user: User, old_password: str,
                          new_password: str) -> None:
    """Ganti password mandiri: password lama wajib benar, lalu flag
    must_change_password dibersihkan. Mengubah password_hash otomatis mencabut
    semua token lama lewat klaim "ph" di deps (lihat security.py)."""
    if not verify_password(old_password, user.password_hash):
        raise ValidationAppError("Password lama salah")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await log_activity(db, action="user.change_password", entity_type="user",
                       entity_id=str(user.id), success=True, user_id=user.id)
    await db.commit()

async def needs_setup(db: AsyncSession) -> bool:
    # Hanya user yang masih aktif (belum soft-delete) yang dihitung: kalau semua
    # user hanya tersisa sebagai baris soft-delete, /setup harus terbuka lagi.
    return not await db.scalar(
        select(func.count(User.id)).where(User.deleted_at.is_(None)))

async def setup(db: AsyncSession, username: str, full_name: str, password: str) -> str:
    """First Superadmin (PRD 3.4.1). Advisory lock so two racing requests can't both win."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('nexfiber_setup'))"))
    if not await needs_setup(db):
        raise NotFoundError("Not found")
    user = User(username=username, full_name=full_name, password_hash=hash_password(password),
                role=SUPERADMIN, last_login_at=datetime.now(UTC))
    db.add(user)
    await db.flush()
    await log_activity(db, action="user.setup", entity_type="user", entity_id=str(user.id),
                       success=True, user_id=user.id)
    await db.commit()
    return create_access_token(user.id, user.role, user.password_hash)
