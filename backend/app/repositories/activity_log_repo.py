"""activity_logs: insert helper + read query for Logs page (PRD 3.4.15).
raw_command/raw_output are mandatory for every OLT write (PRD 4.3/4.6) — this is the one
place that enforces that at the code level.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Scope, scoped
from app.models.activity_log import ActivityLog
from app.models.olt import Olt
from app.models.onu import Onu
from app.models.user import User


async def log_activity(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    success: bool,
    entity_id: str | None = None,
    user_id: int | None = None,
    job_id: int | None = None,
    olt_id: int | None = None,
    onu_id: int | None = None,
    raw_command: str | None = None,
    raw_output: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        ActivityLog(
            created_at=datetime.now(UTC),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            success=success,
            user_id=user_id,
            job_id=job_id,
            olt_id=olt_id,
            onu_id=onu_id,
            raw_command=raw_command,
            raw_output=raw_output,
            before=before,
            after=after,
            ip_address=ip_address,
        )
    )
    await db.flush()


#: Aksi yang dipetakan ke kategori spesifik di `category_of` (schemas/activity_log).
#: "delete" sengaja luas: semua aksi *.delete (olt/user/vlan/speed_profile/zone/
#: splitter/onu_type/preset) masuk kategori Hapus, bukan tersembunyi di kategori
#: prefix-nya seperti sebelumnya. "login" hanya user.login.
_SPECIAL_ACTIONS = {
    "authorize": ["onu.authorize"],
    "reboot": ["onu.reboot"],
    "delete": ["onu.delete", "onu.restore_factory"],
}


def _category_condition(category: str):
    """Filter SQL yang persis mencerminkan `category_of`, tanpa daftar aksi statis.

    Daftar aksi statis selalu ketinggalan (mis. `onu.action.*` tidak pernah masuk
    daftar, jadi filter kategori menyembunyikan log itu). Dengan kondisi prefix/inilah,
    aksi baru otomatis masuk kategori yang benar: olt.* -> olt, user.* -> user,
    sisanya yang tidak dipetakan spesifik -> service.
    """
    if category in _SPECIAL_ACTIONS and category != "delete":
        return ActivityLog.action.in_(_SPECIAL_ACTIONS[category])
    if category == "delete":
        return or_(ActivityLog.action.like("%.delete"),
                   ActivityLog.action == "onu.restore_factory")
    if category == "login":
        return ActivityLog.action == "user.login"
    if category == "olt":
        return and_(ActivityLog.action.like("olt.%"),
                    not_(ActivityLog.action.like("%.delete")))
    if category == "user":
        return and_(ActivityLog.action.like("user.%"),
                    ActivityLog.action != "user.login",
                    not_(ActivityLog.action.like("%.delete")))
    if category == "service":
        special = [a for actions in _SPECIAL_ACTIONS.values() for a in actions]
        return and_(not_(ActivityLog.action.in_(special)),
                    ActivityLog.action != "user.login",
                    not_(ActivityLog.action.like("%.delete")),
                    not_(ActivityLog.action.like("olt.%")),
                    not_(ActivityLog.action.like("user.%")))
    raise ValueError(f"Kategori log tidak dikenal: {category}")


def _apply_filters(stmt, *, q, olt_id, user_id, actions, category, since, until):
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(ActivityLog.action.ilike(like), ActivityLog.entity_id.ilike(like),
                               User.username.ilike(like), Onu.serial_number.ilike(like)))
    if olt_id:
        stmt = stmt.where(ActivityLog.olt_id == olt_id)
    if user_id:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if actions:
        stmt = stmt.where(ActivityLog.action.in_(actions))
    if category:
        stmt = stmt.where(_category_condition(category))
    if since:
        stmt = stmt.where(ActivityLog.created_at >= since)
    if until:
        stmt = stmt.where(ActivityLog.created_at <= until)
    return stmt


def _base():
    return (
        select(ActivityLog, User.username, Olt.name, Onu.serial_number)
        .outerjoin(User, User.id == ActivityLog.user_id)
        .outerjoin(Olt, Olt.id == ActivityLog.olt_id)
        .outerjoin(Onu, Onu.id == ActivityLog.onu_id)
    )


def _scoped_logs(stmt, scope: Scope, viewer_id: int | None):
    """Scope log dengan pengecualian non-OLT yang aman.

    Sebelumnya `scoped()` memakai `olt_id IN scope`, sehingga semua baris
    `olt_id IS NULL` (user.*, master data, graph_data) hilang untuk
    non-Superadmin — Admin bahkan tidak melihat log aksinya sendiri di sana.
    Aturan baru, bila viewer_id diketahui: baris OLT tetap harus dalam scope,
    TAPI baris tanpa OLT hanya terlihat bila aktornya adalah viewer sendiri.
    Itu tidak membocorkan log tenant lain (nama zone/user Admin lain tetap
    tersembunyi), karena kepemilikan master data tidak tersimpan di baris log
    sehingga satu-satunya klaim kepemilikan yang bisa dibuktikan adalah
    user_id aktor itu sendiri. Bila viewer_id tidak diberikan (pemanggil lama),
    perilaku lama dipertahankan supaya tidak ada perubahan diam-diam.
    CATATAN PENGKABELAN (diperbarui): activity_log_service.py SUDAH meneruskan
    viewer_id=user.id sejak verifikasi gabungan putaran sebelumnya, jadi aturan
    baru ini AKTIF di API — komentar lama yang menyebutnya belum aktif sudah
    tidak berlaku.
    """
    if scope is None:
        return stmt
    in_scope = ActivityLog.olt_id.in_(scope)
    if viewer_id is not None:
        return stmt.where(or_(in_scope, and_(ActivityLog.olt_id.is_(None),
                                             ActivityLog.user_id == viewer_id)))
    return stmt.where(in_scope)


async def search(db: AsyncSession, scope: Scope, *, q: str | None, olt_id: int | None,
                 user_id: int | None, actions: list[str] | None = None,
                 category: str | None = None, since: datetime | None = None,
                 until: datetime | None = None, page: int = 1, size: int = 50,
                 viewer_id: int | None = None) -> tuple[list, int]:
    filters = dict(q=q, olt_id=olt_id, user_id=user_id, actions=actions, category=category,
                   since=since, until=until)
    total = await db.scalar(_scoped_logs(_apply_filters(
        select(func.count(ActivityLog.id)).outerjoin(User, User.id == ActivityLog.user_id)
        .outerjoin(Onu, Onu.id == ActivityLog.onu_id), **filters,
    ), scope, viewer_id))
    stmt = (_scoped_logs(_apply_filters(_base(), **filters), scope, viewer_id)
            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .offset((page - 1) * size).limit(size))
    return list(await db.execute(stmt)), total or 0
