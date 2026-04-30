"""
Monitor CRUD — dashboard API and HTML views.
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Monitor, Ping, UptimeMonitor, User
from app.services.auth import get_current_user
from app.services.scheduler import compute_next_expected

router = APIRouter(tags=["monitors"])
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fromjson"] = json.loads

PLAN_LIMITS = {
    "free": settings.plan_free_monitors,
    "developer": settings.plan_developer_monitors,
    "team": settings.plan_team_monitors,
    "business": None,  # unlimited
}

_DEVELOPER_PLANS = {"developer", "team", "business"}
_TEAM_PLANS = {"team", "business"}


def check_alert_plan(user: User, body) -> None:
    if user.plan not in _DEVELOPER_PLANS:
        if body.slack_webhook_url or body.discord_webhook_url or body.telegram_bot_token:
            raise HTTPException(
                status_code=402,
                detail="Slack, Discord, and Telegram alerts require the Developer plan or higher.",
            )
    if user.plan not in _TEAM_PLANS:
        if body.pagerduty_key:
            raise HTTPException(
                status_code=402,
                detail="PagerDuty integration requires the Team plan or higher.",
            )


async def _count_all_monitors(user_id, db: AsyncSession) -> int:
    cron = (await db.execute(select(func.count()).where(Monitor.user_id == user_id))).scalar()
    uptime = (await db.execute(select(func.count()).where(UptimeMonitor.user_id == user_id))).scalar()
    return cron + uptime


# ── HTML views ──────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Monitor).where(Monitor.user_id == user.id).order_by(Monitor.created_at.desc())
    )
    monitors = result.scalars().all()
    plan_limit = PLAN_LIMITS.get(user.plan, 5)
    total_count = await _count_all_monitors(user.id, db)
    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "user": user,
        "monitors": monitors,
        "plan_limit": plan_limit,
        "total_count": total_count,
    })


@router.get("/monitors/new", response_class=HTMLResponse)
async def new_monitor_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("dashboard/monitor_form.html", {
        "request": request,
        "user": user,
        "monitor": None,
    })


@router.get("/monitors/{monitor_id}", response_class=HTMLResponse)
async def monitor_detail(
    monitor_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    result = await db.execute(
        select(Ping)
        .where(Ping.monitor_id == monitor.id)
        .order_by(Ping.received_at.desc())
        .limit(50)
    )
    pings = result.scalars().all()
    ping_url = f"{settings.app_url}/ping/{monitor.id}"
    return templates.TemplateResponse("dashboard/monitor_detail.html", {
        "request": request,
        "user": user,
        "monitor": monitor,
        "pings": pings,
        "ping_url": ping_url,
    })


@router.get("/monitors/{monitor_id}/edit", response_class=HTMLResponse)
async def edit_monitor_page(
    monitor_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    return templates.TemplateResponse("dashboard/monitor_form.html", {
        "request": request,
        "user": user,
        "monitor": monitor,
    })


# ── API ──────────────────────────────────────────────────────────────────────

class MonitorCreate(BaseModel):
    name: str
    schedule_type: str = "period"
    period_seconds: int | None = None
    cron_expression: str | None = None
    grace_seconds: int = 300
    tags: str = ""
    alert_email: str | None = None
    alert_webhook_url: str | None = None
    alert_on_recovery: bool = True
    expect_duration_enabled: bool = False
    expect_duration_max_seconds: int | None = None
    duration_alert_pct: int = 200
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    pagerduty_key: str | None = None
    assertions: str | None = None


@router.post("/api/monitors")
async def create_monitor(
    body: MonitorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_alert_plan(user, body)
    # Enforce plan limit (shared pool: cron + uptime)
    limit = PLAN_LIMITS.get(user.plan, 5)
    if limit is not None:
        count = await _count_all_monitors(user.id, db)
        if count >= limit:
            raise HTTPException(status_code=402, detail=f"Plan limit reached ({limit} monitors). Upgrade to add more.")

    monitor = Monitor(
        user_id=user.id,
        **body.model_dump(),
    )
    monitor.next_expected_at = compute_next_expected(monitor)
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return {"id": str(monitor.id), "ping_url": f"{settings.app_url}/ping/{monitor.id}"}


@router.put("/api/monitors/{monitor_id}")
async def update_monitor(
    monitor_id: str,
    body: MonitorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_alert_plan(user, body)
    monitor = await _get_owned_monitor(monitor_id, user, db)
    for field, value in body.model_dump().items():
        setattr(monitor, field, value)
    monitor.next_expected_at = compute_next_expected(monitor)
    await db.commit()
    return {"status": "updated"}


@router.delete("/api/monitors/{monitor_id}")
async def delete_monitor(
    monitor_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    await db.delete(monitor)
    await db.commit()
    return {"status": "deleted"}


@router.post("/api/monitors/{monitor_id}/pause")
async def pause_monitor(
    monitor_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitor = await _get_owned_monitor(monitor_id, user, db)
    monitor.is_paused = not monitor.is_paused
    await db.commit()
    return {"status": "paused" if monitor.is_paused else "active"}


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_owned_monitor(monitor_id: str, user: User, db: AsyncSession) -> Monitor:
    try:
        uid = uuid.UUID(monitor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(
        select(Monitor).where(Monitor.id == uid, Monitor.user_id == user.id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Not found")
    return monitor
