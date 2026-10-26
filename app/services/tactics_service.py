from __future__ import annotations

import io
import logging
from typing import Optional

import chess.pgn
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.chess import openings
from app.chess.lines import THEME_ORDER
from app.chess.tactics import analyze_mistake, themes_text
from app.database.database import session_scope
from app.database.models import Game, Mistake

logger = logging.getLogger("chesslytics.tactics")

BATCH = 200


def valid_theme(value: Optional[str]) -> Optional[str]:
    return value if value in THEME_ORDER else None


def apply_tactics(mistake: Mistake) -> None:
    facts = dict(mistake.facts or {})
    line = facts.get("best_line") or []
    result = analyze_mistake(
        mistake.fen or "",
        mistake.played_uci,
        [item for item in line if isinstance(item, str)],
        mistake.best_move_uci,
        facts,
    )
    facts["tactics"] = result
    mistake.facts = facts
    mistake.themes_text = themes_text(result["themes"])


def missing_filter():
    return or_(
        Mistake.facts.is_(None),
        ~cast(Mistake.facts, String).like('%"tactics"%'),
    )


def retag(session: Session, limit: int = BATCH) -> int:
    rows = list(
        session.scalars(
            select(Mistake).where(Mistake.fen.is_not(None), missing_filter()).limit(limit)
        )
    )
    for row in rows:
        try:
            apply_tactics(row)
        except Exception:
            logger.exception("could not analyse the tactics of mistake %s", row.id)
            facts = dict(row.facts or {})
            facts["tactics"] = {"heuristic": True, "themes": [], "failed": True}
            row.facts = facts
    session.flush()
    return len(rows)


def retag_all(max_rows: int = 20000) -> int:
    done = 0
    while done < max_rows:
        with session_scope() as session:
            count = retag(session)
        done += count
        if count < BATCH:
            break
    return done


def fill_openings(session: Session, limit: int = 500) -> int:
    rows = list(
        session.scalars(
            select(Game)
            .where(Game.pgn.is_not(None), or_(Game.opening.is_(None), Game.opening == ""))
            .limit(limit)
        )
    )
    changed = 0
    for game in rows:
        parsed = chess.pgn.read_game(io.StringIO(game.pgn or ""))
        if parsed is None:
            continue
        ucis = [move.uci() for move in parsed.mainline_moves()]
        found = openings.classify_moves(ucis)
        if found is None:
            game.opening = "-"
            continue
        eco, name, _ply = found
        game.opening = name[:255]
        if not game.eco:
            game.eco = eco
        changed += 1
    session.flush()
    return changed


def fill_openings_all() -> int:
    total = 0
    while True:
        with session_scope() as session:
            count = fill_openings(session)
            remaining = session.scalar(
                select(func.count(Game.id)).where(
                    Game.pgn.is_not(None), or_(Game.opening.is_(None), Game.opening == "")
                )
            )
        total += count
        if not remaining or count == 0:
            break
    return total


def theme_counts(session: Session, user_id: int) -> list[dict]:
    counts: dict[str, int] = {}
    for text in session.scalars(
        select(Mistake.themes_text).where(
            Mistake.user_id == user_id, Mistake.themes_text.is_not(None)
        )
    ):
        for theme in (text or "").strip("|").split("|"):
            if theme:
                counts[theme] = counts.get(theme, 0) + 1
    order = {theme: index for index, theme in enumerate(THEME_ORDER)}
    return [
        {"theme": theme, "count": count}
        for theme, count in sorted(counts.items(), key=lambda item: (-item[1], order.get(item[0], 99)))
    ]


def run_background() -> None:
    try:
        openings.known(chess.Board())
        retag_all()
        fill_openings_all()
    except Exception:
        logger.exception("background tactics backfill failed")
