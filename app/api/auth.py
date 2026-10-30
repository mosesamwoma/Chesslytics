from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, mailer, security, settings
from app.database.database import get_db
from app.database.models import User, utcnow
from app.services import recovery_service, session_service, token_service, user_service

logger = logging.getLogger("chesslytics")

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOGIN_IP_LIMIT = 20
LOGIN_IP_WINDOW = 600
REGISTER_IP_LIMIT = 5
REGISTER_IP_WINDOW = 3600
RESET_IP_LIMIT = 10
RESET_IP_WINDOW = 3600
FORGOT_IP_LIMIT = 6
FORGOT_ADDRESS_LIMIT = 3
FORGOT_WINDOW = 3600
RECOVER_IP_LIMIT = 15
RECOVER_USER_LIMIT = 8
RECOVER_WINDOW = 3600
VERIFY_IP_LIMIT = 20
VERIFY_IP_WINDOW = 3600


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)
    email: Optional[str] = Field(default=None, max_length=254)


class RecoverRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    recovery_code: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class AccountDeletion(BaseModel):
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class ForgotRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)


class ResetRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)


def too_many(wait: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=429, detail=message, headers={"Retry-After": str(wait)}
    )


@router.get("/status")
def status() -> dict:
    return {
        "registration_enabled": settings.registration_enabled(),
        "min_password_length": security.MIN_PASSWORD_LENGTH,
        "email_enabled": settings.email_enabled(),
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
    address = (payload.email or "").strip()
    wants_email = bool(address) and settings.email_enabled()
    if wants_email:
        problem = mailer.email_error(address)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
    verification: Optional[tuple[str, str]] = None
    try:
        user = user_service.create_user(db, payload.username, payload.password)
        user.last_login_at = utcnow()
        recovery_code = recovery_service.issue(db, user)
        if wants_email:
            user_service.set_email(db, user, address)
            raw = token_service.issue(
                db, user, token_service.KIND_VERIFY_EMAIL, email=user.email_key
            )
            verification = mailer.verification_message(
                f"{settings.public_url()}/verify-email?token={raw}"
            )
        user_service.audit(db, "user.register", actor=user, target=user.username, ip=ip)
        db.commit()
    except user_service.UserError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if verification is not None and user.email:
        mailer.send_async(user.email, verification[0], verification[1])
    auth.start_session(response, request, db, user)
    return {
        "user": user_service.user_payload(user, private=True),
        "recovery_code": recovery_code,
    }


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
        raise HTTPException(status_code=401, detail="incorrect username or password") from None
    except user_service.AccountLocked as exc:
        security.limiter.record(ip_key, LOGIN_IP_WINDOW)
        user = user_service.get_by_username(db, payload.username)
        user_service.audit(
            db, "auth.locked", actor=user, target=payload.username[:64], ip=ip
        )
        db.commit()
        raise too_many(
            exc.retry_after, f"too many failed attempts; try again in {exc.retry_after} seconds"
        ) from None
    except user_service.AccountDisabled:
        raise HTTPException(status_code=403, detail="this account has been disabled") from None
    user_service.audit(db, "auth.login", actor=user, ip=ip)
    db.commit()
    auth.start_session(response, request, db, user)
    return {"user": user_service.user_payload(user, private=True)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    token = auth.read_cookie(request)
    payload = security.read_session_token(token) if token else None
    if payload is not None:
        session_service.end(db, payload["uid"], payload["sid"])
        db.commit()
    auth.clear_session_cookie(response, request)
    return {"signed_out": True}


@router.get("/sessions")
def list_sessions(
    request: Request,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"sessions": session_service.listing(db, user.id, request.state.sid)}


@router.post("/sessions/revoke-others")
def revoke_other_sessions(
    request: Request,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    count = session_service.end_all(db, user.id, keep_sid=request.state.sid)
    user_service.audit(db, "auth.sessions_revoked", actor=user, ip=security.client_ip(request))
    db.commit()
    return {"revoked": count}


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    response: Response,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    mine = session_service.listing(db, user.id, request.state.sid)
    target = next((item for item in mine if item["id"] == session_id), None)
    if target is None or not session_service.end_one(db, user.id, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    user_service.audit(db, "auth.session_revoked", actor=user, ip=security.client_ip(request))
    db.commit()
    if target["current"]:
        auth.clear_session_cookie(response, request)
    return {"revoked": session_id, "signed_out": bool(target["current"])}


@router.get("/me")
def me(user: User = Depends(auth.current_user)) -> dict:
    return {"user": user_service.user_payload(user, private=True)}


@router.post("/forgot")
def forgot_password(
    payload: ForgotRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    if not settings.email_enabled():
        raise HTTPException(
            status_code=400, detail="password reset by email is not available on this server"
        )
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"forgot:{ip}", FORGOT_IP_LIMIT, FORGOT_WINDOW)
    if wait:
        raise too_many(wait, "too many requests; try again later")
    identifier = payload.identifier.strip()
    wait = security.limiter.consume(
        f"forgot-id:{identifier.lower()}", FORGOT_ADDRESS_LIMIT, FORGOT_WINDOW
    )
    if wait:
        raise too_many(wait, "too many requests; try again later")
    user = user_service.find_for_reset(db, identifier)
    if user is not None:
        raw = token_service.issue(db, user, token_service.KIND_RESET_PASSWORD)
        user_service.audit(db, "auth.reset_requested", actor=user, ip=ip)
        db.commit()
        subject, body = mailer.reset_message(f"{settings.public_url()}/reset-password?token={raw}")
        mailer.send_async(user.email, subject, body)
    return {"sent": True}


@router.post("/recover")
def recover_password(
    payload: RecoverRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"recover:{ip}", RECOVER_IP_LIMIT, RECOVER_WINDOW)
    if wait:
        raise too_many(wait, "too many attempts; try again later")
    key = security.normalize_username(payload.username.strip())
    wait = security.limiter.consume(f"recover-user:{key}", RECOVER_USER_LIMIT, RECOVER_WINDOW)
    if wait:
        raise too_many(wait, "too many attempts for this account; try again later")
    user = user_service.get_by_username(db, payload.username.strip())
    valid = recovery_service.matches(user, payload.recovery_code)
    if user is None or not valid or not user.is_active:
        raise HTTPException(
            status_code=400, detail="the username or recovery code is not correct"
        )
    problem = security.password_error(payload.new_password, user.username)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    user_service.change_password(db, user, payload.new_password)
    new_code = recovery_service.issue(db, user)
    user_service.audit(db, "auth.password_recovered", actor=user, ip=ip)
    db.commit()
    return {"recovered": True, "recovery_code": new_code}


@router.post("/reset")
def reset_password(
    payload: ResetRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"reset:{ip}", RESET_IP_LIMIT, RESET_IP_WINDOW)
    if wait:
        raise too_many(wait, "too many attempts; try again later")
    token = token_service.peek(db, payload.token, token_service.KIND_RESET_PASSWORD)
    user = db.get(User, token.user_id) if token is not None else None
    if token is None or user is None:
        raise HTTPException(status_code=400, detail="this reset link is invalid or has expired")
    problem = security.password_error(payload.new_password, user.username)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if not token_service.consume(db, token):
        db.rollback()
        raise HTTPException(status_code=400, detail="this reset link is invalid or has expired")
    user_service.change_password(db, user, payload.new_password)
    token_service.discard_unused(db, user.id, token_service.KIND_RESET_PASSWORD)
    user_service.audit(db, "auth.password_reset", actor=user, ip=ip)
    db.commit()
    return {"reset": True}


@router.post("/verify-email")
def verify_email(
    payload: VerifyRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    ip = security.client_ip(request)
    wait = security.limiter.consume(f"verify:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW)
    if wait:
        raise too_many(wait, "too many attempts; try again later")
    token = token_service.peek(db, payload.token, token_service.KIND_VERIFY_EMAIL)
    user = db.get(User, token.user_id) if token is not None else None
    if token is None or user is None or not token.email:
        raise HTTPException(
            status_code=400, detail="this confirmation link is invalid or has expired"
        )
    try:
        user_service.confirm_email(db, user, token.email)
    except user_service.UserError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token_service.consume(db, token)
    user_service.audit(db, "user.email_verified", actor=user, ip=ip)
    db.commit()
    return {"verified": True}


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
    auth.start_session(response, request, db, user)
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
