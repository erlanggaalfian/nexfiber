"""Dashboard summary (PRD 3.4.A / M11). Every number is a real query."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import olt_repo, onu_repo
from app.services.onu_service import rx_thresholds

LOS_ALERT_AFTER = timedelta(minutes=15)

async def summary(db: AsyncSession) -> dict:
    now = datetime.now(UTC)
    olts = await olt_repo.count_by_status(db)
    onus = await onu_repo.count_by_status(db)
    rx = await rx_thresholds(db)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "action": {
            "los_over_15m": await onu_repo.count_down_since(db, now - LOS_ALERT_AFTER),
            "pending_authorization": await onu_repo.count_pending(db),
            "olt_poll_failed": sum(n for s, n in olts.items() if s != "online"),
        },
        "rx_histogram": await onu_repo.rx_histogram(db, rx["warn"], rx["crit"]),
        "rx_threshold": rx,
        "busiest_pon_ports": [
            {"pon_port_id": pon.id, "olt_id": olt.id, "olt_name": olt.name, "slot": pon.slot,
             "port": pon.port, "used": n, "capacity": olt.max_onu_per_port}
            for pon, olt, n in await olt_repo.busiest_pon_ports(db, 6)
        ],
        "onu_by_status": onus,
        "olt_count": sum(olts.values()),
        "activated_today": await onu_repo.count_registered_since(db, today),
        "last_poll_at": await olt_repo.last_sync_at(db),
    }
