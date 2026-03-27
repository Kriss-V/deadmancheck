from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


class RegisterForm(BaseModel):
    email: EmailStr
    password: str


class LoginForm(BaseModel):
    email: EmailStr
    password: str


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("auth/register.html", {"request": request})


@router.post("/register")
async def register(form: RegisterForm, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=form.email, hashed_password=hash_password(form.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=604800)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login")
async def login(form: LoginForm, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(str(user.id))
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=604800)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response
