"""
Background scheduler: every 30s checks all active monitors and fires alerts
for any that have gone past their grace period without a ping.
"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Monitor
from app.services.alerts import send_down_alert

scheduler = AsyncIOScheduler(timezone="UTC")


def compute_next_expected(monitor: Monitor) -> datetime:
    now = datetime.now(timezone.utc)
    if monitor.schedule_type == "cron" and monitor.cron_expression:
        cron = croniter(monitor.cron_expression, now)
        return cron.get_next(datetime)
    elif monitor.period_seconds:
        return now + timedelta(seconds=monitor.period_seconds)
    return now + timedelta(hours=24)


async def check_monitors() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Monitor).where(
                Monitor.is_paused == False,
                Monitor.status.in_(["up", "new"]),
                Monitor.next_expected_at.isnot(None),
            )
        )
        monitors = result.scalars().all()

        for monitor in monitors:
            deadline = monitor.next_expected_at + timedelta(seconds=monitor.grace_seconds)
            if now >= deadline:
                monitor.status = "late"
                await db.commit()
                await send_down_alert(monitor, reason="missed_ping", db=db)


def start_scheduler() -> None:
    scheduler.add_job(check_monitors, "interval", seconds=30, id="check_monitors", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
