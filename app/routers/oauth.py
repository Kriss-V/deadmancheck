"""
OAuth2 SSO — Google and GitHub.
"""
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.services.auth import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["oauth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"


# ── Google ────────────────────────────────────────────────────────────────────

@router.get("/auth/google")
async def google_login():
    state = secrets.token_urlsafe(16)
    url = _GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.app_url}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    })
    response = RedirectResponse(url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", secure=True, max_age=300)
    return response


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    if not state or state != request.cookies.get("oauth_state"):
        return RedirectResponse("/login?error=1")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": f"{settings.app_url}/auth/google/callback",
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            return RedirectResponse("/login?error=1")

        access_token = token_resp.json().get("access_token")
        userinfo_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            return RedirectResponse("/login?error=1")

        info = userinfo_resp.json()
        email = info.get("email")
        oauth_id = str(info.get("id", ""))

    if not email:
        return RedirectResponse("/login?error=1")

    return await _login_or_create(email, "google", oauth_id, db)


# ── GitHub ────────────────────────────────────────────────────────────────────

@router.get("/auth/github")
async def github_login():
    state = secrets.token_urlsafe(16)
    url = _GITHUB_AUTH_URL + "?" + urlencode({
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.app_url}/auth/github/callback",
        "scope": "read:user user:email",
        "state": state,
    })
    response = RedirectResponse(url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", secure=True, max_age=300)
    return response


@router.get("/auth/github/callback")
async def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    if not state or state != request.cookies.get("oauth_state"):
        return RedirectResponse("/login?error=1")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "redirect_uri": f"{settings.app_url}/auth/github/callback",
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            return RedirectResponse("/login?error=1")

        access_token = token_resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}

        user_resp = await client.get(_GITHUB_USER_URL, headers=headers)
        if user_resp.status_code != 200:
            return RedirectResponse("/login?error=1")

        user_data = user_resp.json()
        oauth_id = str(user_data.get("id", ""))
        email = user_data.get("email")

        if not email:
            emails_resp = await client.get(_GITHUB_EMAILS_URL, headers=headers)
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                email = next(
                    (e["email"] for e in emails if e.get("primary") and e.get("verified")),
                    next((e["email"] for e in emails if e.get("verified")), None),
                )

    if not email:
        return RedirectResponse("/login?error=1")

    return await _login_or_create(email, "github", oauth_id, db)


# ── Shared ────────────────────────────────────────────────────────────────────

async def _login_or_create(
    email: str, provider: str, oauth_id: str, db: AsyncSession
) -> RedirectResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(email=email, hashed_password=None, oauth_provider=provider, oauth_id=oauth_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.oauth_provider:
        user.oauth_provider = provider
        user.oauth_id = oauth_id
        await db.commit()

    token = create_access_token(str(user.id))
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", secure=True, max_age=604800)
    response.delete_cookie("oauth_state")
    return response
