import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_fastapi_instrumentator import Instrumentator

from app.routers import auth, billing, monitors, ping, status_pages, uptime
from app.services.redis_client import close_redis, init_redis
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()


app = FastAPI(title="DeadManCheck", lifespan=lifespan, docs_url=None, redoc_url=None)

Instrumentator().instrument(app).expose(app)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fromjson"] = json.loads

app.include_router(ping.router)
app.include_router(auth.router)
app.include_router(monitors.router)
app.include_router(billing.router)
app.include_router(status_pages.router)
app.include_router(uptime.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


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
