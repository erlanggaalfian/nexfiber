"""VLAN master data + push ke OLT (DECISIONS: fase ini backend-only, UI penuh nanti di
Detail OLT). API side: tulis baris + enqueue job dalam satu commit. Worker side: kirim
command ke OLT lewat driver, hasil mentah dicatat ke activity_logs.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CommandRejectedError, ConflictError, NotFoundError
from app.core.rbac import scope_olt_ids
from app.drivers.base import OltDriver
from app.drivers.types import DriverResult, debug_log
from app.models.job import Job
from app.models.olt import Olt
from app.models.onu import Onu
from app.models.onu_preset import OnuPreset
from app.models.speed_profile import SpeedProfile
from app.models.user import User
from app.models.vlan import Vlan
from app.repositories import olt_repo, onu_repo
from app.repositories.activity_log_repo import log_activity
from app.schemas.vlan import VlanCreate, VlanUpdate
from app.services import job_service
from app.services.onu_service import ensure_writes_allowed


async def list_vlans(db: AsyncSession, olt_id: int | None, user: User) -> list[Vlan]:
    # DRY: query + scope VLAN sudah ada di onu_repo.list_vlans (dipakai dropdown lama).
    return await onu_repo.list_vlans(db, olt_id, scope_olt_ids(user))


async def _get_scoped(db: AsyncSession, vlan_db_id: int, user: User) -> Vlan:
    vlan = await db.get(Vlan, vlan_db_id)
    if vlan is None:
        raise NotFoundError(f"VLAN {vlan_db_id} not found")
    if vlan.olt_id is not None:
        # Di luar cakupan OLT = 404, sama seperti endpoint lain (PRD 3.7).
        await _get_olt(db, vlan.olt_id, user)
    return vlan


async def _get_olt(db: AsyncSession, olt_id: int, user: User):
    olt = await olt_repo.get_active(db, olt_id, scope_olt_ids(user))
    if olt is None:
        raise NotFoundError(f"OLT {olt_id} not found")
    return olt


async def create_vlan(db: AsyncSession, body: VlanCreate, user: User) -> tuple[Vlan, int | None]:
    """Baris VLAN + job push dalam satu commit. olt_id NULL = VLAN global, tanpa job."""
    if body.olt_id is not None:
        await _get_olt(db, body.olt_id, user)
        ensure_writes_allowed()
    vlan = Vlan(**body.model_dump())
    # VLAN OLT dibuat TIDAK AKTIF sampai push_create sukses di worker (yang
    # mengeset is_active=True). Sebelumnya default model True membuat baris
    # tampil aktif padahal perintah belum tentu sampai ke perangkat. VLAN
    # global tanpa job tetap aktif langsung (tidak ada push yang ditunggu).
    if vlan.olt_id is not None:
        vlan.is_active = False
    db.add(vlan)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(f"VLAN {body.vlan_id} already exists on this OLT") from exc
    job_id = None
    if vlan.olt_id is not None:
        job = await job_service.enqueue(db, "create_vlan", olt_id=vlan.olt_id,
                                        payload={"vlan_db_id": vlan.id}, created_by=user.id)
        job_id = job.id
    await log_activity(db, action="vlan.create", entity_type="vlan", entity_id=str(vlan.id),
                       success=True, user_id=user.id, olt_id=vlan.olt_id)
    await db.commit()
    await db.refresh(vlan)
    return vlan, job_id


async def update_vlan(db: AsyncSession, vlan_db_id: int, body: VlanUpdate, user: User) -> Vlan:
    """Edit atribut VLAN di DB saja.

    JUJUR soal perangkat: untuk VLAN yang SUDAH ADA, tidak ada perintah push yang
    mengirim ulang description/gemport/tag_action/user_vlan — `push_ports` hanya
    mengirim perintah switchport per port uplink, dan `push_create` (yang memang
    mengirim description) hanya terjadi sekali saat pembuatan. Jadi perubahan
    field-field itu di sini hanya tersimpan di DB sampai VLAN dihapus dan dibuat
    ulang; UI wajib menyampaikan hal itu, bukan mengklaim perangkat ikut berubah.
    """
    vlan = await _get_scoped(db, vlan_db_id, user)
    values = body.model_dump(exclude_unset=True)
    # Keputusan (lihat laporan): perubahan `type` DITOLAK bila VLAN masih
    # dirujuk, bukan sekadar diperingatkan. Alasan: tipe menentukan perilaku
    # layanan di perangkat (internet/management/voip/iptv), tetapi update_vlan
    # adalah DB-only — tidak ada perintah yang mengirim ulang tipe ke perangkat
    # (lihat docstring fungsi ini). Mengizinkan perubahan tipe berarti DB
    # mengklaim tipe baru sementara perangkat tetap memakai tipe lama, dan
    # tidak ada jalan "push ulang tipe" untuk memperbaikinya kecuali hapus +
    # buat ulang. Menolak lebih jujur daripada peringatan yang bisa diabaikan.
    if "type" in values and values["type"] is not None and values["type"] != vlan.type:
        await _ensure_unused(db, vlan, reason="mengubah tipe")
    for field, value in values.items():
        setattr(vlan, field, value)
    await log_activity(db, action="vlan.update", entity_type="vlan", entity_id=str(vlan.id),
                       success=True, user_id=user.id, olt_id=vlan.olt_id,
                       after=body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    await db.refresh(vlan)
    return vlan


async def set_ports(db: AsyncSession, vlan_db_id: int, ports: dict[str, str],
                    user: User) -> int:
    """Konfigurasi tagged/untagged port uplink: enqueue job push, TANPA menulis DB dulu.

    Dulu `vlan.uplink_ports` ditulis saat enqueue, jadi job yang gagal pun membuat DB
    mengklaim konfigurasi yang tidak pernah sampai ke perangkat. Sekarang yang
    ditulis saat enqueue hanya niat di payload job; `push_ports` (worker) yang
    menulis `uplink_ports` setelah driver sukses.

    Port yang DIHILANGKAN dari map tidak bisa dihapus dari perangkat oleh driver
    saat ini (`zte_c320.set_vlan_ports` hanya mengiterasi port yang dikirim, tanpa
    perintah cabut). Karena itu port yang dihilangkan TIDAK dihapus dari DB di
    worker — ia dipertahankan sebagai "masih terpasang di perangkat" dan dilaporkan
    di hasil job sebagai `removed_not_applied`, sampai driver mendukung perintah
    hapus (lihat catatan di `push_ports`).
    """
    vlan = await _get_scoped(db, vlan_db_id, user)
    if vlan.olt_id is None:
        raise ConflictError("VLAN global tidak punya port uplink; pilih VLAN milik OLT")
    ensure_writes_allowed()
    old = vlan.uplink_ports or {}
    removed = sorted(p for p in old if p not in ports)
    job = await job_service.enqueue(db, "set_vlan_ports", olt_id=vlan.olt_id,
                                    payload={"vlan_db_id": vlan.id, "ports": ports,
                                             "removed_ports": removed},
                                    created_by=user.id)
    await log_activity(db, action="vlan.set_ports", entity_type="vlan", entity_id=str(vlan.id),
                       success=True, user_id=user.id, olt_id=vlan.olt_id, job_id=job.id,
                       after={"ports": ports, "removed_not_applied": removed})
    await db.commit()
    return job.id


async def delete_vlan(db: AsyncSession, vlan_db_id: int, user: User) -> int | None:
    """Global VLAN: hapus baris langsung. VLAN milik OLT: job hapus di device dulu,
    baris dihapus oleh worker setelah OLT menerima command."""
    vlan = await _get_scoped(db, vlan_db_id, user)
    await _ensure_unused(db, vlan)
    if vlan.olt_id is None:
        try:
            await db.delete(vlan)
            await log_activity(db, action="vlan.delete", entity_type="vlan", entity_id=str(vlan_db_id),
                               success=True, user_id=user.id)
            await db.commit()
        except IntegrityError as exc:
            # Guard di atas seharusnya sudah menolak, tapi race tetap mungkin:
            # FK yang menabrak di sini harus jadi 409 yang bisa dibaca operator,
            # bukan 500.
            await db.rollback()
            raise ConflictError(f"VLAN {vlan.vlan_id} masih dipakai, tidak bisa dihapus") from exc
        return None
    ensure_writes_allowed()
    # is_active TIDAK diubah saat enqueue: baris tetap tampil aktif sampai
    # worker sukses menghapusnya (lalu baris dihapus). Bila worker gagal, baris
    # tetap aktif apa adanya — tidak perlu "mengembalikan" nilai, karena nilai
    # aslinya tidak pernah diubah. Mengeset False saat enqueue adalah klaim
    # palsu yang sama seperti kasus buat VLAN di atas, hanya arah sebaliknya.
    job = await job_service.enqueue(db, "delete_vlan", olt_id=vlan.olt_id,
                                    payload={"vlan_db_id": vlan.id}, created_by=user.id)
    # Jejak permintaan hapus di sisi API (sebelumnya hanya ada jejak worker, jadi
    # permintaan hapus yang job-nya tidak pernah dieksekusi tidak punya jejak audit).
    await log_activity(db, action="vlan.delete_requested", entity_type="vlan",
                       entity_id=str(vlan.id), success=True, user_id=user.id,
                       olt_id=vlan.olt_id, job_id=job.id)
    await db.commit()
    return job.id


async def _preset_owner_id(db: AsyncSession, vlan: Vlan) -> int | None:
    """Owner yang dipakai membatasi cek preset, atau None = tanpa batas (global).

    Preset tidak terikat OLT (hanya owner_id), jadi satu-satunya pemetaan tenant
    yang bisa dibuktikan adalah pemilik OLT pemilik VLAN. Untuk VLAN global
    tidak ada pemilik OLT, sehingga cek preset sengaja TIDAK dibatasi: VLAN
    global berdampak ke semua OLT, jadi preset tenant mana pun yang merujuk
    nomornya menghalangi hapus (konservatif, didokumentasikan — bukan lintas
    tenant yang salah, melainkan penghalang global yang disengaja).
    Batasan yang tersisa: preset milik tenant lain yang berbagi OLT lewat
    olt_access tidak terhitung untuk VLAN OLT, karena preset tidak membawa
    olt_id sehingga tidak bisa dibuktikan preset itu berlaku untuk OLT ini.
    """
    if vlan.olt_id is None:
        return None
    olt = await db.get(Olt, vlan.olt_id)
    owner = getattr(olt, "owner_id", None)
    # Test double lama mengembalikan objek VLAN untuk model apa pun; owner_id
    # yang hilang di sana berarti "tidak diketahui", bukan "tanpa batas" —
    # fallback konservatif ke cek tanpa batas, sama seperti VLAN global.
    return owner


async def _ensure_unused(db: AsyncSession, vlan: Vlan, reason: str = "menghapus") -> None:
    """Tolak bila VLAN masih dirujuk — sebagai FK, angka, maupun JSONB.

    Perhatian kolom (bug lama): `Onu.vlan_id` adalah FK ke `vlans.id` (id baris),
    BUKAN nomor VLAN. Membandingkannya dengan `vlan.vlan_id` (nomor 1-4094) membuat
    guard hampir selalu lolos. Untuk VLAN global (`olt_id` NULL) tidak ada filter
    OLT sama sekali: rujukan dari OLT mana pun menghalangi hapus.
    `reason` hanya mengubah kata kerja di pesan error (hapus vs mengubah tipe).
    """
    if await db.scalar(select(Onu.id).where(
            Onu.vlan_id == vlan.id, Onu.deleted_at.is_(None)).limit(1)) is not None:
        raise ConflictError(
            f"VLAN {vlan.vlan_id} masih dipakai ONU sebagai VLAN primer, tidak bisa {reason}")
    if await db.scalar(select(SpeedProfile.id).where(
            SpeedProfile.vlan_db_id == vlan.id).limit(1)) is not None:
        raise ConflictError(f"VLAN {vlan.vlan_id} masih dipakai speed profile, tidak bisa {reason}")
    # Referensi non-FK (angka VLAN perangkat, bukan id baris): preset, service-port
    # yang terpasang, dan VLAN WAN. Untuk VLAN milik OLT, batasi ke ONU OLT itu;
    # untuk VLAN global, berlaku untuk semua OLT.
    onu_scope = [Onu.deleted_at.is_(None)]
    if vlan.olt_id is not None:
        onu_scope.append(Onu.olt_id == vlan.olt_id)
    preset_stmt = select(OnuPreset.id).where(OnuPreset.vlan == vlan.vlan_id)
    preset_owner = await _preset_owner_id(db, vlan)
    if preset_owner is not None:
        # Hanya preset milik pemilik VLAN yang menghalangi — preset tenant lain
        # tidak boleh memblokir hapus VLAN tenant ini.
        preset_stmt = preset_stmt.where(OnuPreset.owner_id == preset_owner)
    if await db.scalar(preset_stmt.limit(1)) is not None:
        raise ConflictError(
            f"VLAN {vlan.vlan_id} masih dipakai preset ONU (nomor VLAN di preset), "
            f"tidak bisa {reason}")
    if await db.scalar(select(Onu.id).where(
            Onu.service_vlan_ids.contains([vlan.vlan_id]), *onu_scope).limit(1)) is not None:
        raise ConflictError(
            f"VLAN {vlan.vlan_id} masih terpasang di perangkat ONU (service VLAN), "
            f"tidak bisa {reason}")
    if await db.scalar(select(Onu.id).where(
            Onu.wan_vlan == vlan.vlan_id, *onu_scope).limit(1)) is not None:
        raise ConflictError(
            f"VLAN {vlan.vlan_id} masih dipakai sebagai VLAN WAN ONU, tidak bisa {reason}")


# --- worker handlers ---------------------------------------------------------

async def _load(db: AsyncSession, job: Job) -> Vlan:
    vlan = await db.get(Vlan, job.payload["vlan_db_id"])
    if vlan is None:
        raise NotFoundError(f"VLAN {job.payload['vlan_db_id']} not found")
    return vlan


async def _record(db: AsyncSession, job: Job, vlan: Vlan, action: str,
                  result: DriverResult) -> None:
    # Pola sama dengan onu_service._record: log command mentah, commit sebelum raise.
    await log_activity(db, action=action, entity_type="vlan", entity_id=str(vlan.id),
                       success=result.success, user_id=job.created_by, job_id=job.id,
                       olt_id=vlan.olt_id, raw_command=result.raw_command,
                       raw_output=result.raw_output)
    if not result.success:
        # mark_failed tidak menulis job.result, dan worker me-rollback sebelum menandai
        # gagal — jadi jejak CLI harus ikut commit di sini supaya UI tetap bisa
        # menampilkannya saat aksi gagal.
        job.result = {"debug_log": debug_log(result)}
        await db.commit()
        raise CommandRejectedError(result.message or "OLT rejected command")


async def push_create(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    vlan = await _load(db, job)
    result = await driver.create_vlan(vlan.vlan_id, vlan.description or vlan.name)
    await _record(db, job, vlan, "vlan.push_create", result)
    vlan.is_active = True
    return {"debug_log": debug_log(result)}


async def push_delete(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    vlan = await _load(db, job)
    # Cek ulang pemakaian di worker: menutup race enqueue->eksekusi (VLAN yang
    # tadinya tidak terpakai bisa dipakai ONU/profile/preset baru selama job
    # mengantre). Bila guard ini menolak, perintah TIDAK dikirim dan job gagal
    # dengan ConflictError — baris tetap ada, perangkat tidak disentuh. Satu
    # race yang masih terbuka: rujukan yang dibuat persis bersamaan dengan
    # eksekusi worker (tidak ada lock baris VLAN di sini); menutup itu butuh
    # SELECT ... FOR UPDATE pada baris VLAN di worker, di luar cakupan ini.
    await _ensure_unused(db, vlan)
    result = await driver.delete_vlan(vlan.vlan_id)
    await _record(db, job, vlan, "vlan.push_delete", result)
    await db.delete(vlan)
    return {"debug_log": debug_log(result)}


async def push_ports(db: AsyncSession, job: Job, driver: OltDriver) -> dict:
    ensure_writes_allowed()
    vlan = await _load(db, job)
    ports: dict[str, str] = job.payload.get("ports", {})
    result = await driver.set_vlan_ports(vlan.vlan_id, ports)
    await _record(db, job, vlan, "vlan.push_ports", result)
    # BARU ditulis di sini (setelah driver sukses), bukan saat enqueue. Port yang
    # dihilangkan TIDAK dihapus dari DB: driver tidak punya perintah cabut, jadi
    # menghapusnya dari DB saja akan berbohong soal keadaan perangkat. Port itu
    # dipertahankan dan dilaporkan, sampai driver mendukung perintah hapus
    # (perlu diubah agen pemilik driver — payload `removed_ports` sudah dikirim
    # job ini sebagai kontrak untuk implementasi itu).
    old = vlan.uplink_ports or {}
    removed = sorted(p for p in old if p not in ports)
    vlan.uplink_ports = {**old, **ports}
    out: dict = {"debug_log": debug_log(result), "ports": len(ports)}
    if removed:
        out["removed_not_applied"] = removed
    return out
