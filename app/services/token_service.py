from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.database.models import AccountToken, User, utcnow

KIND_VERIFY_EMAIL = "verify_email"
KIND_RESET_PASSWORD = "reset_password"
LIFETIMES = {
    KIND_VERIFY_EMAIL: timedelta(hours=24),
    KIND_RESET_PASSWORD: timedelta(hours=1),
}
RETENTION = timedelta(days=7)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def lifetime_seconds(kind: str) -> int:
    return int(LIFETIMES[kind].total_seconds())


def issue(session: Session, user: User, kind: str, email: Optional[str] = None) -> str:
    session.execute(
        delete(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.kind == kind,
            AccountToken.used_at.is_(None),
        )
    )
    raw = secrets.token_urlsafe(32)
    session.add(
        AccountToken(
            user_id=user.id,
            kind=kind,
            token_hash=_digest(raw),
            email=email,
            expires_at=utcnow() + LIFETIMES[kind],
        )
    )
    session.flush()
    return raw


def peek(session: Session, raw: str, kind: str) -> Optional[AccountToken]:
    if not raw or len(raw) > 128:
        return None
    token = session.scalar(
        select(AccountToken).where(
            AccountToken.token_hash == _digest(raw), AccountToken.kind == kind
        )
    )
    if token is None or token.used_at is not None:
        return None
    if _aware(token.expires_at) <= utcnow():
        return None
    return token


def consume(session: Session, token: AccountToken) -> bool:
    result = session.execute(
        update(AccountToken)
        .where(AccountToken.id == token.id, AccountToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    session.flush()
    return bool(result.rowcount)


def discard_unused(session: Session, user_id: int, kind: str) -> None:
    session.execute(
        delete(AccountToken).where(
            AccountToken.user_id == user_id,
            AccountToken.kind == kind,
            AccountToken.used_at.is_(None),
        )
    )
    session.flush()


def prune(session: Session) -> None:
    cutoff = utcnow() - RETENTION
    session.execute(
        delete(AccountToken).where(
            (AccountToken.expires_at < cutoff)
            | (AccountToken.used_at.is_not(None) & (AccountToken.used_at < cutoff))
        )
    )
    session.flush()
