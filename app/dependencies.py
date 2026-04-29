from fastapi import Form, HTTPException, Request


async def verify_csrf(request: Request, csrf_token: str = Form(default="")):
    if csrf_token != request.cookies.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
