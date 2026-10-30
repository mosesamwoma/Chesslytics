from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import security, settings
from app.database.models import User, UserSession, utcnow

TOUCH_SECONDS = 300
MAX_SESSIONS_PER_USER = 20
USER_AGENT_LIMIT = 200


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def digest(sid: str) -> str:
    return hmac.new(settings.secret_key(), b"session:" + sid.encode("utf-8"), hashlib.sha256).hexdigest()


def start(session: Session, user: User, ip: str, user_agent: str) -> str:
    now = utcnow()
    session.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < now)
    )
    sid = secrets.token_urlsafe(32)
    row = UserSession(
        user_id=user.id,
        sid_hash=digest(sid),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_hours()),
        ip=(ip or "")[:64] or None,
        user_agent=(user_agent or "")[:USER_AGENT_LIMIT] or None,
    )
    session.add(row)
    session.flush()
    surplus = list(
        session.scalars(
            select(UserSession.id)
            .where(UserSession.user_id == user.id)
            .order_by(UserSession.created_at.desc())
            .offset(MAX_SESSIONS_PER_USER)
        )
    )
    if surplus:
        session.execute(delete(UserSession).where(UserSession.id.in_(surplus)))
    token = security.create_session_token(user.id, user.token_version or 0, sid)
    return token


def find(session: Session, user_id: int, sid: str) -> Optional[UserSession]:
    row = session.scalar(
        select(UserSession).where(
            UserSession.user_id == user_id, UserSession.sid_hash == digest(sid)
        )
    )
    if row is None:
        return None
    if _aware(row.expires_at) <= utcnow():
        session.delete(row)
        session.flush()
        return None
    return row


def touch(session: Session, row: UserSession) -> bool:
    now = utcnow()
    if (now - _aware(row.last_seen_at)).total_seconds() >= TOUCH_SECONDS:
        row.last_seen_at = now
        session.flush()
        return True
    return False


def end(session: Session, user_id: int, sid: str) -> None:
    session.execute(
        delete(UserSession).where(
            UserSession.user_id == user_id, UserSession.sid_hash == digest(sid)
        )
    )


def end_all(session: Session, user_id: int, keep_sid: Optional[str] = None) -> int:
    statement = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_sid:
        statement = statement.where(UserSession.sid_hash != digest(keep_sid))
    return int(session.execute(statement).rowcount or 0)


def end_one(session: Session, user_id: int, session_id: int) -> bool:
    removed = session.execute(
        delete(UserSession).where(UserSession.user_id == user_id, UserSession.id == session_id)
    )
    return bool(removed.rowcount)


def listing(session: Session, user_id: int, current_sid: Optional[str]) -> list[dict]:
    now = utcnow()
    current_hash = digest(current_sid) if current_sid else None
    rows = session.scalars(
        select(UserSession)
        .where(UserSession.user_id == user_id, UserSession.expires_at > now)
        .order_by(UserSession.last_seen_at.desc())
    )
    return [
        {
            "id": row.id,
            "created_at": _aware(row.created_at).isoformat(),
            "last_seen_at": _aware(row.last_seen_at).isoformat(),
            "expires_at": _aware(row.expires_at).isoformat(),
            "ip": row.ip,
            "user_agent": row.user_agent,
            "current": row.sid_hash == current_hash,
        }
        for row in rows
    ]


def prune(session: Session) -> None:
    session.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    session.flush()
