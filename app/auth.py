from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import security, settings
from app.database.database import get_db
from app.database.models import User

SESSION_COOKIE = "chesslytics_session"
CSRF_HEADER = "x-csrf-protection"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ROLE_ADMIN = "admin"


def unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def set_session_cookie(response: Response, request: Request, user: User) -> None:
    token = security.create_session_token(user.id, user.token_version or 0)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(settings.session_hours() * 3600),
        httponly=True,
        secure=security.is_https(request) or settings.env_bool("COOKIE_SECURE", False),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=security.is_https(request) or settings.env_bool("COOKIE_SECURE", False),
        samesite="lax",
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise unauthorized()
    payload = security.read_session_token(token)
    if payload is None:
        raise unauthorized("invalid or expired session")
    user = db.get(User, payload["uid"])
    if user is None or not user.is_active or (user.token_version or 0) != payload["ver"]:
        raise unauthorized("invalid or expired session")
    request.state.user = user
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="administrator access required")
    return user
