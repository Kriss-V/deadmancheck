"""
app/routers/seo_pages.py

Generic router that serves SEO content pages from HTML templates.
Handles three URL patterns:
  /compare/vs-[competitor]     → app/templates/compare/vs-[competitor].html
  /[use-case]-monitoring       → app/templates/[use-case]-monitoring.html
  /[platform]-cron-monitoring  → app/templates/[platform]-cron-monitoring.html

To add a new page: drop the .html file in the right templates folder and it
is served automatically — no code changes needed.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Adjust this path if your templates directory is in a different location
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── Slugs that should NOT be handled by this generic router ──────────────────
# These are routes already registered elsewhere in your app.
# Add any slug here that has its own dedicated router/view.
RESERVED_SLUGS = {
    "cron-job-monitoring",
    "backup-monitoring",
    "etl-job-monitoring",
    "cron-job-output-monitoring",
    "monitor-long-running-cron-jobs",
}


# ── Compare pages ─────────────────────────────────────────────────────────────

@router.get("/compare/{slug}", response_class=HTMLResponse)
async def compare_page(request: Request, slug: str):
    """
    Serves /compare/vs-[competitor] pages.
    Template file: app/templates/compare/{slug}.html
    """
    template_path = TEMPLATES_DIR / "compare" / f"{slug}.html"

    if not template_path.exists():
        # Fall through to 404 — FastAPI will handle it
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Page not found")

    return templates.TemplateResponse(
        f"compare/{slug}.html",
        {"request": request},
    )


# ── Use-case and platform pages ───────────────────────────────────────────────

@router.get("/{slug}", response_class=HTMLResponse)
async def seo_page(request: Request, slug: str):
    """
    Serves use-case pages (/etl-monitoring, /celery-task-monitoring etc.)
    and platform pages (/railway-cron-monitoring etc.)

    Template file: app/templates/{slug}.html

    Reserved slugs (handled by other routers) return 404 from here so
    FastAPI keeps routing them to the correct handler.
    """
    if slug in RESERVED_SLUGS:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Page not found")

    template_path = TEMPLATES_DIR / f"{slug}.html"

    if not template_path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Page not found")

    return templates.TemplateResponse(
        f"{slug}.html",
        {"request": request},
    )
