"""
Uptime monitor CRUD — dashboard API and HTML views.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Monitor, UptimeCheck, UptimeMonitor, User
from app.routers.monitors import PLAN_LIMITS, _count_all_monitors, check_alert_plan
from app.services.auth import get_current_user

router = APIRouter(tags=["uptime"])
templates = Jinja2Templates(directory="app/templates")


# ── HTML views ───────────────────────────────────────────────────────────────

@router.get("/uptime", response_class=HTMLResponse)
async def uptime_list(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == user.id).order_by(UptimeMonitor.created_at.desc())
    )
    monitors = result.scalars().all()
    return templates.TemplateResponse("uptime/list.html", {
        "request": request,
        "user": user,
        "monitors": monitors,
    })


@router.get("/uptime/new", response_class=HTMLResponse)
async def new_uptime_monitor(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("uptime/form.html", {
        "request": request,
        "user": user,
        "monitor": None,
    })


@router.get("/uptime/{monitor_id}", response_class=HTMLResponse)
async def uptime_detail(
    monitor_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    checks_result = await db.execute(
        select(UptimeCheck)
        .where(UptimeCheck.monitor_id == monitor.id)
        .order_by(UptimeCheck.checked_at.desc())
        .limit(50)
    )
    checks = checks_result.scalars().all()

    # Uptime % over last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = [c for c in checks if c.checked_at >= cutoff]
    uptime_pct = round(sum(1 for c in recent if c.is_up) / len(recent) * 100, 1) if recent else None

    # Chart data — oldest first, only checks with response times
    chart_checks = [c for c in reversed(checks) if c.response_ms is not None]
    chart_labels = [c.checked_at.strftime('%Y-%m-%dT%H:%M:%SZ') for c in chart_checks]
    chart_values = [round(c.response_ms, 1) for c in chart_checks]
    chart_colors = ['#22c55e' if c.is_up else '#ef4444' for c in chart_checks]

    return templates.TemplateResponse("uptime/detail.html", {
        "request": request,
        "user": user,
        "monitor": monitor,
        "checks": checks,
        "uptime_pct": uptime_pct,
        "chart_labels": chart_labels,
        "chart_values": chart_values,
        "chart_colors": chart_colors,
    })


@router.get("/uptime/{monitor_id}/edit", response_class=HTMLResponse)
async def edit_uptime_monitor(
    monitor_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    return templates.TemplateResponse("uptime/form.html", {
        "request": request,
        "user": user,
        "monitor": monitor,
    })


# ── API ──────────────────────────────────────────────────────────────────────

class UptimeMonitorCreate(BaseModel):
    name: str
    url: str
    interval_seconds: int = 300
    timeout_seconds: int = 10
    expected_status_code: int = 200
    alert_email: str | None = None
    alert_webhook_url: str | None = None
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    pagerduty_key: str | None = None
    alert_on_recovery: bool = True


@router.post("/api/uptime")
async def create_uptime_monitor(
    body: UptimeMonitorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_alert_plan(user, body)
    # Enforce shared plan limit (cron + uptime combined)
    limit = PLAN_LIMITS.get(user.plan, 5)
    if limit is not None:
        count = await _count_all_monitors(user.id, db)
        if count >= limit:
            raise HTTPException(status_code=402, detail=f"Plan limit reached ({limit} monitors). Upgrade to add more.")

    now = datetime.now(timezone.utc)
    monitor = UptimeMonitor(
        id=uuid.uuid4(),
        user_id=user.id,
        next_check_at=now,  # check immediately on first run
        **body.model_dump(),
    )
    db.add(monitor)
    await db.commit()
    return {"id": str(monitor.id)}


@router.put("/api/uptime/{monitor_id}")
async def update_uptime_monitor(
    monitor_id: str,
    body: UptimeMonitorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_alert_plan(user, body)
    monitor = await _get_owned_monitor(monitor_id, user, db)
    for field, value in body.model_dump().items():
        setattr(monitor, field, value)
    await db.commit()
    return {"status": "updated"}


@router.delete("/api/uptime/{monitor_id}")
async def delete_uptime_monitor(
    monitor_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    await db.delete(monitor)
    await db.commit()
    return {"status": "deleted"}


@router.post("/api/uptime/{monitor_id}/pause")
async def pause_uptime_monitor(
    monitor_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    monitor.is_paused = not monitor.is_paused
    await db.commit()
    return {"status": "paused" if monitor.is_paused else "active"}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_owned_monitor(monitor_id: str, user: User, db: AsyncSession) -> UptimeMonitor:
    try:
        uid = uuid.UUID(monitor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.id == uid, UptimeMonitor.user_id == user.id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Not found")
    return monitor
