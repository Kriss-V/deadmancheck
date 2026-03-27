"""
Ping endpoints — the core product mechanic.

Each monitor gets a unique UUID. Jobs call:
  GET/POST /ping/{uuid}            — success heartbeat
  GET/POST /ping/{uuid}/start      — job started (begins duration tracking)
  GET/POST /ping/{uuid}/fail       — job explicitly failed

Duration tracking:
  If a /start was received, the next /ping or /success records the elapsed time.
  If duration exceeds expect_duration_max_seconds or >duration_alert_pct% of avg, an anomaly alert fires.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Monitor, Ping
from app.services.alerts import maybe_send_recovery_alert
from app.services.redis_client import START_PING_TTL_SECONDS, get_redis
from app.services.scheduler import compute_next_expected

router = APIRouter(tags=["ping"])

_START_KEY_PREFIX = "start:"


async def _get_monitor(monitor_id: str, db: AsyncSession) -> Monitor:
    try:
        uid = uuid.UUID(monitor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    result = await db.execute(select(Monitor).where(Monitor.id == uid))
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


async def _compute_duration(monitor_id: str) -> float | None:
    redis = get_redis()
    if redis is None:
        return None
    key = _START_KEY_PREFIX + str(monitor_id)
    value = await redis.getdel(key)
    if value is None:
        return None
    start = datetime.fromisoformat(value)
    return (datetime.now(timezone.utc) - start).total_seconds()


def _update_rolling_avg(monitor: Monitor, duration: float) -> None:
    if monitor.avg_duration_seconds is None:
        monitor.avg_duration_seconds = duration
    else:
        # Exponential moving average (alpha=0.2, recent pings weighted more)
        monitor.avg_duration_seconds = 0.8 * monitor.avg_duration_seconds + 0.2 * duration


def _is_duration_anomaly(monitor: Monitor, duration: float) -> bool:
    if not monitor.expect_duration_enabled:
        return False
    # Hard max
    if monitor.expect_duration_max_seconds and duration > monitor.expect_duration_max_seconds:
        return True
    # % above rolling average
    if monitor.avg_duration_seconds and monitor.avg_duration_seconds > 0:
        pct = (duration / monitor.avg_duration_seconds) * 100
        if pct > monitor.duration_alert_pct:
            return True
    return False


@router.api_route("/ping/{monitor_id}", methods=["GET", "POST"])
async def ping_success(
    monitor_id: str,
    request: Request,
    exit_code: Optional[int] = Query(None),
    output: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, db)

    if monitor.is_paused:
        return {"status": "paused"}

    was_late = monitor.status == "late"
    duration = await _compute_duration(monitor_id)
    anomaly = _is_duration_anomaly(monitor, duration) if duration is not None else False

    if duration is not None:
        _update_rolling_avg(monitor, duration)
        monitor.last_duration_seconds = duration

    ping = Ping(
        monitor_id=monitor.id,
        kind="success",
        duration_seconds=duration,
        duration_anomaly=int(anomaly),
        exit_code=exit_code,
        output=(output or "")[:10000] if output else None,
        source_ip=request.client.host if request.client else None,
    )

    monitor.status = "up"
    monitor.last_ping_at = datetime.now(timezone.utc)
    monitor.next_expected_at = compute_next_expected(monitor)

    db.add(ping)
    await db.commit()

    if was_late:
        await maybe_send_recovery_alert(monitor, db)

    response: dict = {"status": "ok"}
    if duration is not None:
        response["duration_seconds"] = round(duration, 2)
    if anomaly:
        response["warning"] = "duration_anomaly"
    return response


@router.api_route("/ping/{monitor_id}/start", methods=["GET", "POST"])
async def ping_start(
    monitor_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, db)

    if monitor.is_paused:
        return {"status": "paused"}

    redis = get_redis()
    if redis is not None:
        key = _START_KEY_PREFIX + str(monitor.id)
        await redis.set(key, datetime.now(timezone.utc).isoformat(), ex=START_PING_TTL_SECONDS)

    ping = Ping(
        monitor_id=monitor.id,
        kind="start",
        source_ip=request.client.host if request.client else None,
    )
    db.add(ping)
    await db.commit()

    return {"status": "ok", "message": "start recorded — call /ping/{id} when done"}


@router.api_route("/ping/{monitor_id}/fail", methods=["GET", "POST"])
async def ping_fail(
    monitor_id: str,
    request: Request,
    exit_code: Optional[int] = Query(None),
    output: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_monitor(monitor_id, db)
    duration = await _compute_duration(monitor_id)

    ping = Ping(
        monitor_id=monitor.id,
        kind="fail",
        duration_seconds=duration,
        exit_code=exit_code,
        output=(output or "")[:10000] if output else None,
        source_ip=request.client.host if request.client else None,
    )

    monitor.status = "late"  # treat explicit fail same as late — triggers alert
    monitor.last_ping_at = datetime.now(timezone.utc)

    db.add(ping)
    await db.commit()

    # Fire alert immediately on explicit fail
    from app.services.alerts import send_down_alert
    await send_down_alert(monitor, reason="explicit_fail", db=db)

    return {"status": "ok", "message": "failure recorded"}
