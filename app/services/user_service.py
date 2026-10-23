from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import mailer, security, settings
from app.database.models import (
    AccountToken,
    AnalysisJob,
    AuditLog,
    CoachInsight,
    Game,
    Mistake,
    Move,
    Pattern,
    PlayerProfile,
    PuzzleAttempt,
    User,
    utcnow,
)

logger = logging.getLogger("chesslytics")

ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLES = (ROLE_USER, ROLE_ADMIN)
MAX_ACCOUNT_FAILURES = 8
ACCOUNT_LOCK_MINUTES = 15


class UserError(ValueError):
    pass


class AuthenticationFailed(Exception):
    pass


class AccountLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("account temporarily locked")
        self.retry_after = retry_after


class AccountDisabled(Exception):
    pass


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def audit(
    session: Session,
    action: str,
    actor: Optional[User] = None,
    target: Optional[str] = None,
    ip: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor.id if actor is not None else None,
            actor_name=actor.username[:64] if actor is not None else None,
            action=action[:48],
            target=target[:128] if target else None,
            ip=ip[:64] if ip else None,
            detail=detail[:255] if detail else None,
        )
    )
    logger.info(
        "audit action=%s actor=%s target=%s ip=%s",
        action,
        actor.username if actor is not None else "-",
        target or "-",
        ip or "-",
    )


def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def get_by_username(session: Session, username: str) -> Optional[User]:
    key = security.normalize_username(username)
    return session.scalar(select(User).where(User.username_key == key))


def count_users(session: Session) -> int:
    return int(session.scalar(select(func.count(User.id))) or 0)


def count_active_admins(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count(User.id)).where(
                User.role == ROLE_ADMIN, User.is_active.is_(True)
            )
        )
        or 0
    )


def create_user(
    session: Session,
    username: str,
    password: str,
    role: str = ROLE_USER,
    allow_reserved: bool = False,
) -> User:
    username = username.strip()
    problem = security.username_error(username, allow_reserved=allow_reserved)
    if problem:
        raise UserError(problem)
    problem = security.password_error(password, username)
    if problem:
        raise UserError(problem)
    if role not in ROLES:
        raise UserError("unknown role")
    if get_by_username(session, username) is not None:
        raise UserError("that username is already taken")

    user = User(
        username=username,
        username_key=security.normalize_username(username),
        password_hash=security.hash_password(password),
        role=role,
        is_active=True,
        token_version=0,
        failed_logins=0,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise UserError("that username is already taken") from exc
    return user


def authenticate(session: Session, username: str, password: str) -> User:
    user = get_by_username(session, username)
    if user is None:
        security.burn_password_check(password)
        raise AuthenticationFailed()

    now = utcnow()
    locked_until = _aware(user.locked_until)
    if locked_until is not None and locked_until > now:
        security.burn_password_check(password)
        raise AccountLocked(max(1, int((locked_until - now).total_seconds()) + 1))

    if not security.verify_password(password, user.password_hash):
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_ACCOUNT_FAILURES:
            user.failed_logins = 0
            user.locked_until = now + timedelta(minutes=ACCOUNT_LOCK_MINUTES)
        session.commit()
        raise AuthenticationFailed()

    if not user.is_active:
        raise AccountDisabled()

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    session.commit()
    return user


def change_password(session: Session, user: User, new_password: str) -> None:
    problem = security.password_error(new_password, user.username)
    if problem:
        raise UserError(problem)
    user.password_hash = security.hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1
    user.failed_logins = 0
    user.locked_until = None
    session.flush()


def revoke_sessions(session: Session, user: User) -> None:
    user.token_version = (user.token_version or 0) + 1
    session.flush()


def user_payload(user: User, private: bool = False) -> dict:
    payload = {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.role == ROLE_ADMIN,
        "is_active": bool(user.is_active),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "email_verified": user.email_verified_at is not None,
        "digest_enabled": bool(user.digest_enabled),
    }
    if private:
        payload["email"] = user.email
    return payload


def set_email(session: Session, user: User, email: str) -> None:
    problem = mailer.email_error(email)
    if problem:
        raise UserError(problem)
    key = mailer.normalize_email(email)
    if user.email_key == key and user.email_verified_at is not None:
        raise UserError("that address is already confirmed on your account")
    user.email = email.strip()
    user.email_key = key
    user.email_verified_at = None
    session.flush()


def clear_email(session: Session, user: User) -> None:
    user.email = None
    user.email_key = None
    user.email_verified_at = None
    session.execute(
        delete(AccountToken).where(
            AccountToken.user_id == user.id,
            AccountToken.kind == "verify_email",
        )
    )
    session.flush()


def confirm_email(session: Session, user: User, key: str) -> None:
    if user.email_key != key:
        raise UserError("this link is no longer valid")
    other = session.scalar(
        select(User.id).where(
            User.email_key == key,
            User.email_verified_at.is_not(None),
            User.id != user.id,
        )
    )
    if other is not None:
        raise UserError("that address is already confirmed on another account")
    user.email_verified_at = utcnow()
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise UserError("that address is already confirmed on another account") from exc


def find_for_reset(session: Session, identifier: str) -> Optional[User]:
    text_value = identifier.strip()
    if not text_value:
        return None
    if "@" in text_value:
        user = session.scalar(
            select(User).where(
                User.email_key == mailer.normalize_email(text_value),
                User.email_verified_at.is_not(None),
            )
        )
    else:
        user = get_by_username(session, text_value)
        if user is not None and user.email_verified_at is None:
            return None
    if user is None or not user.is_active or not user.email:
        return None
    return user


def delete_user_data(session: Session, user_id: int) -> None:
    game_ids = select(Game.id).where(Game.user_id == user_id)
    mistake_ids = select(Mistake.id).where(
        (Mistake.user_id == user_id) | (Mistake.game_id.in_(game_ids))
    )
    profile_ids = select(PlayerProfile.id).where(PlayerProfile.user_id == user_id)

    session.execute(
        delete(PuzzleAttempt).where(
            (PuzzleAttempt.user_id == user_id) | (PuzzleAttempt.mistake_id.in_(mistake_ids))
        )
    )
    session.execute(delete(CoachInsight).where(CoachInsight.user_id == user_id))
    session.execute(delete(AccountToken).where(AccountToken.user_id == user_id))
    session.execute(delete(Pattern).where(Pattern.profile_id.in_(profile_ids)))
    session.execute(delete(PlayerProfile).where(PlayerProfile.user_id == user_id))
    session.execute(
        delete(Mistake).where((Mistake.user_id == user_id) | (Mistake.game_id.in_(game_ids)))
    )
    session.execute(delete(Move).where(Move.game_id.in_(game_ids)))
    session.execute(delete(Game).where(Game.user_id == user_id))
    session.execute(delete(AnalysisJob).where(AnalysisJob.user_id == user_id))
    session.flush()


def delete_user(session: Session, user: User) -> None:
    delete_user_data(session, user.id)
    session.execute(delete(User).where(User.id == user.id))
    session.flush()


def adopt_orphans(session: Session, admin_id: int) -> dict:
    counts: dict[str, int] = {}
    statements = {
        "games": "UPDATE games SET user_id = :uid WHERE user_id IS NULL",
        "mistakes": (
            "UPDATE mistakes SET user_id = "
            "(SELECT g.user_id FROM games g WHERE g.id = mistakes.game_id) "
            "WHERE user_id IS NULL"
        ),
        "puzzle_attempts": (
            "UPDATE puzzle_attempts SET user_id = "
            "(SELECT m.user_id FROM mistakes m WHERE m.id = puzzle_attempts.mistake_id) "
            "WHERE user_id IS NULL"
        ),
        "player_profiles": "UPDATE player_profiles SET user_id = :uid WHERE user_id IS NULL",
        "coach_insights": "UPDATE coach_insights SET user_id = :uid WHERE user_id IS NULL",
    }
    for table, statement in statements.items():
        result = session.execute(text(statement), {"uid": admin_id})
        counts[table] = int(result.rowcount or 0)
    session.flush()
    return counts


def bootstrap_admin(session: Session) -> Optional[User]:
    password = settings.admin_password()
    username = settings.admin_username() or "admin"
    admin: Optional[User] = None

    if password:
        problem = security.username_error(username, allow_reserved=True)
        if problem is None:
            problem = security.password_error(password, username)
        if problem:
            logger.error(
                "ADMIN_USERNAME / ADMIN_PASSWORD rejected: %s. No administrator was created.",
                problem,
            )
        else:
            admin = get_by_username(session, username)
            if admin is None:
                try:
                    admin = create_user(
                        session, username, password, ROLE_ADMIN, allow_reserved=True
                    )
                    audit(session, "admin.bootstrap", actor=admin, target=admin.username)
                    logger.info("created administrator %s", admin.username)
                except UserError as exc:
                    logger.error("could not create administrator: %s", exc)
            else:
                changed = False
                if admin.role != ROLE_ADMIN:
                    admin.role = ROLE_ADMIN
                    changed = True
                if not admin.is_active:
                    admin.is_active = True
                    changed = True
                if settings.env_bool("ADMIN_RESET_PASSWORD", False):
                    admin.password_hash = security.hash_password(password)
                    admin.token_version = (admin.token_version or 0) + 1
                    admin.failed_logins = 0
                    admin.locked_until = None
                    changed = True
                    logger.warning(
                        "administrator password was reset from ADMIN_PASSWORD; "
                        "remove ADMIN_RESET_PASSWORD now"
                    )
                if changed:
                    audit(session, "admin.bootstrap.update", actor=admin, target=admin.username)

    if admin is None:
        admin = session.scalar(
            select(User)
            .where(User.role == ROLE_ADMIN, User.is_active.is_(True))
            .order_by(User.id)
            .limit(1)
        )
    if admin is None:
        logger.warning(
            "no administrator exists; set ADMIN_USERNAME and ADMIN_PASSWORD (10+ characters)"
        )
        return None

    adopted = adopt_orphans(session, admin.id)
    if any(adopted.values()):
        logger.info("assigned existing data to %s: %s", admin.username, adopted)
    session.commit()
    return admin


def list_users(
    session: Session, query: Optional[str], limit: int, offset: int
) -> tuple[list[dict], int]:
    filters = []
    if query:
        escaped = (
            query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        filters.append(User.username_key.like(f"%{escaped}%", escape="\\"))

    total = int(session.scalar(select(func.count(User.id)).where(*filters)) or 0)
    users = list(
        session.scalars(
            select(User).where(*filters).order_by(User.id).limit(limit).offset(offset)
        )
    )
    ids = [user.id for user in users]
    game_counts: dict[int, int] = {}
    mistake_counts: dict[int, int] = {}
    if ids:
        game_counts = dict(
            session.execute(
                select(Game.user_id, func.count(Game.id))
                .where(Game.user_id.in_(ids))
                .group_by(Game.user_id)
            ).all()
        )
        mistake_counts = dict(
            session.execute(
                select(Mistake.user_id, func.count(Mistake.id))
                .where(Mistake.user_id.in_(ids))
                .group_by(Mistake.user_id)
            ).all()
        )
    rows = []
    for user in users:
        row = user_payload(user)
        row["games"] = int(game_counts.get(user.id, 0))
        row["mistakes"] = int(mistake_counts.get(user.id, 0))
        locked = _aware(user.locked_until)
        row["locked"] = bool(locked is not None and locked > utcnow())
        rows.append(row)
    return rows, total


def platform_stats(session: Session) -> dict:
    now = utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    return {
        "users": count_users(session),
        "active_users": int(
            session.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
        ),
        "admins": count_active_admins(session),
        "new_users_7d": int(
            session.scalar(select(func.count(User.id)).where(User.created_at >= week_ago))
            or 0
        ),
        "active_users_24h": int(
            session.scalar(select(func.count(User.id)).where(User.last_login_at >= day_ago))
            or 0
        ),
        "games": int(session.scalar(select(func.count(Game.id))) or 0),
        "games_analyzed": int(
            session.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_not(None)))
            or 0
        ),
        "mistakes": int(session.scalar(select(func.count(Mistake.id))) or 0),
        "puzzle_attempts": int(session.scalar(select(func.count(PuzzleAttempt.id))) or 0),
        "jobs_queued": int(
            session.scalar(select(func.count(AnalysisJob.id)).where(AnalysisJob.status == "queued"))
            or 0
        ),
        "jobs_running": int(
            session.scalar(
                select(func.count(AnalysisJob.id)).where(AnalysisJob.status == "running")
            )
            or 0
        ),
        "registration_open": settings.registration_enabled(),
    }


def recent_audit(session: Session, limit: int, offset: int = 0) -> list[dict]:
    rows = session.scalars(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "actor": row.actor_name,
            "action": row.action,
            "target": row.target,
            "ip": row.ip,
            "detail": row.detail,
        }
        for row in rows
    ]


def prune_audit(session: Session, days: int = 180) -> None:
    cutoff = utcnow() - timedelta(days=days)
    session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    session.flush()

