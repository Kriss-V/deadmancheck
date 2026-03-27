from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import auth, billing, monitors, ping
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

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(ping.router)
app.include_router(auth.router)
app.include_router(monitors.router)
app.include_router(billing.router)


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
