from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import chess
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import settings
from app.chess.engine import ChessEngine, SearchLimit, find_stockfish
from app.chess.evaluator import clamp_loss, win_percent
from app.database.models import Mistake, PuzzleAttempt, utcnow
from app.services import analysis_service

DEFAULT_TOLERANCE_WINPCT = 5.0
WEAK_CATEGORY_MIN_ATTEMPTS = 3
GRADING_WAIT_SECONDS = 15.0
REVIEW_INTERVAL_HOURS = (0.25, 24.0, 72.0, 168.0, 336.0, 720.0)
MAX_BOX = len(REVIEW_INTERVAL_HOURS) - 1
PRACTICE_MODES = ("all", "queue", "due", "new")

_grading_slots = threading.BoundedSemaphore(settings.max_concurrent_grading())


class EngineBusy(RuntimeError):
    pass


@contextmanager
def grading_slot():
    if not _grading_slots.acquire(timeout=GRADING_WAIT_SECONDS):
        raise EngineBusy("the engine is busy right now; please try again in a moment")
    try:
        yield
    finally:
        _grading_slots.release()


def tolerance() -> float:
    raw = os.environ.get("PUZZLE_TOLERANCE")
    if not raw:
        return DEFAULT_TOLERANCE_WINPCT
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TOLERANCE_WINPCT


def board_for(mistake: Mistake) -> Optional[chess.Board]:
    if not mistake.fen:
        return None
    try:
        return chess.Board(mistake.fen)
    except ValueError:
        return None


def best_move(board: chess.Board, mistake: Mistake) -> Optional[chess.Move]:
    if mistake.best_move_uci:
        try:
            move = chess.Move.from_uci(mistake.best_move_uci)
        except ValueError:
            move = None
        if move is not None and move in board.legal_moves:
            return move
    if mistake.best_move:
        try:
            return board.parse_san(mistake.best_move)
        except ValueError:
            return None
    return None


def attempts_for(session: Session, user_id: int, mistake_ids: list[int]) -> dict[int, dict]:
    if not mistake_ids:
        return {}
    rows = session.execute(
        select(
            PuzzleAttempt.mistake_id,
            func.count(PuzzleAttempt.id),
            func.coalesce(
                func.sum(case((PuzzleAttempt.correct.is_(True), 1), else_=0)), 0
            ),
        )
        .where(PuzzleAttempt.user_id == user_id, PuzzleAttempt.mistake_id.in_(mistake_ids))
        .group_by(PuzzleAttempt.mistake_id)
    ).all()
    return {
        mistake_id: {"attempts": int(total), "solved": int(correct)}
        for mistake_id, total, correct in rows
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _fold_attempts(rows) -> dict[int, dict]:
    states: dict[int, dict] = {}
    for mistake_id, correct, created_at in rows:
        state = states.setdefault(
            mistake_id, {"box": 0, "attempts": 0, "solved": 0, "last": None}
        )
        state["attempts"] += 1
        if correct:
            state["solved"] += 1
            state["box"] = min(state["box"] + 1, MAX_BOX)
        else:
            state["box"] = 0
        state["last"] = _aware(created_at)
    now = utcnow()
    for state in states.values():
        due_at = state["last"] + timedelta(hours=REVIEW_INTERVAL_HOURS[state["box"]])
        state["due_at"] = due_at
        state["due"] = due_at <= now
    return states


def review_states(
    session: Session, user_id: int, mistake_ids: Optional[list[int]] = None
) -> dict[int, dict]:
    statement = select(
        PuzzleAttempt.mistake_id, PuzzleAttempt.correct, PuzzleAttempt.created_at
    ).where(PuzzleAttempt.user_id == user_id)
    if mistake_ids is not None:
        if not mistake_ids:
            return {}
        statement = statement.where(PuzzleAttempt.mistake_id.in_(mistake_ids))
    rows = session.execute(
        statement.order_by(PuzzleAttempt.created_at, PuzzleAttempt.id)
    ).all()
    return _fold_attempts(rows)


def review_summary(state: Optional[dict]) -> dict:
    if not state:
        return {"status": "new", "box": 0, "due": False, "due_at": None}
    if state["due"]:
        status = "due"
    elif state["box"] >= MAX_BOX:
        status = "mastered"
    else:
        status = "learning"
    return {
        "status": status,
        "box": state["box"],
        "due": bool(state["due"]),
        "due_at": state["due_at"].isoformat(),
    }


def to_puzzle(
    mistake: Mistake, tally: Optional[dict] = None, state: Optional[dict] = None
) -> Optional[dict]:
    board = board_for(mistake)
    if board is None:
        return None
    tally = tally or {}
    return {
        "review": review_summary(state),
        "id": mistake.id,
        "game_id": mistake.game_id,
        "fen": mistake.fen,
        "orientation": mistake.color,
        "legal_moves": sorted(move.uci() for move in board.legal_moves),
        "move_number": mistake.move_number,
        "ply": mistake.ply,
        "color": mistake.color,
        "player": mistake.player,
        "opponent": mistake.opponent,
        "phase": mistake.phase,
        "opening": mistake.opening,
        "severity": mistake.severity,
        "category": mistake.category,
        "loss": mistake.loss,
        "in_book": mistake.in_book,
        "attempts": tally.get("attempts", 0),
        "solved": tally.get("solved", 0) > 0,
    }


def solution(mistake: Mistake) -> dict:
    board = board_for(mistake)
    move = best_move(board, mistake) if board is not None else None
    return {
        "id": mistake.id,
        "fen": mistake.fen,
        "best_move": mistake.best_move,
        "best_move_uci": move.uci() if move is not None else mistake.best_move_uci,
        "best_move_san": board.san(move) if (board is not None and move is not None) else mistake.best_move,
        "played_move": mistake.played_move,
        "played_uci": mistake.played_uci,
        "loss": mistake.loss,
        "severity": mistake.severity,
        "category": mistake.category,
        "category_basis": mistake.category_basis,
        "phase": mistake.phase,
        "opening": mistake.opening,
        "in_book": mistake.in_book,
        "book_move": mistake.book_move,
        "facts": mistake.facts,
    }


def puzzle_query(
    user_id: int,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    player: Optional[str] = None,
):
    statement = select(Mistake).where(Mistake.user_id == user_id, Mistake.fen.is_not(None))
    if category:
        statement = statement.where(Mistake.category == category)
    if severity:
        statement = statement.where(Mistake.severity == severity)
    if player:
        statement = statement.where(Mistake.player == player)
    return statement


def _practice_order(
    session: Session,
    user_id: int,
    category: Optional[str],
    severity: Optional[str],
    player: Optional[str],
    practice: str,
) -> tuple[list[int], dict[int, dict]]:
    candidates = session.execute(
        puzzle_query(user_id, category, severity, player)
        .with_only_columns(Mistake.id, Mistake.loss_cp)
        .order_by(Mistake.loss_cp.desc(), Mistake.id)
    ).all()
    states = review_states(session, user_id, [row[0] for row in candidates])

    due: list[tuple[datetime, int]] = []
    waiting: list[tuple[datetime, int]] = []
    fresh: list[int] = []
    for mistake_id, _loss in candidates:
        state = states.get(mistake_id)
        if state is None:
            fresh.append(mistake_id)
        elif state["due"]:
            due.append((state["due_at"], mistake_id))
        else:
            waiting.append((state["due_at"], mistake_id))
    due.sort()
    waiting.sort()

    if practice == "due":
        ordered = [mistake_id for _, mistake_id in due]
    elif practice == "new":
        ordered = fresh
    else:
        ordered = (
            [mistake_id for _, mistake_id in due]
            + fresh
            + [mistake_id for _, mistake_id in waiting]
        )
    return ordered, states


def _list_by_practice(
    session: Session,
    user_id: int,
    category: Optional[str],
    severity: Optional[str],
    player: Optional[str],
    practice: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    ordered, states = _practice_order(session, user_id, category, severity, player, practice)
    page = ordered[max(0, offset) : max(0, offset) + max(1, min(limit, 200))]
    if not page:
        return [], len(ordered)
    rows = {
        mistake.id: mistake
        for mistake in session.scalars(select(Mistake).where(Mistake.id.in_(page)))
    }
    puzzles = []
    for mistake_id in page:
        mistake = rows.get(mistake_id)
        if mistake is None:
            continue
        state = states.get(mistake_id)
        tally = {
            "attempts": state["attempts"] if state else 0,
            "solved": state["solved"] if state else 0,
        }
        puzzle = to_puzzle(mistake, tally, state)
        if puzzle is not None:
            puzzles.append(puzzle)
    return puzzles, len(ordered)


def list_puzzles(
    session: Session,
    user_id: int,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    player: Optional[str] = None,
    unseen_only: bool = False,
    limit: int = 20,
    offset: int = 0,
    practice: str = "all",
) -> tuple[list[dict], int]:
    if unseen_only and practice == "all":
        practice = "new"
    if practice != "all":
        return _list_by_practice(
            session, user_id, category, severity, player, practice, limit, offset
        )
    tally = (
        select(
            PuzzleAttempt.mistake_id.label("mistake_id"),
            func.count(PuzzleAttempt.id).label("attempts"),
            func.coalesce(
                func.sum(case((PuzzleAttempt.correct.is_(True), 1), else_=0)), 0
            ).label("solved"),
        )
        .where(PuzzleAttempt.user_id == user_id)
        .group_by(PuzzleAttempt.mistake_id)
        .subquery()
    )
    seen = func.coalesce(tally.c.attempts, 0)

    statement = puzzle_query(user_id, category, severity, player).outerjoin(
        tally, tally.c.mistake_id == Mistake.id
    )
    if unseen_only:
        statement = statement.where(seen == 0)

    total = int(
        session.scalar(
            select(func.count()).select_from(statement.subquery())
        )
        or 0
    )

    rows = session.execute(
        statement.add_columns(seen, func.coalesce(tally.c.solved, 0))
        .order_by(seen.asc(), Mistake.loss_cp.desc(), Mistake.id)
        .limit(max(1, min(limit, 200)))
        .offset(max(0, offset))
    ).all()

    states = review_states(session, user_id, [mistake.id for mistake, _, _ in rows])
    puzzles = []
    for mistake, attempts, solved in rows:
        puzzle = to_puzzle(
            mistake, {"attempts": attempts, "solved": solved}, states.get(mistake.id)
        )
        if puzzle is not None:
            puzzles.append(puzzle)

    return puzzles, total


def get_mistake(session: Session, user_id: int, mistake_id: int) -> Optional[Mistake]:
    return session.scalar(
        select(Mistake).where(Mistake.id == mistake_id, Mistake.user_id == user_id)
    )


def attempt_summary(session: Session, user_id: int, mistake_id: int) -> dict:
    return attempts_for(session, user_id, [mistake_id]).get(
        mistake_id, {"attempts": 0, "solved": 0}
    )


def grade(
    session: Session,
    user_id: int,
    mistake: Mistake,
    uci: str,
    limit: Optional[SearchLimit] = None,
) -> dict:
    board = board_for(mistake)
    if board is None:
        raise ValueError("this mistake has no stored position to replay")

    candidate = uci.strip().lower()
    try:
        played = chess.Move.from_uci(candidate)
    except ValueError as exc:
        raise ValueError(f"{uci!r} is not a move in UCI form") from exc
    if played not in board.legal_moves:
        raise ValueError(f"{candidate} is not legal in this position")

    played_san = board.san(played)
    reference = best_move(board, mistake)
    reference_uci = reference.uci() if reference is not None else None

    after = board.copy(stack=False)
    after.push(played)
    fen_after = after.fen()

    graded_by = "stored"
    loss_vs_best = 0.0
    graded_engine: Optional[str] = None
    notes: list[str] = []

    if reference_uci is not None and played.uci() == reference_uci:
        correct, verdict = True, "best"
    elif after.is_checkmate():
        correct, verdict = True, "mate"
    elif after.is_game_over():
        correct, verdict = False, "draw"
        notes.append("the move ends the game as a draw")
    else:
        graded_by = "engine"
        try:
            outcome = _grade_with_engine(board, after, limit, notes)
            correct = outcome["correct"]
            verdict = outcome["verdict"]
            loss_vs_best = outcome["loss_vs_best"]
            graded_engine = outcome["engine"]
        except (FileNotFoundError, OSError):
            graded_by = "exact_match"
            correct, verdict = False, "not_best"
            notes.append(
                "no engine was available to weigh alternatives, so only the stored best "
                "move counted as correct"
            )

    result = {
        "puzzle_id": mistake.id,
        "correct": correct,
        "verdict": verdict,
        "graded_by": graded_by,
        "played_uci": played.uci(),
        "played_san": played_san,
        "best_move": mistake.best_move,
        "best_move_uci": reference_uci,
        "loss_vs_best": loss_vs_best,
        "tolerance_winpct": tolerance(),
        "fen_after": fen_after,
        "category": mistake.category,
        "category_basis": mistake.category_basis,
        "severity": mistake.severity,
        "notes": notes,
    }

    session.add(
        PuzzleAttempt(
            user_id=user_id,
            mistake_id=mistake.id,
            player=mistake.player,
            played_uci=played.uci(),
            played_san=played_san,
            correct=bool(correct),
            verdict=verdict,
            loss_vs_best=loss_vs_best,
            graded_by=graded_by,
            engine=graded_engine,
        )
    )
    session.flush()
    result["attempts"] = attempt_summary(session, user_id, mistake.id)
    result["review"] = review_summary(
        review_states(session, user_id, [mistake.id]).get(mistake.id)
    )
    return result


def _grade_with_engine(
    board: chess.Board,
    after: chess.Board,
    limit: Optional[SearchLimit],
    notes: list[str],
) -> dict:
    search = limit or analysis_service.default_limit()

    with grading_slot():
        with ChessEngine(find_stockfish(), search) as engine:
            engine_name = engine.name
            cp_before = analysis_service.position_score(engine, board, {}, engine_name, search)
            cp_after = analysis_service.position_score(engine, after, {}, engine_name, search)

    swing = win_percent(cp_before) - win_percent(-cp_after)
    loss_vs_best = round(max(clamp_loss(cp_before + cp_after), 0) / 100.0, 2)

    if swing <= tolerance():
        return {
            "correct": True,
            "verdict": "equal_to_best",
            "loss_vs_best": loss_vs_best,
            "engine": engine_name,
        }

    notes.append(
        f"the engine weighed this move {swing:.1f} win% below the best continuation"
    )
    return {
        "correct": False,
        "verdict": "worse_than_best",
        "loss_vs_best": loss_vs_best,
        "engine": engine_name,
    }


def stats(session: Session, user_id: int) -> dict:
    filters = [PuzzleAttempt.user_id == user_id]

    total = int(
        session.scalar(select(func.count(PuzzleAttempt.id)).where(*filters)) or 0
    )
    correct = int(
        session.scalar(
            select(func.count(PuzzleAttempt.id)).where(
                *filters, PuzzleAttempt.correct.is_(True)
            )
        )
        or 0
    )

    rows = session.execute(
        select(
            Mistake.category,
            func.count(PuzzleAttempt.id),
            func.coalesce(
                func.sum(case((PuzzleAttempt.correct.is_(True), 1), else_=0)), 0
            ),
        )
        .join(Mistake, Mistake.id == PuzzleAttempt.mistake_id)
        .where(*filters)
        .group_by(Mistake.category)
        .order_by(func.count(PuzzleAttempt.id).desc())
    ).all()

    by_category = [
        {
            "category": category,
            "attempts": int(attempts),
            "correct": int(right),
            "accuracy": round(100.0 * right / attempts, 1) if attempts else 0.0,
        }
        for category, attempts, right in rows
    ]

    eligible = [
        row for row in by_category if row["attempts"] >= WEAK_CATEGORY_MIN_ATTEMPTS
    ]
    weakest = min(eligible, key=lambda row: row["accuracy"]) if eligible else None

    puzzles = int(
        session.scalar(
            select(func.count(Mistake.id)).where(
                Mistake.user_id == user_id, Mistake.fen.is_not(None)
            )
        )
        or 0
    )

    available = set(
        session.scalars(
            select(Mistake.id).where(Mistake.user_id == user_id, Mistake.fen.is_not(None))
        )
    )
    states = {
        mistake_id: state
        for mistake_id, state in review_states(session, user_id).items()
        if mistake_id in available
    }
    due_now = sum(1 for state in states.values() if state["due"])
    mastered = sum(
        1 for state in states.values() if not state["due"] and state["box"] >= MAX_BOX
    )

    return {
        "due_now": due_now,
        "new_puzzles": len(available) - len(states),
        "mastered": mastered,
        "attempts": total,
        "correct": correct,
        "accuracy": round(100.0 * correct / total, 1) if total else 0.0,
        "puzzles_available": puzzles,
        "puzzles_attempted": int(
            session.scalar(
                select(func.count(func.distinct(PuzzleAttempt.mistake_id))).where(*filters)
            )
            or 0
        ),
        "by_category": by_category,
        "weakest_category": weakest,
        "tolerance_winpct": tolerance(),
    }


def attempt_to_dict(attempt: PuzzleAttempt) -> dict:
    return {
        "id": attempt.id,
        "mistake_id": attempt.mistake_id,
        "player": attempt.player,
        "played_uci": attempt.played_uci,
        "played_san": attempt.played_san,
        "correct": attempt.correct,
        "verdict": attempt.verdict,
        "loss_vs_best": attempt.loss_vs_best,
        "graded_by": attempt.graded_by,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
    }


def recent_attempts(session: Session, user_id: int, limit: int = 20) -> list[PuzzleAttempt]:
    statement = select(PuzzleAttempt).where(PuzzleAttempt.user_id == user_id)
    statement = statement.order_by(
        PuzzleAttempt.created_at.desc(), PuzzleAttempt.id.desc()
    ).limit(max(1, min(limit, 200)))
    return list(session.scalars(statement))
