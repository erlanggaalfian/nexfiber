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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.exceptions import ValidationAppError as ValidationError
from app.core.rbac import MANAGERS, scope_olt_ids
from app.drivers import zte_onu_actions as za
from app.models.olt import Olt, PonPort
from app.models.onu import Onu
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
}
#: kind yang butuh role manager (sama dengan endpoint tulis yang sudah ada).
MANAGER_KINDS = {"delete", "restore-factory", "replace-sn", "move"}

_SECRET_RE = re.compile(
    r"\b(key|password|pass|secret)\s+(?!default\b)\S+", re.I
)


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
    zones = (await db.execute(select(Zone).order_by(Zone.name))).scalars().all()
    splitters = (await db.execute(select(Splitter).order_by(Splitter.name))).scalars().all()
    onu_types = (await db.execute(select(OnuType).order_by(OnuType.name))).scalars().all()
    return {
        "vlans": [{"number": v.vlan_id, "name": v.name,
                   "is_management": v.type == "management"} for v in vlans],
        "zones": [{"id": z.id, "name": z.name} for z in zones],
        "splitters": [{"id": s.id, "name": s.name, "zone_id": s.zone_id,
                       "ports": s.capacity} for s in splitters],
        # Sector belum jadi tabel sendiri di Nexfiber (dipakai zone sebagai sektor).
        "sectors": [{"id": z.id, "name": z.name} for z in zones],
        "speed_profiles": [{"id": p.id, "name": p.name} for p in profiles],
        "onu_types": [{"id": t.id, "name": t.name} for t in onu_types],
        "wan_modes": ["webpage", "dhcp", "static", "pppoe"],
    }


async def update_location(db: AsyncSession, onu_id: int, body: dict, user: User):
    """Update location details — HANYA kolom DB, tanpa perintah ke perangkat.

    Pakai `onu_service.update_info` yang sudah ada (DRY); `sector_id` dipetakan ke
    kolom zone sektor belum punya tabel sendiri, jadi disimpan apa adanya bila ada.
    """
    from app.schemas.onu import OnuInfoBody

    onu, _ = await _onu_and_pon(db, onu_id, user)
    fields = {k: v for k, v in body.items()
              if k in OnuInfoBody.model_fields and v is not None}
    info = OnuInfoBody.model_validate(fields)
    return await onu_service.update_info(db, onu.serial_number, info, user)


def _build_commands(kind: str, onu: Onu, pon: PonPort, body: dict,
                    vlan_numbers: list[int] | None = None) -> list[str]:
    """kind -> perintah vendor. Hanya ZTE (MVP); vendor lain ditolak di caller."""
    slot, port, idx = pon.slot, pon.port, onu.onu_index
    if idx is None:
        raise ValidationError("ONU belum punya onu_index di OLT")
    if kind == "attached-vlans":
        return za.build_attached_vlans(slot, port, idx, vlan_numbers or [])
    if kind == "eth-port":
        return za.build_eth_port(
            slot, port, idx, eth_port=body["port"], enabled=body.get("enabled", True),
            mode=body["mode"], vlan_id=body.get("vlan_id"),
            allowed_vlans=body.get("allowed_vlans"), dhcp=body.get("dhcp", "none"))
    if kind == "wifi-port":
        return za.build_wifi_port(
            slot, port, idx, wifi_port=body["port"], enabled=body.get("enabled", True),
            mode=body["mode"], vlan_id=body.get("vlan_id"),
            allowed_vlans=body.get("allowed_vlans"), ssid=body.get("ssid"),
            auth_mode=body.get("auth_mode", "wpa2"), password=body.get("password"),
            dhcp=body.get("dhcp", "none"))
    if kind == "wifi-clear":
        return za.build_wifi_clear(slot, port, idx, wifi_port=body["port"])
    if kind == "onu-type":
        return za.build_onu_type(slot, port, idx, onu_type=body["onu_type_name"])
    if kind == "mgmt-ip":
        return za.build_mgmt_ip(slot, port, idx, mode=body["mode"], ip=body.get("ip"))
    if kind in ("voip-enable", "voip-disable"):
        return za.build_voip(slot, port, idx, enabled=kind == "voip-enable")
    if kind == "resync-config":
        return za.build_resync_config(slot, port, idx)
    if kind == "replace-sn":
        return za.build_replace_sn(slot, port, idx, onu_type=onu.onu_type or "",
                                   new_sn=body["new_sn"])
    if kind == "move":
        return za.build_replace_sn(body["board"], body["port"], idx,
                                   onu_type=onu.onu_type or "",
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
        await onu_service.update_info(
            db, onu.serial_number,
            OnuInfoBody.model_validate({"external_id": body.get("external_id")}), user)
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

    vlan_numbers = None
    if kind == "attached-vlans":
        vlans = await onu_repo.list_vlans(db, onu.olt_id, scope_olt_ids(user))
        wanted = body.get("vlans") or []
        known = {v.vlan_id for v in vlans}
        unknown = [n for n in wanted if n not in known]
        if unknown:
            raise ValidationError(f"VLAN belum terdaftar di OLT ini: {unknown}")
        vlan_numbers = wanted
    if kind == "onu-type":
        type_id = body.get("onu_type_id")
        onu_type = await db.get(OnuType, type_id) if type_id else None
        if onu_type is None:
            raise ValidationError("onu_type_id tidak dikenal")
        body = {**body, "onu_type_name": onu_type.name}

    try:
        commands = _build_commands(kind, onu, pon, body, vlan_numbers)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    onu_service.ensure_writes_allowed()
    safe = redact_commands(commands)

    from app.drivers.factory import build_driver

    driver = build_driver(olt)
    result = await driver.run_onu_commands(commands)
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
