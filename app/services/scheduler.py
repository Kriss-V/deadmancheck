"""
Background scheduler: every 30s checks all active monitors and fires alerts
for any that have gone past their grace period without a ping.
Also polls uptime monitors every 60s.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Monitor, UptimeCheck, UptimeMonitor
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


async def check_uptime_monitors() -> None:
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(UptimeMonitor).where(
                UptimeMonitor.is_paused == False,
                UptimeMonitor.next_check_at <= now,
            )
        )
        monitors = result.scalars().all()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for monitor in monitors:
                await _run_uptime_check(monitor, client, db, now)


async def _run_uptime_check(
    monitor: UptimeMonitor,
    client: httpx.AsyncClient,
    db: AsyncSession,
    now: datetime,
) -> None:
    from app.services.alerts import maybe_send_uptime_recovery, send_uptime_down_alert

    is_up = False
    status_code = None
    response_ms = None
    error = None

    try:
        start = time.monotonic()
        resp = await client.get(monitor.url, timeout=monitor.timeout_seconds)
        response_ms = round((time.monotonic() - start) * 1000, 1)
        status_code = resp.status_code
        is_up = (status_code == monitor.expected_status_code) or (200 <= status_code < 300 and monitor.expected_status_code == 200)
    except httpx.TimeoutException:
        error = f"Timed out after {monitor.timeout_seconds}s"
    except Exception as e:
        error = str(e)[:500]

    # Record check
    check = UptimeCheck(
        id=uuid.uuid4(),
        monitor_id=monitor.id,
        checked_at=now,
        is_up=is_up,
        status_code=status_code,
        response_ms=response_ms,
        error=error,
    )
    db.add(check)

    prev_status = monitor.status
    monitor.last_checked_at = now
    monitor.last_response_ms = response_ms
    monitor.last_status_code = status_code
    monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)

    if is_up:
        monitor.status = "up"
        if prev_status == "down":
            monitor.alert_sent_at = None
            await db.commit()
            await maybe_send_uptime_recovery(monitor, db)
        else:
            await db.commit()
    else:
        monitor.status = "down"
        await db.commit()
        await send_uptime_down_alert(monitor, status_code, error, db)


def start_scheduler() -> None:
    scheduler.add_job(check_monitors, "interval", seconds=30, id="check_monitors", replace_existing=True)
    scheduler.add_job(check_uptime_monitors, "interval", seconds=60, id="check_uptime_monitors", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
