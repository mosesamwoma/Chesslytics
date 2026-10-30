from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, mailer, security, settings
from app.database.database import get_db
from app.database.models import User
from app.services import session_service, token_service, user_service

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(auth.require_admin)]
)


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


def _target(db: Session, user_id: int) -> User:
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


def _would_remove_last_admin(db: Session, target: User) -> bool:
    return (
        target.role == user_service.ROLE_ADMIN
        and bool(target.is_active)
        and user_service.count_active_admins(db) <= 1
    )


@router.get("/email")
def email_status() -> dict:
    missing = settings.email_missing()
    return {
        "enabled": not missing,
        "provider": settings.mail_provider(),
        "from": settings.mail_from() or None,
        "public_url": settings.public_url() or None,
        "missing": missing,
    }


@router.post("/email/test")
def email_test(user: User = Depends(auth.current_user)) -> dict:
    wait = security.limiter.consume(f"mailtest:{user.id}", 5, 3600)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"too many test emails; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )
    if not settings.email_enabled():
        raise HTTPException(
            status_code=400,
            detail="email is not set up: missing " + ", ".join(settings.email_missing()),
        )
    if not user.email:
        raise HTTPException(
            status_code=400,
            detail="add an email address to your own account first (Account page)",
        )
    try:
        mailer.deliver(
            user.email,
            "Chesslytics test email",
            "This is a test message from your Chesslytics server. Email is working.\n",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"sending failed: {exc}") from exc
    return {"sent_to": user.email}


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    return user_service.platform_stats(db)


@router.get("/users")
def users(
    q: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    rows, total = user_service.list_users(db, q, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "users": rows}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    admin: User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
) -> dict:
    target = _target(db, user_id)
    ip = security.client_ip(request)
    changes = []

    if payload.role is not None and payload.role != target.role:
        if payload.role not in user_service.ROLES:
            raise HTTPException(status_code=400, detail="unknown role")
        if target.id == admin.id:
            raise HTTPException(status_code=400, detail="you cannot change your own role")
        if payload.role != user_service.ROLE_ADMIN and _would_remove_last_admin(db, target):
            raise HTTPException(status_code=400, detail="at least one administrator is required")
        target.role = payload.role
        user_service.revoke_sessions(db, target)
        changes.append(f"role={payload.role}")

    if payload.is_active is not None and payload.is_active != bool(target.is_active):
        if target.id == admin.id:
            raise HTTPException(status_code=400, detail="you cannot disable your own account")
        if not payload.is_active and _would_remove_last_admin(db, target):
            raise HTTPException(status_code=400, detail="at least one administrator is required")
        target.is_active = payload.is_active
        if not payload.is_active:
            session_service.end_all(db, target.id)
        user_service.revoke_sessions(db, target)
        changes.append(f"active={payload.is_active}")

    if changes:
        user_service.audit(
            db, "admin.user_update", actor=admin, target=target.username, ip=ip,
            detail=", ".join(changes),
        )
    db.commit()
    return {"user": user_service.user_payload(target)}


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: int,
    payload: PasswordReset,
    request: Request,
    admin: User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
) -> dict:
    target = _target(db, user_id)
    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="use the Account page to change your own password",
        )
    try:
        user_service.change_password(db, target, payload.new_password)
    except user_service.UserError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_service.audit(
        db, "admin.password_reset", actor=admin, target=target.username,
        ip=security.client_ip(request),
    )
    db.commit()
    return {"reset": True}


@router.post("/users/{user_id}/reset-link")
def reset_link(
    user_id: int,
    request: Request,
    admin: User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
) -> dict:
    target = _target(db, user_id)
    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="use the Account page to change your own password",
        )
    raw = token_service.issue(db, target, token_service.KIND_RESET_PASSWORD)
    user_service.audit(
        db, "admin.reset_link", actor=admin, target=target.username,
        ip=security.client_ip(request),
    )
    db.commit()
    return {
        "path": f"/reset-password?token={raw}",
        "expires_in": token_service.lifetime_seconds(token_service.KIND_RESET_PASSWORD),
    }


@router.post("/users/{user_id}/unlock")
def unlock(
    user_id: int,
    request: Request,
    admin: User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
) -> dict:
    target = _target(db, user_id)
    target.failed_logins = 0
    target.locked_until = None
    user_service.audit(
        db, "admin.unlock", actor=admin, target=target.username,
        ip=security.client_ip(request),
    )
    db.commit()
    return {"user": user_service.user_payload(target)}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
) -> dict:
    target = _target(db, user_id)
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="use account settings to delete yourself")
    if _would_remove_last_admin(db, target):
        raise HTTPException(status_code=400, detail="at least one administrator is required")
    name = target.username
    user_service.audit(
        db, "admin.user_delete", actor=admin, target=name, ip=security.client_ip(request)
    )
    user_service.delete_user(db, target)
    db.commit()
    return {"deleted": user_id}


@router.get("/audit")
def audit_log(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    return {"events": user_service.recent_audit(db, limit, offset)}
