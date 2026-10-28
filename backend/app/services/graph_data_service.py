"""Settings -> Graph Data: statistik, retensi otomatis, dan hapus manual rentang tanggal
untuk dua tabel time-series ONU (`onu_traffic_history`, `onu_signal_history`).

Kenapa di sini dan bukan di sampler: retensi dulu dikerjakan sampler trafik sendiri
(RETENTION_DAYS hardcode), jadi (a) tabel sinyal tidak pernah dibersihkan dan (b) tidak
ada pembersihan sama sekali kalau sampler mati. Sekarang satu job harian membersihkan
keduanya sesuai nilai di tabel `settings` (key `graph_retention`) — tanpa migrasi.

Penghapusan selalu BERBATCH (`DELETE ... WHERE id IN (SELECT ... LIMIT n)`): satu DELETE
puluhan juta baris menahan lock tabel dan membuat sampler ikut gagal.
"""

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.rbac import scope_olt_ids
from app.models.olt import Olt
from app.models.onu import Onu, OnuSignalHistory, OnuTrafficHistory
from app.models.setting import Setting
from app.models.user import User
from app.repositories import activity_log_repo
from app.schemas.graph_data import (
    GraphDeleteByOlt,
    GraphDeleteResult,
    GraphKind,
    GraphRetention,
    GraphStat,
)

SETTING_KEY = "graph_retention"
# Pilihan yang boleh dipakai; 0 = retensi otomatis nonaktif (simpan selamanya).
ALLOWED_DAYS = (0, 7, 14, 30, 60, 90, 180)
# Trafik 30 hari = nilai yang dulu hardcode di sampler. Sinyal 90 hari: barisnya jauh
# lebih sedikit (15 menit sekali, hanya saat berubah) jadi aman disimpan lebih lama.
DEFAULT_RETENTION = {"traffic": 30, "signal": 90}
# Tanggal di UI dibaca sebagai hari kalender WIB (zona operasional pemilik), bukan UTC.
WIB = timezone(timedelta(hours=7))
# Satu batch DELETE. Cukup besar supaya purge harian selesai cepat, cukup kecil supaya
# lock baris tidak menahan sampler yang jalan tiap 5 menit.
BATCH = 20_000

MODELS: dict[GraphKind, type] = {"traffic": OnuTrafficHistory, "signal": OnuSignalHistory}


async def get_retention(db: AsyncSession) -> GraphRetention:
    row = await db.get(Setting, SETTING_KEY)
    stored = row.value if row else {}
    return GraphRetention(**{
        kind: _valid_days(stored.get(kind, default), kind)
        for kind, default in DEFAULT_RETENTION.items()
    })


def _valid_days(value: object, kind: str) -> int:
    """Nilai di luar daftar ditolak. Baris `settings` yang rusak (diedit manual) jatuh
    kembali ke default alih-alih membuat halaman gagal dimuat."""
    if isinstance(value, int) and value in ALLOWED_DAYS:
        return value
    return DEFAULT_RETENTION[kind]


async def set_retention(db: AsyncSession, body: GraphRetention, user: User) -> GraphRetention:
    for kind in DEFAULT_RETENTION:
        days = getattr(body, kind)
        if days not in ALLOWED_DAYS:
            raise ValidationAppError(
                f"Retensi {kind} harus salah satu dari {list(ALLOWED_DAYS)} hari"
            )
    value = {kind: getattr(body, kind) for kind in DEFAULT_RETENTION}
    stmt = insert(Setting).values(
        key=SETTING_KEY, value=value, updated_by=user.id,
        description="Retensi data graph (hari, 0 = nonaktif)",
    )
    await db.execute(stmt.on_conflict_do_update(
        index_elements=[Setting.key],
        set_={"value": value, "updated_by": user.id, "updated_at": datetime.now(UTC)},
    ))
    await activity_log_repo.log_activity(
        db, action="graph_data.set_retention", entity_type="setting", entity_id=SETTING_KEY,
        success=True, user_id=user.id, after=value,
    )
    return GraphRetention(**value)


async def stats(db: AsyncSession, user: User) -> list[GraphStat]:
    """Jumlah baris + sampel tertua/terbaru dalam cakupan OLT user, plus ukuran tabel.

    Ukuran dari `pg_total_relation_size` = seluruh tabel (tidak bisa dibagi per OLT);
    jumlah baris tetap dibatasi cakupan supaya Admin tidak melihat volume Admin lain.
    """
    scope = scope_olt_ids(user)
    out: list[GraphStat] = []
    for kind, model in MODELS.items():
        stmt = select(func.count(model.id), func.min(model.sampled_at), func.max(model.sampled_at))
        if scope is not None:
            stmt = stmt.where(model.onu_id.in_(select(Onu.id).where(Onu.olt_id.in_(scope))))
        rows, oldest, newest = (await db.execute(stmt)).one()
        size = await db.scalar(
            text("SELECT pg_total_relation_size(CAST(:table_name AS regclass))")
            .bindparams(table_name=model.__tablename__)
        )
        out.append(GraphStat(kind=kind, rows=rows or 0, oldest_at=oldest, newest_at=newest,
                             size_bytes=int(size) if size is not None else None))
    return out


def _window(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Rentang tanggal WIB inklusif -> batas waktu [awal hari, awal hari berikutnya)."""
    if date_from > date_to:
        raise ValidationAppError("Tanggal awal tidak boleh setelah tanggal akhir")
    today = datetime.now(WIB).date()
    if date_to > today:
        raise ValidationAppError("Tanggal akhir tidak boleh di masa depan")
    start = datetime.combine(date_from, datetime.min.time(), tzinfo=WIB)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=WIB)
    return start, end


async def _onu_ids(db: AsyncSession, user: User, olt_id: int | None):
    """Subquery ONU yang boleh disentuh. `None` = semua ONU (Superadmin tanpa filter OLT).

    OLT di luar cakupan dijawab 404, pola sama dengan endpoint ONU/OLT lain (PRD 3.7).
    """
    scope = scope_olt_ids(user)
    if olt_id is not None:
        # Superadmin (scope None) boleh menyentuh histori OLT yang sudah dihapus:
        # dulu filter deleted_at membuat hapus manual untuk OLT terhapus selalu 404
        # dan, bila retensi diset 0, historinya yatim permanen. Non-superadmin
        # tetap dibatasi scope + OLT yang belum dihapus.
        if scope is None:
            allowed = select(Olt.id).where(Olt.id == olt_id)
        else:
            allowed = select(Olt.id).where(Olt.id == olt_id, Olt.deleted_at.is_(None),
                                           Olt.id.in_(scope))
        if await db.scalar(allowed) is None:
            raise NotFoundError(f"OLT {olt_id} tidak ditemukan")
        return select(Onu.id).where(Onu.olt_id == olt_id)
    if scope is None:
        return None
    return select(Onu.id).where(Onu.olt_id.in_(scope))


def _range_filter(model, start: datetime, end: datetime, onu_ids):
    conds = [model.sampled_at >= start, model.sampled_at < end]
    if onu_ids is not None:
        conds.append(model.onu_id.in_(onu_ids))
    return conds


async def _by_olt(db: AsyncSession, kinds: list[str], start: datetime, end: datetime,
                  onu_ids) -> list[GraphDeleteByOlt]:
    """Rincian hitungan per OLT untuk jenis-jenis yang diminta. Filter yang sama
    dengan hitungan total (rentang + cakupan user), jadi Admin hanya melihat
    OLT dalam scope-nya. OLT tanpa baris di rentang ini tidak muncul."""
    merged: dict[int, dict] = {}
    for kind in dict.fromkeys(kinds):
        model = MODELS[kind]
        stmt = (
            select(Onu.olt_id, Olt.name, func.count(model.id))
            .select_from(model)
            .join(Onu, Onu.id == model.onu_id)
            .outerjoin(Olt, Olt.id == Onu.olt_id)
            .where(*_range_filter(model, start, end, onu_ids))
            .group_by(Onu.olt_id, Olt.name)
            .order_by(Onu.olt_id)
        )
        for olt_id, olt_name, count in await db.execute(stmt):
            row = merged.setdefault(olt_id, {"olt_name": olt_name, "deleted": {}})
            row["deleted"][kind] = int(count or 0)
    out = []
    for olt_id in sorted(merged):
        row = merged[olt_id]
        out.append(GraphDeleteByOlt(
            olt_id=olt_id, olt_name=row["olt_name"],
            deleted=row["deleted"], total=sum(row["deleted"].values())))
    return out


async def preview_delete(db: AsyncSession, body, user: User) -> GraphDeleteResult:
    start, end = _window(body.date_from, body.date_to)
    onu_ids = await _onu_ids(db, user, body.olt_id)
    counts: dict[str, int] = {}
    for kind in dict.fromkeys(body.kinds):
        model = MODELS[kind]
        counts[kind] = await db.scalar(
            select(func.count(model.id)).where(*_range_filter(model, start, end, onu_ids))
        ) or 0
    return GraphDeleteResult(deleted=counts, total=sum(counts.values()),
                             by_olt=await _by_olt(db, body.kinds, start, end, onu_ids))


async def delete_range(db: AsyncSession, body, user: User) -> GraphDeleteResult:
    """Hard-delete. Tidak ada undo, jadi UI wajib memakai pratinjau + konfirmasi."""
    start, end = _window(body.date_from, body.date_to)
    onu_ids = await _onu_ids(db, user, body.olt_id)
    # Rincian per OLT diambil SEBELUM penghapusan (filter sama): setelah baris
    # dihapus tidak ada lagi yang bisa dihitung. Total per jenis di bawah tetap
    # dari hitungan batch yang benar-benar terhapus, bukan dari snapshot ini.
    by_olt = await _by_olt(db, body.kinds, start, end, onu_ids)
    counts: dict[str, int] = {}
    for kind in dict.fromkeys(body.kinds):
        model = MODELS[kind]
        counts[kind] = await _delete_batched(db, model, _range_filter(model, start, end, onu_ids))
    await activity_log_repo.log_activity(
        db, action="graph_data.delete", entity_type="graph_data", success=True,
        user_id=user.id, olt_id=body.olt_id,
        after={"kinds": list(dict.fromkeys(body.kinds)),
               "date_from": body.date_from.isoformat(), "date_to": body.date_to.isoformat(),
               "olt_id": body.olt_id, "deleted": counts, "total": sum(counts.values())},
    )
    return GraphDeleteResult(deleted=counts, total=sum(counts.values()), by_olt=by_olt)


async def _delete_batched(db: AsyncSession, model, conds: list) -> int:
    """Hapus per BATCH baris sampai habis, commit tiap batch supaya lock cepat dilepas."""
    total = 0
    while True:
        ids = select(model.id).where(*conds).limit(BATCH).scalar_subquery()
        result = await db.execute(delete(model).where(model.id.in_(ids)))
        removed = result.rowcount or 0
        total += removed
        await db.commit()
        if removed < BATCH:
            return total


async def purge_expired(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Job harian: hapus sampel lebih tua dari retensi. 0 hari = jenis itu dilewati."""
    now = now or datetime.now(UTC)
    retention = await get_retention(db)
    purged: dict[str, int] = {}
    for kind, model in MODELS.items():
        days = getattr(retention, kind)
        if days <= 0:
            purged[kind] = 0
            continue
        cutoff = now - timedelta(days=days)
        purged[kind] = await _delete_batched(db, model, [model.sampled_at < cutoff])
    return purged
