"""
Status pages — public and dashboard CRUD.
"""
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Monitor, Ping, StatusPage, User
from app.services.auth import get_current_user

router = APIRouter(tags=["status_pages"])
templates = Jinja2Templates(directory="app/templates")


# ── Public view (no auth) ────────────────────────────────────────────────────

@router.get("/status/{slug}", response_class=HTMLResponse)
async def public_status_page(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StatusPage).where(StatusPage.slug == slug))
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Status page not found")

    monitor_ids = json.loads(page.monitor_ids or "[]")
    monitors_data = []

    for mid in monitor_ids:
        try:
            uid = uuid.UUID(mid)
        except ValueError:
            continue
        m_result = await db.execute(select(Monitor).where(Monitor.id == uid))
        monitor = m_result.scalar_one_or_none()
        if not monitor:
            continue

        # Last 30 pings for uptime dots
        pings_result = await db.execute(
            select(Ping)
            .where(Ping.monitor_id == monitor.id)
            .order_by(Ping.received_at.desc())
            .limit(30)
        )
        pings = pings_result.scalars().all()

        monitors_data.append({"monitor": monitor, "pings": pings})

    # Overall status
    statuses = [m["monitor"].status for m in monitors_data]
    if any(s == "late" for s in statuses):
        overall = "issues"
    elif all(s == "up" for s in statuses) and statuses:
        overall = "operational"
    else:
        overall = "unknown"

    return templates.TemplateResponse("status/public.html", {
        "request": request,
        "page": page,
        "monitors_data": monitors_data,
        "overall": overall,
    })


# ── Dashboard views ──────────────────────────────────────────────────────────

@router.get("/status-pages", response_class=HTMLResponse)
async def list_status_pages(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StatusPage).where(StatusPage.user_id == user.id).order_by(StatusPage.created_at.desc())
    )
    pages = result.scalars().all()
    return templates.TemplateResponse("status/list.html", {
        "request": request,
        "user": user,
        "pages": pages,
    })


@router.get("/status-pages/new", response_class=HTMLResponse)
async def new_status_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    monitors_result = await db.execute(
        select(Monitor).where(Monitor.user_id == user.id).order_by(Monitor.name)
    )
    monitors = monitors_result.scalars().all()
    return templates.TemplateResponse("status/form.html", {
        "request": request,
        "user": user,
        "page": None,
        "monitors": monitors,
        "selected_ids": [],
    })


@router.get("/status-pages/{page_id}/edit", response_class=HTMLResponse)
async def edit_status_page(
    page_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = await _get_owned_page(page_id, user, db)
    monitors_result = await db.execute(
        select(Monitor).where(Monitor.user_id == user.id).order_by(Monitor.name)
    )
    monitors = monitors_result.scalars().all()
    return templates.TemplateResponse("status/form.html", {
        "request": request,
        "user": user,
        "page": page,
        "monitors": monitors,
        "selected_ids": json.loads(page.monitor_ids or "[]"),
    })


# ── API ──────────────────────────────────────────────────────────────────────

class StatusPageCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    monitor_ids: list[str] = []


@router.post("/api/status-pages")
async def create_status_page(
    body: StatusPageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slug = _sanitize_slug(body.slug)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid slug")

    existing = await db.execute(select(StatusPage).where(StatusPage.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already taken")

    page = StatusPage(
        id=uuid.uuid4(),
        user_id=user.id,
        name=body.name,
        slug=slug,
        description=body.description,
        monitor_ids=json.dumps(body.monitor_ids),
    )
    db.add(page)
    await db.commit()
    return {"id": str(page.id), "slug": page.slug}


@router.put("/api/status-pages/{page_id}")
async def update_status_page(
    page_id: str,
    body: StatusPageCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = await _get_owned_page(page_id, user, db)
    slug = _sanitize_slug(body.slug)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid slug")

    # Check slug uniqueness (excluding self)
    existing = await db.execute(select(StatusPage).where(StatusPage.slug == slug))
    existing_page = existing.scalar_one_or_none()
    if existing_page and existing_page.id != page.id:
        raise HTTPException(status_code=400, detail="Slug already taken")

    page.name = body.name
    page.slug = slug
    page.description = body.description
    page.monitor_ids = json.dumps(body.monitor_ids)
    await db.commit()
    return {"status": "updated"}


@router.delete("/api/status-pages/{page_id}")
async def delete_status_page(
    page_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = await _get_owned_page(page_id, user, db)
    await db.delete(page)
    await db.commit()
    return {"status": "deleted"}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_owned_page(page_id: str, user: User, db: AsyncSession) -> StatusPage:
    try:
        uid = uuid.UUID(page_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(
        select(StatusPage).where(StatusPage.id == uid, StatusPage.user_id == user.id)
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Not found")
    return page


def _sanitize_slug(slug: str) -> str:
    slug = slug.lower().strip()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug
