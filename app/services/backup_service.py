from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Optional

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import JSON, Boolean, Float, Integer, String, Text

from app import settings
from app.chess.pgn_parser import game_metadata, parse_pgn
from app.database.models import Game, Mistake, Pattern, PlayerProfile, PuzzleAttempt
from app.services import game_service

FORMAT = "chesslytics-backup"
VERSION = 1
MAX_PGN_CHARS = 200_000
MAX_JSON_CHARS = 200_000
MAX_TEXT_CHARS = 20_000
MAX_MISTAKES = 100_000
MAX_ATTEMPTS = 200_000
MAX_PATTERNS = 500
INT_LIMIT = 2**31 - 1

MISTAKE_SKIP = {"id", "user_id", "game_id", "created_at"}
ATTEMPT_SKIP = {"id", "user_id", "mistake_id", "created_at"}
PROFILE_SKIP = {"id", "user_id", "created_at"}
PATTERN_SKIP = {"id", "profile_id", "created_at"}

_INVALID = object()


class BackupError(ValueError):
    pass


def _row(instance: Any, skip: set[str]) -> dict:
    values = {}
    for column in instance.__table__.columns:
        if column.name in skip or column.primary_key:
            continue
        value = getattr(instance, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        values[column.name] = value
    return values


def export_backup(session: Session, user_id: int) -> dict:
    games = list(
        session.scalars(select(Game).where(Game.user_id == user_id).order_by(Game.id))
    )
    mistakes = list(
        session.scalars(
            select(Mistake)
            .where(Mistake.user_id == user_id)
            .order_by(Mistake.game_id, Mistake.ply)
        )
    )
    attempts_by_mistake: dict[int, list[dict]] = {}
    for attempt in session.scalars(
        select(PuzzleAttempt)
        .where(PuzzleAttempt.user_id == user_id)
        .order_by(PuzzleAttempt.id)
    ):
        attempts_by_mistake.setdefault(attempt.mistake_id, []).append(
            _row(attempt, ATTEMPT_SKIP)
        )
    mistakes_by_game: dict[int, list[dict]] = {}
    for mistake in mistakes:
        entry = _row(mistake, MISTAKE_SKIP)
        entry["attempts"] = attempts_by_mistake.get(mistake.id, [])
        mistakes_by_game.setdefault(mistake.game_id, []).append(entry)

    exported_games = []
    for game in games:
        exported_games.append(
            {
                "pgn": game.pgn,
                "source": game.source,
                "mistakes": mistakes_by_game.get(game.id, []),
            }
        )

    profile = session.scalar(
        select(PlayerProfile)
        .where(PlayerProfile.user_id == user_id)
        .order_by(PlayerProfile.created_at.desc(), PlayerProfile.id.desc())
        .limit(1)
    )
    exported_profile = None
    if profile is not None:
        exported_profile = _row(profile, PROFILE_SKIP)
        exported_profile["patterns"] = [
            _row(pattern, PATTERN_SKIP) for pattern in profile.patterns
        ]

    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "games": exported_games,
        "profile": exported_profile,
    }


def render(backup: dict) -> str:
    return json.dumps(backup, separators=(",", ":"), default=str)


def _coerce(column_type: Any, value: Any) -> Any:
    if isinstance(column_type, Boolean):
        return value if isinstance(value, bool) else _INVALID
    if isinstance(column_type, Integer):
        if isinstance(value, bool) or not isinstance(value, int):
            return _INVALID
        return value if abs(value) <= INT_LIMIT else _INVALID
    if isinstance(column_type, Float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _INVALID
        number = float(value)
        return number if math.isfinite(number) else _INVALID
    if isinstance(column_type, (String, Text)):
        if not isinstance(value, str):
            return _INVALID
        text_value = value.replace("\x00", "")
        length = getattr(column_type, "length", None) or MAX_TEXT_CHARS
        return text_value[:length]
    if isinstance(column_type, JSON):
        try:
            encoded = json.dumps(value)
        except (TypeError, ValueError):
            return _INVALID
        return value if len(encoded) <= MAX_JSON_CHARS else _INVALID
    return _INVALID


def _build(model: Any, raw: Any, skip: set[str]) -> Optional[Any]:
    if not isinstance(raw, dict):
        return None
    values = {}
    for column in model.__table__.columns:
        name = column.name
        if name in skip or column.primary_key:
            continue
        value = raw.get(name)
        coerced = _INVALID if value is None else _coerce(column.type, value)
        if coerced is _INVALID:
            if column.nullable:
                values[name] = None
                continue
            if column.default is not None:
                continue
            return None
        values[name] = coerced
    return model(**values)


def _valid_fen(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        chess.Board(value)
    except ValueError:
        return None
    return value


def _mistake(raw: Any) -> Optional[Mistake]:
    mistake = _build(Mistake, raw, MISTAKE_SKIP)
    if mistake is None:
        return None
    if mistake.color not in ("white", "black") or mistake.ply < 1 or mistake.move_number < 1:
        return None
    mistake.fen = _valid_fen(mistake.fen)
    mistake.fen_after = _valid_fen(mistake.fen_after)
    return mistake


def restore_backup(session: Session, user_id: int, data: Any) -> dict:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("this file is not a Chesslytics backup")
    if data.get("version") != VERSION:
        raise BackupError("this backup was made by an incompatible version")
    entries = data.get("games")
    if not isinstance(entries, list):
        raise BackupError("the backup has no games list")
    if len(entries) > settings.max_games_per_user():
        raise BackupError(
            f"the backup holds more than {settings.max_games_per_user()} games, "
            "which is the most an account can keep"
        )

    longest = settings.max_plies_per_game()
    parsed: list[tuple[dict, Any, str]] = []
    invalid = 0
    for entry in entries:
        text_value = entry.get("pgn") if isinstance(entry, dict) else None
        if not isinstance(text_value, str) or not text_value.strip() or len(text_value) > MAX_PGN_CHARS:
            invalid += 1
            continue
        games, _errors = parse_pgn(text_value)
        if len(games) != 1 or game_service.plies_in(games[0]) > longest:
            invalid += 1
            continue
        parsed.append((entry, games[0], game_metadata(games[0])["fingerprint"]))

    fingerprints = list({fingerprint for _, _, fingerprint in parsed})
    known: set[str] = set()
    for start in range(0, len(fingerprints), 500):
        chunk = fingerprints[start : start + 500]
        known.update(
            session.scalars(
                select(Game.fingerprint).where(
                    Game.user_id == user_id, Game.fingerprint.in_(chunk)
                )
            )
        )

    fresh: list[tuple[dict, Any, str]] = []
    seen: set[str] = set()
    for entry, game, fingerprint in parsed:
        if fingerprint in known or fingerprint in seen:
            continue
        seen.add(fingerprint)
        fresh.append((entry, game, fingerprint))

    room = settings.max_games_per_user() - game_service.count_games(session, user_id)
    if len(fresh) > room:
        raise BackupError(
            f"your library is limited to {settings.max_games_per_user()} games; "
            f"this backup would add {len(fresh)} but only {max(room, 0)} fit"
        )

    if fresh:
        game_service.store_games(
            session, user_id, [game for _, game, _ in fresh], source="restored from backup"
        )
    rows = {
        row.fingerprint: row
        for row in game_service.games_by_fingerprint(
            session, user_id, [fingerprint for _, _, fingerprint in fresh]
        )
    }

    mistake_count = 0
    attempt_count = 0
    for entry, _game, fingerprint in fresh:
        row = rows.get(fingerprint)
        if row is None:
            continue
        source = entry.get("source")
        if isinstance(source, str):
            row.source = game_service.fit(source, 255)
        raw_mistakes = entry.get("mistakes")
        if not isinstance(raw_mistakes, list):
            continue
        used_plies: set[int] = set()
        for raw in raw_mistakes:
            if mistake_count >= MAX_MISTAKES:
                break
            mistake = _mistake(raw)
            if mistake is None or mistake.ply in used_plies:
                continue
            used_plies.add(mistake.ply)
            mistake.user_id = user_id
            mistake.game_id = row.id
            session.add(mistake)
            session.flush()
            mistake_count += 1
            raw_attempts = raw.get("attempts") if isinstance(raw, dict) else None
            if not isinstance(raw_attempts, list):
                continue
            for raw_attempt in raw_attempts:
                if attempt_count >= MAX_ATTEMPTS:
                    break
                attempt = _build(PuzzleAttempt, raw_attempt, ATTEMPT_SKIP)
                if attempt is None:
                    continue
                attempt.user_id = user_id
                attempt.mistake_id = mistake.id
                session.add(attempt)
                attempt_count += 1

    profile_restored = False
    raw_profile = data.get("profile")
    has_profile = session.scalar(
        select(PlayerProfile.id).where(PlayerProfile.user_id == user_id).limit(1)
    )
    if has_profile is None and isinstance(raw_profile, dict) and fresh:
        profile = _build(PlayerProfile, raw_profile, PROFILE_SKIP)
        if profile is not None:
            profile.user_id = user_id
            session.add(profile)
            session.flush()
            patterns = raw_profile.get("patterns")
            if isinstance(patterns, list):
                for raw_pattern in patterns[:MAX_PATTERNS]:
                    pattern = _build(Pattern, raw_pattern, PATTERN_SKIP)
                    if pattern is not None:
                        pattern.profile_id = profile.id
                        session.add(pattern)
            profile_restored = True

    session.flush()
    return {
        "games_restored": len(fresh),
        "games_already_present": len(parsed) - len(fresh),
        "games_unreadable": invalid,
        "mistakes_restored": mistake_count,
        "attempts_restored": attempt_count,
        "profile_restored": profile_restored,
    }
