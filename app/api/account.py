from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, mailer, security, settings
from app.api.common import read_upload
from app.database.database import get_db
from app.database.models import User
from app.services import backup_service, recovery_service, token_service, user_service

router = APIRouter(prefix="/api/account", tags=["account"])

BACKUPS_PER_HOUR = 6
RESTORES_PER_HOUR = 5
EMAIL_CHANGES_PER_HOUR = 6
PASSWORD_ATTEMPTS_PER_HOUR = 10


class EmailChange(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


class DigestChange(BaseModel):
    enabled: bool


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=security.MAX_PASSWORD_LENGTH)


def _limited(key: str, limit: int, window: int, message: str) -> None:
    wait = security.limiter.consume(key, limit, window)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"{message}; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )


def _require_email_support() -> None:
    if not settings.email_enabled():
        raise HTTPException(
            status_code=400, detail="email features are not available on this server"
        )


def _check_password(user: User, password: str) -> None:
    _limited(
        f"password:{user.id}", PASSWORD_ATTEMPTS_PER_HOUR, 3600, "too many attempts"
    )
    if not security.verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="password is incorrect")


def _send_verification(db: Session, user: User) -> tuple[str, str, str]:
    raw = token_service.issue(
        db, user, token_service.KIND_VERIFY_EMAIL, email=user.email_key
    )
    subject, body = mailer.verification_message(
        f"{settings.public_url()}/verify-email?token={raw}"
    )
    return subject, body, raw


@router.put("/email")
def change_email(
    payload: EmailChange,
    request: Request,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_email_support()
    _check_password(user, payload.password)
    _limited(f"email:{user.id}", EMAIL_CHANGES_PER_HOUR, 3600, "too many email requests")
    try:
        user_service.set_email(db, user, payload.email)
    except user_service.UserError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    subject, body, _raw = _send_verification(db, user)
    user_service.audit(db, "user.email_set", actor=user, ip=security.client_ip(request))
    db.commit()
    mailer.send_async(user.email, subject, body)
    return {"user": user_service.user_payload(user, private=True)}


@router.post("/email/resend")
def resend_verification(
    request: Request,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_email_support()
    if not user.email or user.email_verified_at is not None:
        raise HTTPException(status_code=400, detail="there is no address waiting for confirmation")
    _limited(f"email:{user.id}", EMAIL_CHANGES_PER_HOUR, 3600, "too many email requests")
    subject, body, _raw = _send_verification(db, user)
    db.commit()
    mailer.send_async(user.email, subject, body)
    return {"sent": True}


@router.delete("/email")
def remove_email(
    payload: PasswordConfirmation,
    request: Request,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    _check_password(user, payload.password)
    user_service.clear_email(db, user)
    user_service.audit(db, "user.email_removed", actor=user, ip=security.client_ip(request))
    db.commit()
    return {"user": user_service.user_payload(user, private=True)}


@router.get("/backup")
def download_backup(
    user: User = Depends(auth.current_user), db: Session = Depends(get_db)
) -> Response:
    _limited(f"backup:{user.id}", BACKUPS_PER_HOUR, 3600, "too many backups")
    content = backup_service.render(backup_service.export_backup(db, user.id))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="chesslytics-backup-{stamp}.json"'
        },
    )


@router.post("/backup/restore")
async def restore_backup(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    _limited(f"restore:{user.id}", RESTORES_PER_HOUR, 3600, "too many restores")
    text = await read_upload(file, settings.max_backup_bytes())
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="that file is not valid JSON") from exc
    try:
        result = backup_service.restore_backup(db, user.id, data)
    except backup_service.BackupError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_service.audit(
        db,
        "user.backup_restore",
        actor=user,
        ip=security.client_ip(request),
        detail=f"games={result['games_restored']}",
    )
    db.commit()
    return result


@router.post("/recovery-code")
def new_recovery_code(
    payload: PasswordConfirmation,
    request: Request,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    _check_password(user, payload.password)
    code = recovery_service.issue(db, user)
    user_service.audit(db, "user.recovery_code", actor=user, ip=security.client_ip(request))
    db.commit()
    return {"recovery_code": code, "user": user_service.user_payload(user, private=True)}


@router.put("/digest")
def set_digest(
    change: DigestChange,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    if change.enabled:
        _require_email_support()
        if not user.email or user.email_verified_at is None:
            raise HTTPException(
                status_code=400, detail="confirm your email address before turning on the digest"
            )
    user.digest_enabled = change.enabled
    if change.enabled:
        user.last_digest_at = None
    db.commit()
    return {"user": user_service.user_payload(user, private=True)}
