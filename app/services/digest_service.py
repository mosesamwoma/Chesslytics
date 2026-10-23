from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mailer, settings
from app.database.database import session_scope
from app.database.models import Game, User, utcnow
from app.services import progress_service, training_service

logger = logging.getLogger("chesslytics.digest")

DIGEST_INTERVAL = timedelta(days=7)
CHECK_SECONDS = 3600
MAX_PER_RUN = 100


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def eligible(user: User) -> bool:
    return bool(
        user.is_active
        and user.digest_enabled
        and user.email
        and user.email_verified_at is not None
    )


def due_users(session: Session, now: Optional[datetime] = None) -> list[User]:
    moment = now or utcnow()
    users = session.scalars(
        select(User).where(User.digest_enabled.is_(True), User.is_active.is_(True))
    )
    return [
        user
        for user in users
        if eligible(user)
        and (user.last_digest_at is None or _aware(user.last_digest_at) <= moment - DIGEST_INTERVAL)
    ][:MAX_PER_RUN]


def build(session: Session, user: User, now: Optional[datetime] = None) -> dict:
    moment = now or utcnow()
    progress = progress_service.progress(session, user.id, weeks=8)
    stats = training_service.stats(session, user.id)
    since = moment - DIGEST_INTERVAL
    new_games = sum(
        1
        for created in session.scalars(
            select(Game.created_at).where(Game.user_id == user.id, Game.created_at >= since)
        )
        if created is not None
    )
    weeks = progress["weeks"]
    latest = weeks[-1] if weeks else None
    previous = weeks[-2] if len(weeks) >= 2 else None
    return {
        "new_games": new_games,
        "latest": latest,
        "previous": previous,
        "due_now": stats["due_now"],
        "new_puzzles": stats["new_puzzles"],
        "streak": stats["activity"]["current_streak"],
        "goal": stats["activity"]["daily_goal"],
        "has_content": bool(new_games or latest or stats["due_now"] or stats["new_puzzles"]),
    }


def _change(latest: Optional[dict], previous: Optional[dict]) -> Optional[str]:
    if not latest or not previous:
        return None
    now_value = latest.get("mistakes_per_100")
    before = previous.get("mistakes_per_100")
    if now_value is None or before is None:
        return None
    if now_value < before:
        return f"down from {before} the week before, which is the right direction"
    if now_value > before:
        return f"up from {before} the week before"
    return f"the same as the week before ({before})"


def render(user: User, digest: dict) -> tuple[str, str]:
    lines = [f"Hi {user.username}, here is your week in Chesslytics.", ""]
    latest = digest["latest"]
    if digest["new_games"]:
        lines.append(f"New games added this week: {digest['new_games']}")
    if latest:
        lines.append(
            f"Most recent week of play: {latest['games']} games, "
            f"{latest['mistakes_per_100']} mistakes per 100 moves"
        )
        change = _change(latest, digest["previous"])
        if change:
            lines.append(f"That is {change}.")
    if digest["due_now"]:
        lines.append(f"Puzzles due for review: {digest['due_now']}")
    if digest["new_puzzles"]:
        lines.append(f"Puzzles you have not tried yet: {digest['new_puzzles']}")
    if digest["streak"]:
        lines.append(f"Your practice streak: {digest['streak']} days")
    else:
        lines.append(f"Solve {digest['goal']} puzzles today to start a streak.")
    base = settings.public_url()
    if base:
        lines.extend(["", f"Practice now: {base}/training"])
    lines.extend(
        [
            "",
            "You get this email once a week because you turned on the weekly digest. "
            "You can turn it off any time on the Account page.",
        ]
    )
    return "Your weekly Chesslytics digest", "\n".join(lines) + "\n"


def send_due(now: Optional[datetime] = None) -> int:
    if not settings.email_enabled():
        return 0
    sent = 0
    with session_scope() as session:
        for user in due_users(session, now):
            moment = now or utcnow()
            try:
                digest = build(session, user, moment)
                if digest["has_content"]:
                    subject, body = render(user, digest)
                    mailer.deliver(user.email or "", subject, body)
                    sent += 1
            except Exception:
                logger.exception("could not send a weekly digest")
                continue
            user.last_digest_at = moment
    return sent


class DigestScheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None or not settings.email_enabled():
            return
        self._thread = threading.Thread(target=self._run, name="digest", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(CHECK_SECONDS):
            try:
                send_due()
            except Exception:
                logger.exception("weekly digest run failed")


scheduler = DigestScheduler()
