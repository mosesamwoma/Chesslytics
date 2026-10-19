from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, security, settings
from app.database.database import get_db
from app.database.models import User, utcnow
from app.services import user_service

logger = logging.getLogger("chesslytics")

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOGIN_IP_LIMIT = 20
LOGIN_IP_WINDOW = 600
REGISTER_IP_LIMIT = 5
REGISTER_IP_WINDOW = 3600


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class AccountDeletion(BaseModel):
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


def too_many(wait: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=429, detail=message, headers={"Retry-After": str(wait)}
    )


@router.get("/status")
def status() -> dict:
    return {
        "registration_enabled": settings.registration_enabled(),
        "min_password_length": security.MIN_PASSWORD_LENGTH,
    }


@router.post("/register", status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    if not settings.registration_enabled():
        raise HTTPException(status_code=403, detail="registration is closed")
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"register:{ip}", REGISTER_IP_LIMIT, REGISTER_IP_WINDOW)
    if wait:
        raise too_many(wait, "too many accounts created from this address; try again later")
    try:
        user = user_service.create_user(db, payload.username, payload.password)
        user.last_login_at = utcnow()
        user_service.audit(db, "user.register", actor=user, target=user.username, ip=ip)
        db.commit()
    except user_service.UserError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    auth.set_session_cookie(response, request, user)
    return {"user": user_service.user_payload(user)}


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    ip = security.client_ip(request)
    ip_key = f"login:{ip}"
    wait = security.limiter.retry_after(ip_key, LOGIN_IP_LIMIT, LOGIN_IP_WINDOW)
    if wait:
        raise too_many(wait, f"too many failed attempts; try again in {wait} seconds")
    try:
        user = user_service.authenticate(db, payload.username, payload.password)
    except user_service.AuthenticationFailed:
        security.limiter.record(ip_key, LOGIN_IP_WINDOW)
        logger.info("failed login for %r from %s", payload.username[:64], ip)
        raise HTTPException(status_code=401, detail="incorrect username or password")
    except user_service.AccountLocked as exc:
        security.limiter.record(ip_key, LOGIN_IP_WINDOW)
        user = user_service.get_by_username(db, payload.username)
        user_service.audit(
            db, "auth.locked", actor=user, target=payload.username[:64], ip=ip
        )
        db.commit()
        raise too_many(
            exc.retry_after, f"too many failed attempts; try again in {exc.retry_after} seconds"
        )
    except user_service.AccountDisabled:
        raise HTTPException(status_code=403, detail="this account has been disabled")
    user_service.audit(db, "auth.login", actor=user, ip=ip)
    db.commit()
    auth.set_session_cookie(response, request, user)
    return {"user": user_service.user_payload(user)}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    auth.clear_session_cookie(response, request)
    return {"signed_out": True}


@router.get("/me")
def me(user: User = Depends(auth.current_user)) -> dict:
    return {"user": user_service.user_payload(user)}


@router.post("/password")
def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"password:{user.id}", 10, 3600)
    if wait:
        raise too_many(wait, "too many attempts; try again later")
    if not security.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    try:
        user_service.change_password(db, user, payload.new_password)
    except user_service.UserError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_service.audit(db, "user.password_change", actor=user, ip=ip)
    db.commit()
    auth.set_session_cookie(response, request, user)
    return {"changed": True}


@router.delete("/me")
def delete_account(
    payload: AccountDeletion,
    request: Request,
    response: Response,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"password:{user.id}", 10, 3600)
    if wait:
        raise too_many(wait, "too many attempts; try again later")
    if not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="password is incorrect")
    if user.role == user_service.ROLE_ADMIN and user_service.count_active_admins(db) <= 1:
        raise HTTPException(status_code=400, detail="the last administrator cannot be deleted")
    name = user.username
    user_service.audit(db, "user.delete_self", actor=user, target=name, ip=ip)
    user_service.delete_user(db, user)
    db.commit()
    auth.clear_session_cookie(response, request)
    return {"deleted": True}
