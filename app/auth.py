from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import security, settings
from app.database.database import get_db
from app.database.models import User
from app.services import session_service

SESSION_COOKIE = "chesslytics_session"
HOST_COOKIE = "__Host-chesslytics_session"
CSRF_HEADER = "x-csrf-protection"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ROLE_ADMIN = "admin"


def unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def cookie_secure(request: Request) -> bool:
    return security.is_https(request) or settings.env_bool("COOKIE_SECURE", False)


def read_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(HOST_COOKIE) or request.cookies.get(SESSION_COOKIE)


def start_session(response: Response, request: Request, db: Session, user: User) -> None:
    token = session_service.start(
        db, user, security.client_ip(request), request.headers.get("user-agent", "")
    )
    db.commit()
    secure = cookie_secure(request)
    response.set_cookie(
        key=HOST_COOKIE if secure else SESSION_COOKIE,
        value=token,
        max_age=int(settings.session_hours() * 3600),
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    if secure:
        response.delete_cookie(key=SESSION_COOKIE, path="/")


def clear_session_cookie(response: Response, request: Request) -> None:
    secure = cookie_secure(request)
    response.delete_cookie(
        key=SESSION_COOKIE, path="/", httponly=True, secure=secure, samesite="strict"
    )
    response.delete_cookie(
        key=HOST_COOKIE, path="/", httponly=True, secure=True, samesite="strict"
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = read_cookie(request)
    if not token:
        raise unauthorized()
    payload = security.read_session_token(token)
    if payload is None:
        raise unauthorized("invalid or expired session")
    user = db.get(User, payload["uid"])
    if user is None or not user.is_active or (user.token_version or 0) != payload["ver"]:
        raise unauthorized("invalid or expired session")
    row = session_service.find(db, user.id, payload["sid"])
    if row is None:
        db.commit()
        raise unauthorized("invalid or expired session")
    if session_service.touch(db, row):
        db.commit()
    request.state.user = user
    request.state.sid = payload["sid"]
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="administrator access required")
    return user
