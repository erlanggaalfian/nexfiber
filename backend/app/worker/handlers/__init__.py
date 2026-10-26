"""One handler per job_type (PRD 4.2). Signature: (db, job, olt, driver) -> result dict.
Handlers don't commit; the worker commits on success and rolls back on exception.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CommandRejectedError
from app.drivers.base import OltDriver
from app.models.job import Job
from app.models.olt import Olt
from app.services import (
    olt_service,
    onu_service,
    onu_traffic_history_service,
    speed_profile_service,
    sync_service,
    vlan_service,
)

Handler = Callable[[AsyncSession, Job, Olt, OltDriver], Awaitable[dict]]

class NotImplementedPhase2(Exception):
    """Permanent failure: no retry."""

async def authorize_onu(db, job, olt, driver):
    return await onu_service.authorize_onu(db, job, driver)

async def delete_onu(db, job, olt, driver):
    return await onu_service.delete_onu(db, job, driver)

async def reboot_onu(db, job, olt, driver):
    return await onu_service.reboot_onu(db, job, driver)

async def set_state(db, job, olt, driver):
    return await onu_service.set_state(db, job, driver)

async def apply_speed_profile(db, job, olt, driver):
    return await onu_service.apply_speed_profile(db, job, driver)

async def refresh_onu_detail(db, job, olt, driver):
    return await onu_service.refresh_onu_detail(db, job, driver)

async def resync_onu(db, job, olt, driver):
    return await onu_service.resync_onu(db, job, driver)

async def set_onu_vlan(db, job, olt, driver):
    return await onu_service.set_onu_vlan(db, job, driver)

async def replace_onu(db, job, olt, driver):
    return await onu_service.replace_onu(db, job, driver)

async def restore_factory(db, job, olt, driver):
    return await onu_service.restore_factory(db, job, driver)

async def read_onu_status(db, job, olt, driver):
    return await onu_service.read_onu_status(db, job, driver)

async def read_onu_running_config(db, job, olt, driver):
    return await onu_service.read_onu_running_config(db, job, driver)

async def read_onu_software(db, job, olt, driver):
    return await onu_service.read_onu_software(db, job, driver)

async def create_vlan(db, job, olt, driver):
    return await vlan_service.push_create(db, job, driver)

async def delete_vlan(db, job, olt, driver):
    return await vlan_service.push_delete(db, job, driver)

async def push_speed_profile(db, job, olt, driver):
    return await speed_profile_service.push_to_olt(db, job, driver)

async def sync_speed_profiles(db, job, olt, driver):
    return await speed_profile_service.sync_from_olt(db, job, driver)

async def sync_onu_status(db, job, olt, driver):
    return await sync_service.sync_onu_status(db, olt, driver)

async def sync_onu_optical(db, job, olt, driver):
    return await sync_service.sync_onu_optical(db, olt, driver)

async def sync_olt_metrics(db, job, olt, driver):
    return await sync_service.sync_olt_metrics(db, olt, driver)

async def sync_unconfigured(db, job, olt, driver):
    return await sync_service.sync_unconfigured(db, olt, driver)

async def sample_onu_traffic(db, job, olt, driver):
    """Sampler histori trafik: SNMP saja, tidak memakai `driver` (dua bulkwalk per OLT)."""
    return await onu_traffic_history_service.sample_olt(db, olt)

async def backup_olt_config(db, job, olt, driver):
    triggered_by = f"user:{job.created_by}" if job.created_by else "schedule"
    return await sync_service.backup_olt_config(db, olt, driver, triggered_by)

async def test_connection(db, job, olt, driver):
    """Dua boolean terpisah dari dua tes sungguhan (DECISIONS "Audit fitur SmartOLT").

    Job gagal hanya kalau KEDUA protokol gagal; satu protokol hidup tetap berarti OLT
    terjangkau, dan hasil per protokol disimpan apa adanya di result job.
    """
    check = await driver.test_connection()
    result = {
        "cli_ok": check.cli_ok,
        "snmp_ok": check.snmp_ok,
        "cli_message": check.cli_message,
        "snmp_message": check.snmp_message,
        "raw_output": check.raw_output[:2000],
    }
    if not (check.cli_ok or check.snmp_ok):
        olt.status = "unreachable"
        olt.last_error = f"CLI: {check.cli_message} | SNMP: {check.snmp_message}"[:500]
        raise CommandRejectedError(olt.last_error)
    olt.status = "online"
    olt.last_sync_at = datetime.now(UTC)
    olt.last_error = None if (check.cli_ok and check.snmp_ok) else (
        f"CLI: {check.cli_message} | SNMP: {check.snmp_message}"[:500]
    )
    return result

async def set_vlan_ports(db, job, olt, driver):
    return await vlan_service.push_ports(db, job, driver)

async def set_port_config(db, job, olt, driver):
    return await olt_service.push_port_config(db, job, driver)

async def tr069_push(db, job, olt, driver):
    raise NotImplementedPhase2("Phase 2, belum diimplementasi")

HANDLERS: dict[str, Handler] = {
    "authorize_onu": authorize_onu,
    "delete_onu": delete_onu,
    "reboot_onu": reboot_onu,
    "set_state": set_state,
    "apply_speed_profile": apply_speed_profile,
    "refresh_onu_detail": refresh_onu_detail,
    "resync_onu": resync_onu,
    "set_onu_vlan": set_onu_vlan,
    "replace_onu": replace_onu,
    "restore_factory": restore_factory,
    "read_onu_status": read_onu_status,
    "read_onu_running_config": read_onu_running_config,
    "read_onu_software": read_onu_software,
    "create_vlan": create_vlan,
    "delete_vlan": delete_vlan,
    "push_speed_profile": push_speed_profile,
    "sync_speed_profiles": sync_speed_profiles,
    "sync_onu_status": sync_onu_status,
    "sync_onu_optical": sync_onu_optical,
    "sync_olt_metrics": sync_olt_metrics,
    "sync_unconfigured": sync_unconfigured,
    "sample_onu_traffic": sample_onu_traffic,
    "backup_olt_config": backup_olt_config,
    "test_connection": test_connection,
    "set_vlan_ports": set_vlan_ports,
    "set_port_config": set_port_config,
    "tr069_push": tr069_push,
}
