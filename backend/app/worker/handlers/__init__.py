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
from app.services import onu_service, sync_service

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

async def sync_onu_status(db, job, olt, driver):
    return await sync_service.sync_onu_status(db, olt, driver)

async def sync_onu_optical(db, job, olt, driver):
    return await sync_service.sync_onu_optical(db, olt, driver)

async def sync_unconfigured(db, job, olt, driver):
    return await sync_service.sync_unconfigured(db, olt, driver)

async def backup_olt_config(db, job, olt, driver):
    triggered_by = f"user:{job.created_by}" if job.created_by else "schedule"
    return await sync_service.backup_olt_config(db, olt, driver, triggered_by)

async def test_connection(db, job, olt, driver):
    result = await driver.test_connection()
    if not result.success:
        raise CommandRejectedError(result.message or "OLT rejected command")
    olt.status = "online"
    olt.last_sync_at = datetime.now(UTC)
    olt.last_error = None
    return {"raw_output": result.raw_output[:2000]}

async def tr069_push(db, job, olt, driver):
    raise NotImplementedPhase2("Phase 2, belum diimplementasi")

HANDLERS: dict[str, Handler] = {
    "authorize_onu": authorize_onu,
    "delete_onu": delete_onu,
    "reboot_onu": reboot_onu,
    "set_state": set_state,
    "apply_speed_profile": apply_speed_profile,
    "sync_onu_status": sync_onu_status,
    "sync_onu_optical": sync_onu_optical,
    "sync_unconfigured": sync_unconfigured,
    "backup_olt_config": backup_olt_config,
    "test_connection": test_connection,
    "tr069_push": tr069_push,
}
