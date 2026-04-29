import logging
import secrets
from datetime import datetime, timedelta, timezone

import resend
from fastapi import APIRouter, Depends, Form, Request, status
from app.dependencies import verify_csrf
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.services.auth import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)
resend.api_key = settings.resend_api_key

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_csrf),
):
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse("auth/register.html", {
            "request": request, "error": "Email already registered"
        })

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if settings.resend_api_key:
        try:
            resend.Emails.send({
                "from": settings.alert_from_email,
                "to": [email],
                "subject": "Welcome to DeadManCheck",
                "html": f"""
<h2>Welcome to DeadManCheck 👋</h2>
<p>Your account is set up and ready to go.</p>
<p>Get started by creating your first monitor — it takes about 2 minutes:</p>
<p><a href="{settings.app_url}/monitors/new">Create your first monitor →</a></p>
<h3>Quick start</h3>
<p>Once you've created a monitor, add one line to your cron job:</p>
<pre style="background:#1f2937;color:#e5e7eb;padding:12px;border-radius:6px;">curl {settings.app_url}/ping/YOUR-MONITOR-UUID</pre>
<p>For duration tracking, bookend your job:</p>
<pre style="background:#1f2937;color:#e5e7eb;padding:12px;border-radius:6px;">curl {settings.app_url}/ping/YOUR-MONITOR-UUID/start
# ... your job ...
curl {settings.app_url}/ping/YOUR-MONITOR-UUID</pre>
<p>Questions? Reply to this email anytime.</p>
<p style="color:#6b7280;font-size:12px">DeadManCheck.io — Cron job monitoring</p>
""",
            })
        except Exception as e:
            logger.error(f"[auth] failed to send welcome email: {e}")

    token = create_access_token(str(user.id))
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", secure=True, max_age=604800)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_csrf),
):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "Invalid email or password"
        })

    token = create_access_token(str(user.id))
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", secure=True, max_age=604800)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_csrf),
):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always show success to prevent email enumeration
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()

        reset_url = f"{settings.app_url}/reset-password?token={token}"
        logger.info(f"[auth] password reset requested for {email}, resend_key_set={bool(settings.resend_api_key)}, app_url={settings.app_url}")
        if settings.resend_api_key:
            try:
                resend.Emails.send({
                "from": settings.alert_from_email,
                "to": [email],
                "subject": "Reset your DeadManCheck password",
                "html": f"""
<h2>Reset your password</h2>
<p>Click the link below to reset your password. This link expires in 1 hour.</p>
<p><a href="{reset_url}">Reset password →</a></p>
<p style="color:#6b7280;font-size:12px">If you didn't request this, ignore this email.</p>
""",
                })
                logger.info(f"[auth] password reset email sent to {email}")
            except Exception as e:
                logger.error(f"[auth] failed to send password reset email: {e}")

    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request,
        "success": "If that email is registered, you'll receive a reset link shortly."
    })


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    return templates.TemplateResponse("auth/reset_password.html", {"request": request, "token": token})


@router.post("/reset-password")
async def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_csrf),
):
    result = await db.execute(select(User).where(User.reset_token == token))
    user = result.scalar_one_or_none()

    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.now(timezone.utc):
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "token": token,
            "error": "This reset link is invalid or has expired."
        })

    user.hashed_password = hash_password(password)
    user.reset_token = None
    user.reset_token_expires_at = None
    await db.commit()

    return RedirectResponse(url="/login?reset=1", status_code=status.HTTP_302_FOUND)
