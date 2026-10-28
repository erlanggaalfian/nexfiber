"""Aksi & konfigurasi ONU (modal SmartOLT) — satu service untuk semua `kind`.

Kontrak API ada di `routers/onu_actions.py`. Aturan tetap di sini:

1. Tiap aksi yang MENULIS ke perangkat wajib `confirm=true` (tanpa itu 400) — dicek di
   `ensure_confirmed`, bukan di UI.
2. Rahasia (password WiFi/PPPoE) TIDAK boleh masuk log, audit, atau field `commands` pada
   respons. `redact_commands` adalah satu-satunya jalan keluar perintah ke luar service.
3. Kind yang sintaksnya belum terbukti di perangkat dijawab 501 (`UNSUPPORTED_KINDS`),
   tidak pernah dikarang.
4. Aksi yang sudah punya endpoint sendiri (reboot/delete/state/speed/restore-factory)
   TIDAK diduplikasi: kind-nya hanya pembungkus `enqueue_onu_job` yang sudah ada.
"""

from __future__ import annotations

import re

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.exceptions import ValidationAppError as ValidationError
from app.core.rbac import MANAGERS, owner_of, scope_olt_ids
from app.drivers import zte_onu_actions as za
from app.drivers.onu_report import parse_current_ip, parse_wan_ip
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
from app.models.unconfigured_onu import UnconfiguredOnu
from app.models.onu_type import OnuType
from app.models.speed_profile import SpeedProfile
from app.models.splitter import Splitter
from app.models.user import User
from app.models.vlan import Vlan
from app.models.zone import Zone
from app.repositories import onu_repo
from app.repositories.activity_log_repo import log_activity
from app.services import onu_service

#: kind -> job_type yang SUDAH ADA. Jangan tulis alur baru untuk ini.
JOB_KINDS: dict[str, str] = {
    "reboot": "reboot_onu",
    "restore-factory": "restore_factory",
    "delete": "delete_onu",
    "disable": "set_state",
    "enable": "set_state",
    "speed-profile": "apply_speed_profile",
    # Recreate config = job resync_onu (authorize ulang dari DB), BUKAN perintah
    # `clear` langsung: clear menghapus tcont/gemport/service-port tanpa mengirim
    # ulang apa pun, jadi modal ini tidak boleh lagi memakai jalur perintah langsung.
    "resync-config": "resync_onu",
}
#: kind yang butuh role manager (sama dengan endpoint tulis yang sudah ada).
MANAGER_KINDS = {"delete", "restore-factory", "replace-sn", "move"}

_SECRET_RE = re.compile(
    r"\b(key|password|pass|secret)\s+(?!default\b)\S+", re.I
)


def port_config_entry(kind: str, body: dict) -> tuple[str, str, dict] | None:
    """Entri port_configs untuk satu aksi port yang sukses: (bagian, kunci port,
    nilai yang boleh disimpan). Dipakai run_action DAN diuji langsung — sandi
    WiFi sengaja tidak pernah masuk nilai (modal selalu meminta sandi baru
    saat auth != open, jadi prefill tidak membutuhkannya). Kind lain -> None."""
    if kind == "eth-port":
        return ("eth", str(body.get("port")), {
            "enabled": body.get("enabled", True),
            "mode": body.get("mode"),
            "vlan_id": body.get("vlan_id"),
            "allowed_vlans": body.get("allowed_vlans") or [],
            "dhcp": body.get("dhcp", "none"),
        })
    if kind == "wifi-port":
        return ("wifi", str(body.get("port")), {
            "enabled": body.get("enabled", True),
            "mode": body.get("mode"),
            "vlan_id": body.get("vlan_id"),
            "allowed_vlans": body.get("allowed_vlans") or [],
            "ssid": body.get("ssid"),
            "auth_mode": body.get("auth_mode", "wpa2"),
        })
    return None


def redact_commands(commands: list[str]) -> list[str]:
    """Buang nilai setelah kata kunci rahasia. Satu-satunya pintu keluar perintah."""
    return [_SECRET_RE.sub(r"\1 <REDACTED>", c) for c in commands]


def ensure_confirmed(kind: str, body: dict) -> None:
    writes, _ = za.SUPPORTED_KINDS.get(kind, (False, None))
    if writes and body.get("confirm") is not True:
        raise ValidationError(f"Aksi {kind} menulis ke perangkat: butuh confirm=true")


async def _onu_and_pon(db: AsyncSession, onu_id: int, user: User) -> tuple[Onu, PonPort]:
    serial = await onu_repo.get_serial_by_id(db, onu_id, scope_olt_ids(user))
    if serial is None:
        raise NotFoundError(f"ONU {onu_id} not found")
    onu = await onu_repo.get_active(db, onu_id)
    if onu is None:
        raise NotFoundError(f"ONU {onu_id} not found")
    return onu, await db.get(PonPort, onu.pon_port_id)


def _vlan_numbers(vlans: list[Vlan], ids: list[int]) -> list[int]:
    by_id = {v.id: v.vlan_id for v in vlans}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValidationError(f"VLAN tidak dikenal: {missing}")
    return [by_id[i] for i in ids]


async def list_actions(db: AsyncSession, onu_id: int, user: User) -> dict:
    """Daftar kind + dukungan nyata. `supported:false` = POST akan balas 501."""
    await _onu_and_pon(db, onu_id, user)
    actions = []
    for kind, (writes, note) in za.SUPPORTED_KINDS.items():
        actions.append({"kind": kind, "supported": True, "writes_device": writes, "note": note})
    for kind, reason in za.UNSUPPORTED_KINDS.items():
        actions.append({"kind": kind, "supported": False, "writes_device": True, "note": reason})
    actions.append({"kind": "location", "supported": True, "writes_device": False,
                    "note": "PUT /api/onus/{id}/location — hanya DB Nexfiber."})
    actions.sort(key=lambda a: a["kind"])
    return {"actions": actions}


async def config_options(db: AsyncSession, onu_id: int, user: User) -> dict:
    """Isi dropdown semua modal dalam satu panggilan (frontend tidak perlu 7 request)."""
    onu, _ = await _onu_and_pon(db, onu_id, user)
    scope = scope_olt_ids(user)
    vlans = await onu_repo.list_vlans(db, onu.olt_id, scope)
    profiles = await onu_repo.list_speed_profiles(db, onu.olt_id, scope)
    # Zone/Splitter sebelumnya dikembalikan TANPA filter pemilik (enumerasi lintas
    # tenant): siapa pun dalam scope satu OLT bisa mendaftar nama zone/splitter
    # tenant lain. Sekarang: zone dibatasi owner_id pemanggil (Superadmin = semua),
    # splitter dibatasi lewat zone pemilik — konsisten dengan list_splitters yang
    # memakai owned() (splitter tanpa zone tetap tidak terlihat non-Superadmin,
    # karena kepemilikannya hanya bisa diwariskan lewat zone).
    owner = owner_of(user)
    zone_stmt = select(Zone).order_by(Zone.name)
    if owner is not None:
        zone_stmt = zone_stmt.where(Zone.owner_id == owner)
    zones = (await db.execute(zone_stmt)).scalars().all()
    splitter_stmt = select(Splitter).order_by(Splitter.name)
    if owner is not None:
        splitter_stmt = splitter_stmt.where(
            Splitter.zone_id.in_([z.id for z in zones]))
    splitters = (await db.execute(splitter_stmt)).scalars().all()
    # Tipe nonaktif tidak boleh ditawarkan/diterapkan lewat modal (konsisten dengan
    # daftar VLAN dan speed profile yang sudah memfilter is_active).
    onu_types = (await db.execute(
        select(OnuType).where(OnuType.is_active.is_(True)).order_by(OnuType.name)
    )).scalars().all()
    return {
        "vlans": [{"number": v.vlan_id, "name": v.name,
                   "is_management": v.type == "management"} for v in vlans],
        "zones": [{"id": z.id, "name": z.name} for z in zones],
        "splitters": [{"id": s.id, "name": s.name, "zone_id": s.zone_id,
                       "ports": s.capacity} for s in splitters],
        # Sector belum jadi tabel sendiri di Nexfiber (dipakai zone sebagai sektor).
        "sectors": [{"id": z.id, "name": z.name} for z in zones],
        "speed_profiles": [{"id": p.id, "name": p.name, "direction": p.direction}
                            for p in profiles],
        "onu_types": [{"id": t.id, "name": t.name} for t in onu_types],
        "wan_modes": ["webpage", "dhcp", "static", "pppoe"],
    }


async def update_location(db: AsyncSession, onu_id: int, body: dict, user: User):
    """Update location details — HANYA kolom DB, tanpa perintah ke perangkat.

    Pakai `onu_service.update_info` yang sudah ada (DRY). PUT penuh: nilai null
    ikut diteruskan supaya mengosongkan field benar-benar menghapus nilai lama,
    bukan diam-diam dipertahankan.
    """
    from app.schemas.onu import OnuInfoBody

    onu, _ = await _onu_and_pon(db, onu_id, user)
    fields = {k: v for k, v in body.items() if k in OnuInfoBody.model_fields}
    info = OnuInfoBody.model_validate(fields)
    return await onu_service.update_info(db, onu.serial_number, info, user)


async def refresh_ip(db: AsyncSession, onu_id: int, user: User) -> dict:
    """Ambil IP ONU terbaca dari perangkat (laporan ip-host + pasangan running-config),
    simpan ke DB.

    Read-only ke perangkat. Aturan keras: `onus.ip_address` HANYA IP dari VLAN yang
    ditandai management di master VLAN, `onus.wan_ip_address` HANYA IP dari VLAN
    non-management — keduanya tidak pernah saling mewakili. Yang tidak bisa dipasangkan
    tidak pernah disimpan (nilai lama dibiarkan apa adanya, tidak pernah
    dikosongkan/ditebak).
    """
    from app.drivers.factory import build_driver

    onu, pon = await _onu_and_pon(db, onu_id, user)
    olt = await db.get(Olt, onu.olt_id)
    if olt.vendor != "zte":
        raise NotImplementedError(f"Vendor {olt.vendor} belum didukung untuk refresh-ip")
    if onu.onu_index is None:
        raise ValidationError("ONU belum punya onu_index di OLT")
    iface = f"gpon-onu_1/{pon.slot}/{pon.port}:{onu.onu_index}"
    raw = await build_driver(olt).fetch_onu_ip_host(pon.slot, pon.port, onu.onu_index)
    report, mng_cfg = raw
    management_vlans = {v.vlan_id for v in (await db.execute(select(Vlan).where(
        Vlan.type == "management", or_(Vlan.olt_id == onu.olt_id, Vlan.olt_id.is_(None))
    ))).scalars()}
    ip = parse_current_ip(report, mng_cfg, management_vlans)
    if ip:
        onu.ip_address = ip
    wan_ip = parse_wan_ip(report, mng_cfg, management_vlans)
    if wan_ip:
        onu.wan_ip_address = wan_ip
    # Dibaca sebelum commit: atribut expire setelah commit.
    saved, saved_wan = onu.ip_address, onu.wan_ip_address
    await log_activity(
        db, action="onu.read_ip_host", entity_type="onu", entity_id=str(onu.id),
        success=True, user_id=user.id, olt_id=onu.olt_id, onu_id=onu.id,
        raw_command=f"show gpon remote-onu ip-host {iface} ; show onu running config {iface}",
    )
    await db.commit()
    return {"ip_address": saved, "wan_ip_address": saved_wan}


def _int_field(body: dict, key: str, *, lo: int, hi: int) -> int:
    """Field int wajib dengan rentang — menggantikan akses body[...] mentah yang
    sebelumnya jadi KeyError/TypeError (500) bila field hilang atau bertipe salah."""
    v = body.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise ValidationError(f"{key} harus angka {lo}..{hi}, dapat {v!r}")
    return v


def _bool_field(body: dict, key: str, default: bool) -> bool:
    v = body.get(key, default)
    if not isinstance(v, bool):
        raise ValidationError(f"{key} harus boolean, dapat {v!r}")
    return v


def _str_field(body: dict, key: str) -> str:
    v = body.get(key)
    if not isinstance(v, str) or v == "":
        raise ValidationError(f"{key} wajib diisi")
    return v


def _build_commands(kind: str, onu: Onu, pon: PonPort, body: dict,
                    vlan_numbers: list[int] | None = None,
                    previous_vlan_count: int | None = None) -> list[str]:
    """kind -> perintah vendor. Hanya ZTE (MVP); vendor lain ditolak di caller.

    Semua field wajib divalidasi di sini (bukan di builder yang memakai perbandingan
    mentah) supaya body hilang/salah tipe menjadi 422, bukan 500.
    """
    slot, port, idx = pon.slot, pon.port, onu.onu_index
    if idx is None:
        raise ValidationError("ONU belum punya onu_index di OLT")
    if kind == "attached-vlans":
        return za.build_attached_vlans(slot, port, idx, vlan_numbers or [],
                                       previous_count=previous_vlan_count)
    if kind == "eth-port":
        return za.build_eth_port(
            slot, port, idx, eth_port=_int_field(body, "port", lo=1, hi=24),
            enabled=_bool_field(body, "enabled", True),
            mode=_str_field(body, "mode"), vlan_id=body.get("vlan_id"),
            allowed_vlans=body.get("allowed_vlans"), dhcp=body.get("dhcp", "none"))
    if kind == "wifi-port":
        return za.build_wifi_port(
            slot, port, idx, wifi_port=_int_field(body, "port", lo=1, hi=8),
            enabled=_bool_field(body, "enabled", True),
            mode=_str_field(body, "mode"), vlan_id=body.get("vlan_id"),
            allowed_vlans=body.get("allowed_vlans"), ssid=body.get("ssid"),
            auth_mode=body.get("auth_mode", "wpa2"), password=body.get("password"),
            dhcp=body.get("dhcp", "none"))
    if kind == "wifi-clear":
        return za.build_wifi_clear(slot, port, idx,
                                   wifi_port=_int_field(body, "port", lo=1, hi=8))
    if kind == "onu-type":
        return za.build_onu_type(slot, port, idx, onu_type=body["onu_type_name"])
    if kind == "mgmt-ip":
        return za.build_mgmt_ip(slot, port, idx, mode=_str_field(body, "mode"),
                                ip=body.get("ip"), netmask=body.get("netmask"))
    if kind in ("voip-enable", "voip-disable"):
        # Nomor/sandi SIP TIDAK punya sintaks OLT-CLI yang terbukti (hanya
        # `voip protocol sip|none`). Modal lama mengirim keduanya dan backend
        # membuangnya diam-diam — sekarang ditolak eksplisit (422) supaya tidak
        # ada yang mengira akun SIP sudah diprovisi. Modal baru sudah tidak
        # lagi mengirim field ini; penolakan ini menjaga pemanggil API langsung.
        for key in ("phone_number", "password"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                raise ValidationError(
                    f"VoIP {key} tidak bisa diprovisi lewat CLI OLT: tidak ada "
                    "sintaks akun SIP yang terbukti; hanya protocol sip/none "
                    "yang didukung")
        return za.build_voip(slot, port, idx, enabled=kind == "voip-enable")
    if kind == "replace-sn":
        return za.build_replace_sn(slot, port, idx, onu_type=onu.onu_type or "ALL-ONT",
                                   new_sn=_str_field(body, "new_sn"))
    if kind == "move":
        return za.build_replace_sn(body["board"], body["port"], idx,
                                   onu_type=onu.onu_type or "ALL-ONT",
                                   new_sn=onu.serial_number)
    raise ValidationError(f"kind {kind} tidak punya pembangun perintah")


async def run_action(db: AsyncSession, onu_id: int, kind: str, body: dict,
                     user: User) -> dict:
    """Satu pintu POST /api/onus/{id}/actions/{kind}."""
    if kind in za.UNSUPPORTED_KINDS:
        raise NotImplementedError(za.UNSUPPORTED_KINDS[kind])
    if kind not in za.SUPPORTED_KINDS:
        raise NotFoundError(f"kind {kind} tidak dikenal")
    if kind in MANAGER_KINDS and user.role not in MANAGERS:
        raise ForbiddenError(f"Aksi {kind} butuh role manager")
    ensure_confirmed(kind, body)
    onu, pon = await _onu_and_pon(db, onu_id, user)

    # external-id: kolom DB saja, tidak menyentuh perangkat.
    if kind == "external-id":
        from app.schemas.onu import OnuInfoBody
        from pydantic import ValidationError as PydanticValidationError
        try:
            info = OnuInfoBody.model_validate({"external_id": body.get("external_id")})
        except PydanticValidationError as exc:
            # Tanpa ini, external_id >50 karakter jadi 500 (bukan AppError).
            raise ValidationError(str(exc)) from exc
        await onu_service.update_info(db, onu.serial_number, info, user)
        return {"ok": True, "executed": False, "detail": "external_id disimpan di DB",
                "commands": []}

    # Kind yang sudah punya job: pakai ulang, jangan duplikasi alur.
    if kind in JOB_KINDS:
        payload: dict | None = None
        if kind in ("disable", "enable"):
            payload = {"enabled": kind == "enable"}
        elif kind == "speed-profile":
            payload = {"download_speed_profile_id": body.get("download_profile"),
                       "upload_speed_profile_id": body.get("upload_profile")}
        job_id = await onu_service.enqueue_onu_job(
            db, onu.serial_number, JOB_KINDS[kind], user, payload)
        return {"ok": True, "executed": False, "job_id": job_id,
                "detail": f"job {JOB_KINDS[kind]} #{job_id} dibuat", "commands": []}

    olt = await db.get(Olt, onu.olt_id)
    if olt.vendor != "zte":
        raise NotImplementedError(f"Vendor {olt.vendor} belum didukung untuk aksi {kind}")

    # Gate config_state, konsisten dengan jalur job: ONU yang sedang "configuring"
    # (authorize berjalan) tidak boleh ditimpa aksi langsung — perintahnya bisa hilang
    # saat authorize selesai. ONU "failed" tetap diizinkan: aksi langsung justru jalur
    # perbaikan untuk config yang gagal, dan memblokirnya akan mengunci ONU itu.
    if onu.config_state == "configuring":
        raise ValidationError(
            "ONU sedang dikonfigurasi (authorize berjalan); tunggu sampai selesai")

    vlan_numbers = None
    previous_vlan_count = None
    if kind == "attached-vlans":
        vlans = await onu_repo.list_vlans(db, onu.olt_id, scope_olt_ids(user))
        wanted = body.get("vlans") or []
        # VLAN yang sudah terpasang di perangkat boleh dipertahankan walau belum
        # terdaftar di master — kalau tidak, ONU dengan VLAN device-only tidak bisa
        # diubah sama sekali, padahal UI menjanjikan VLAN tersembunyi dipertahankan.
        # Ini TIDAK membuka penambahan VLAN baru sembarangan: yang diizinkan di luar
        # master hanyalah yang memang sudah ada di `service_vlan_ids` ONU ini.
        known = {v.vlan_id for v in vlans} | {int(n) for n in (onu.service_vlan_ids or [])}
        unknown = [n for n in wanted if n not in known]
        if unknown:
            raise ValidationError(f"VLAN belum terdaftar di OLT ini: {unknown}")
        # Simpan hasil validate (dedup + urut), bukan wanted mentah, supaya DB persis
        # sama dengan perintah yang dikirim.
        try:
            vlan_numbers = za.validate_vlans([int(n) for n in wanted])
        except (ValueError, TypeError) as exc:
            raise ValidationError(str(exc)) from exc
        # VLAN management tidak boleh DITAMBAH lewat API ini, meski UI menyembunyikannya.
        # Pengecualian: yang memang sudah terpasang (hidden preservation) boleh
        # dipertahankan — menolaknya akan membuat modal attached-vlans tidak bisa
        # disimpan sama sekali untuk ONU yang punya VLAN management.
        management = {v.vlan_id for v in vlans if v.type == "management"}
        existing = {int(n) for n in (onu.service_vlan_ids or [])}
        new_management = [n for n in vlan_numbers if n in management and n not in existing]
        if new_management:
            raise ValidationError(
                f"VLAN management tidak boleh ditambahkan ke ONU: {new_management}")
        previous_vlan_count = len(existing)
    if kind in ("eth-port", "wifi-port"):
        # VLAN port harus dikenal di master OLT ini dan bukan VLAN management.
        # Sebelumnya hanya rentang 1..4094 yang dicek, jadi VLAN management / VLAN
        # OLT lain / VLAN belum terdaftar bisa dipasang lewat API langsung.
        vlans = await onu_repo.list_vlans(db, onu.olt_id, scope_olt_ids(user))
        by_number = {v.vlan_id: v for v in vlans}
        for label, value in (("vlan_id", body.get("vlan_id")),):
            if value is not None:
                row = by_number.get(value)
                if row is None:
                    raise ValidationError(f"VLAN {value} tidak terdaftar di OLT ini")
                if row.type == "management":
                    raise ValidationError(f"VLAN {value} adalah VLAN management")
        allowed = body.get("allowed_vlans")
        if allowed is not None:
            if not isinstance(allowed, list):
                raise ValidationError("allowed_vlans harus daftar angka")
            for n in allowed:
                row = by_number.get(n)
                if row is None:
                    raise ValidationError(f"VLAN {n} tidak terdaftar di OLT ini")
                if row.type == "management":
                    raise ValidationError(f"VLAN {n} adalah VLAN management")
            # Trunk/hybrid dengan allowed kosong tidak punya perintah hapus yang
            # terbukti, jadi kirimannya hanya akan diam-diam mempertahankan daftar
            # lama — tolak di sini daripada menyesatkan.
            if body.get("mode") in ("trunk", "hybrid") and len(allowed) == 0:
                raise ValidationError(
                    "Mode trunk/hybrid butuh minimal satu allowed VLAN")
    if kind == "onu-type":
        type_id = body.get("onu_type_id")
        onu_type = await db.get(OnuType, type_id) if type_id else None
        if onu_type is None:
            raise ValidationError("onu_type_id tidak dikenal")
        # config_options sudah memfilter tipe nonaktif, tapi API langsung bisa
        # melewatinya — tolak di sini seperti speed profile (`is False`, bukan
        # `not`, supaya objek tanpa atribut is_active tidak salah ditolak).
        if onu_type.is_active is False:
            raise ValidationError("Tipe ONU nonaktif tidak bisa diterapkan")
        body = {**body, "onu_type_name": onu_type.name}
    # Pre-check bentrok SEBELUM perintah dikirim ke perangkat: kalau dicek sesudah,
    # perangkat sudah berubah tapi commit DB gagal (unique index) dan keduanya menyimpang.
    if kind == "replace-sn":
        new_sn = str(body.get("new_sn", "")).strip().upper()
        if new_sn == onu.serial_number:
            raise ValidationError("Serial number baru sama dengan yang sekarang")
        if new_sn and await onu_repo.exists_serial(db, onu.olt_id, new_sn):
            raise ValidationError(f"ONU {new_sn} sudah terdaftar di OLT ini")
    target_pon_id = None
    if kind == "move":
        board, port = body.get("board"), body.get("port")
        if not isinstance(board, int) or isinstance(board, bool) \
                or not isinstance(port, int) or isinstance(port, bool):
            raise ValidationError("move butuh board dan port (angka PON tujuan)")
        target = (await db.execute(select(PonPort).where(
            PonPort.olt_id == onu.olt_id, PonPort.slot == board, PonPort.port == port
        ))).scalars().first()
        if target is None:
            raise ValidationError("PON tujuan belum tersinkron di database OLT ini")
        target_pon_id = target.id
        if onu.onu_index is not None:
            clash = (await db.execute(select(Onu).where(
                Onu.pon_port_id == target.id, Onu.onu_index == onu.onu_index,
                Onu.deleted_at.is_(None), Onu.id != onu.id
            ))).scalars().first()
            if clash is not None:
                raise ValidationError(
                    f"ONU ID {onu.onu_index} sudah terpakai di PON tujuan {board}/{port}")

    try:
        commands = _build_commands(kind, onu, pon, body, vlan_numbers,
                                   previous_vlan_count=previous_vlan_count)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValidationError(str(exc)) from exc

    onu_service.ensure_writes_allowed()
    safe = redact_commands(commands)

    from app.drivers.factory import build_driver

    driver = build_driver(olt)
    result = await driver.run_onu_commands(commands)
    # Perintah "Update attached VLANs" SUKSES = daftar service-port ONU sekarang persis
    # `vlan_numbers` (build_attached_vlans menulis satu service-port per VLAN). Simpan
    # langsung supaya modal dibuka ulang sudah tercentang benar tanpa menunggu siklus
    # sync 15 menit. Hanya saat sukses — kalau OLT menolak, DB tidak boleh mengklaim.
    if kind == "attached-vlans" and result.success and vlan_numbers is not None:
        onu.service_vlan_ids = list(vlan_numbers)
        # Konsistensi dua jalur, arah kebalikan dari set_onu_vlan: bila VLAN
        # primer dihapus dari daftar attached, primer tidak boleh lagi menunjuk
        # VLAN yang sudah tidak terpasang. Aturannya: pakai VLAN pertama yang
        # tersisa di daftar (urutan hasil validate_vlans) bila ada baris masternya
        # (diutamakan OLT ini, lalu global); bila tidak ada baris master yang
        # cocok, kosongkan — jangan mengarang baris master. Bila primer masih ada
        # di daftar, tidak diubah. Daftar kosong tidak mungkin lolos validasi
        # (validate_vlans menolaknya), jadi cabang kosong hanya pertahanan.
        old_primary = await db.get(Vlan, onu.vlan_id) if onu.vlan_id else None
        if old_primary is not None and old_primary.vlan_id not in vlan_numbers:
            new_primary_id = None
            if vlan_numbers:
                candidate = (await db.execute(select(Vlan).where(
                    Vlan.vlan_id == vlan_numbers[0], Vlan.olt_id == onu.olt_id
                ))).scalars().first()
                if candidate is None:
                    candidate = (await db.execute(select(Vlan).where(
                        Vlan.vlan_id == vlan_numbers[0], Vlan.olt_id.is_(None)
                    ))).scalars().first()
                new_primary_id = candidate.id if candidate else None
            onu.vlan_id = new_primary_id
    # Aksi langsung yang mengubah identitas di perangkat wajib ditulis balik ke DB
    # saat sukses — kalau tidak, tampilan (yang membaca DB) dan sync (yang
    # mempertahankan nilai DB lama) akan selamanya menampilkan nilai lama.
    if result.success and kind == "onu-type":
        onu.onu_type_id = body.get("onu_type_id")
        onu.onu_type = body.get("onu_type_name")
    if result.success and kind == "replace-sn":
        new_serial = str(body.get("new_sn", "")).strip().upper()
        onu.serial_number = new_serial
        onu.mac_address = None
        onu.software_version = None
        onu.hardware_version = None
        # Seperti jalur job replace_onu: baris pending ber-serial baru sudah
        # terpakai (itulah ONU ini sekarang), jadi hapus supaya tidak muncul
        # lagi di Unconfigured dan tidak bisa di-authorize kedua kali.
        await db.execute(delete(UnconfiguredOnu).where(
            UnconfiguredOnu.olt_id == onu.olt_id,
            UnconfiguredOnu.serial_number == new_serial))
    if result.success and kind == "move" and target_pon_id is not None:
        onu.pon_port_id = target_pon_id
    # Port Eth/WiFi sukses wajib ditulis balik (pola sama dengan attached-vlans):
    # tanpa ini modal dibuka ulang menampilkan default, bukan nilai yang baru
    # ditulis. Hanya field non-rahasia yang disimpan (lihat port_config_entry).
    if result.success and (entry := port_config_entry(kind, body)) is not None:
        section_name, port_key, value = entry
        stored = dict(onu.port_configs or {})
        section = dict(stored.get(section_name) or {})
        section[port_key] = value
        stored[section_name] = section
        onu.port_configs = stored
    if result.success and kind == "wifi-clear":
        stored = dict(onu.port_configs or {})
        section = dict(stored.get("wifi") or {})
        section.pop(str(body.get("port")), None)
        stored["wifi"] = section
        onu.port_configs = stored
    # Mgmt-IP sukses wajib ditulis balik: tanpa ini modal dibuka ulang menampilkan
    # mode/IP lama sampai sync berikutnya. Mode perintah dipetakan kembali ke mode
    # perangkat: manual -> static, release -> inactive. Pool (auto-assign) tidak
    # menimpa IP lama karena IP barunya belum diketahui sampai sync berikutnya.
    if result.success and kind == "mgmt-ip":
        mode = body.get("mode")
        if mode == "manual":
            onu.mgmt_ip_mode = "static"
            if body.get("ip"):
                onu.ip_address = str(body["ip"]).strip()
        elif mode == "release":
            onu.mgmt_ip_mode = "inactive"
            onu.ip_address = None
        elif mode == "pool":
            onu.mgmt_ip_mode = "dhcp"
    await log_activity(
        db, action=f"onu.action.{kind}", entity_type="onu", entity_id=str(onu.id),
        success=result.success, user_id=user.id, olt_id=onu.olt_id, onu_id=onu.id,
        raw_command=" ; ".join(safe),
        raw_output=_SECRET_RE.sub(r"\1 <REDACTED>", result.raw_output or ""),
    )
    await db.commit()
    return {"ok": result.success, "executed": True,
            "detail": result.message or ("OK" if result.success else "OLT menolak perintah"),
            "commands": safe}


async def speed_profile_names(db: AsyncSession, ids: list[int]) -> list[str]:
    """Nama device profile dari id baris speed_profiles (dipakai uji live)."""
    rows = (await db.execute(select(SpeedProfile).where(SpeedProfile.id.in_(ids)))).scalars()
    return [r.device_profile_id or r.name for r in rows]
