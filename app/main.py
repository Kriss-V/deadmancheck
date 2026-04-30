import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from app.database import engine
from app.routers import auth, billing, monitors, oauth, ping, seo_pages, status_pages, uptime
from app.services.redis_client import close_redis, init_redis
from app.services.scheduler import start_scheduler, stop_scheduler


async def _run_migrations():
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(50)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_id VARCHAR(255)"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _run_migrations()
    await init_redis()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()


app = FastAPI(title="DeadManCheck", lifespan=lifespan, docs_url=None, redoc_url=None)

Instrumentator().instrument(app).expose(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    nonce = secrets.token_urlsafe(16)
    request.state.nonce = nonce
    csrf_token = request.cookies.get("csrf_token") or secrets.token_urlsafe(16)
    request.state.csrf_token = csrf_token
    response = await call_next(request)
    if "csrf_token" not in request.cookies:
        response.set_cookie("csrf_token", csrf_token, httponly=True, samesite="strict", secure=True)
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self'; "
        f"img-src 'self' data:; "
        f"font-src 'self'; "
        f"connect-src 'self'; "
        f"object-src 'none'; "
        f"base-uri 'self'; "
        f"form-action 'self' https://checkout.stripe.com; "
        f"frame-ancestors 'none'"
    )
    return response

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fromjson"] = json.loads

app.include_router(ping.router)
app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(monitors.router)
app.include_router(billing.router)
app.include_router(status_pages.router)
app.include_router(uptime.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/robots.txt")
async def robots():
    content = """User-agent: *
Allow: /

Disallow: /dashboard
Disallow: /monitors/
Disallow: /api/
Disallow: /status-pages/
Disallow: /uptime/
Disallow: /checkout
Disallow: /portal
Disallow: /webhook
Disallow: /login
Disallow: /register
Disallow: /forgot-password
Disallow: /reset-password

Sitemap: https://deadmancheck.io/sitemap.xml"""
    return Response(content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap():
    base = "https://deadmancheck.io"
    templates_dir = Path("app/templates")

    # Pages with fixed URLs that don't map 1-to-1 to template filenames
    static_urls = [
        "/",
        "/pricing",
        "/docs/quickstart",
        "/cron-job-monitoring",
        "/monitor-long-running-cron-jobs",
        "/cron-job-output-monitoring",
        "/backup-monitoring",
        "/etl-job-monitoring",
    ]

    # Auto-discover /compare/* pages
    compare_urls = [
        f"/compare/{p.stem}"
        for p in sorted((templates_dir / "compare").glob("*.html"))
    ]

    # Auto-discover top-level SEO pages (excludes layout/app templates)
    excluded = {
        "base", "landing", "pricing",
        "cron-job-monitoring", "monitor-long-running-cron-jobs",
        "cron-job-output-monitoring", "backup-monitoring", "etl-job-monitoring",
    }
    seo_urls = [
        f"/{p.stem}"
        for p in sorted(templates_dir.glob("*.html"))
        if p.stem not in excluded
    ]

    all_urls = static_urls + compare_urls + seo_urls

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in all_urls:
        lines.append(f"  <url><loc>{base}{url}</loc></url>")
    lines.append("</urlset>")

    return Response("\n".join(lines), media_type="application/xml")


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    return templates.TemplateResponse("pricing.html", {"request": request})


@app.get("/docs/quickstart", response_class=HTMLResponse)
async def quickstart(request: Request):
    return templates.TemplateResponse("docs/quickstart.html", {"request": request})


@app.get("/compare/vs-healthchecks", response_class=HTMLResponse)
async def vs_healthchecks(request: Request):
    return templates.TemplateResponse("compare/vs-healthchecks.html", {"request": request})


@app.get("/compare/vs-cronitor", response_class=HTMLResponse)
async def vs_cronitor(request: Request):
    return templates.TemplateResponse("compare/vs-cronitor.html", {"request": request})


@app.get("/cron-job-monitoring", response_class=HTMLResponse)
async def cron_job_monitoring(request: Request):
    return templates.TemplateResponse("cron-job-monitoring.html", {"request": request})


@app.get("/monitor-long-running-cron-jobs", response_class=HTMLResponse)
async def monitor_long_running(request: Request):
    return templates.TemplateResponse("monitor-long-running-cron-jobs.html", {"request": request})


@app.get("/cron-job-output-monitoring", response_class=HTMLResponse)
async def cron_job_output_monitoring(request: Request):
    return templates.TemplateResponse("cron-job-output-monitoring.html", {"request": request})


@app.get("/backup-monitoring", response_class=HTMLResponse)
async def backup_monitoring(request: Request):
    return templates.TemplateResponse("backup-monitoring.html", {"request": request})


@app.get("/etl-job-monitoring", response_class=HTMLResponse)
async def etl_job_monitoring(request: Request):
    return templates.TemplateResponse("etl-job-monitoring.html", {"request": request})


app.include_router(seo_pages.router)  # must be last — catches dynamic slugs
