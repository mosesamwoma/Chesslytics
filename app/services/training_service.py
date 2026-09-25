from __future__ import annotations

import os
from typing import Optional

import chess
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.chess.engine import ChessEngine, SearchLimit, find_stockfish
from app.chess.evaluator import clamp_loss, win_percent
from app.database.models import Mistake, PuzzleAttempt
from app.services import analysis_service

DEFAULT_TOLERANCE_WINPCT = 5.0
WEAK_CATEGORY_MIN_ATTEMPTS = 3


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
            return None
        return move if move in board.legal_moves else None
    if mistake.best_move:
        try:
            return board.parse_san(mistake.best_move)
        except ValueError:
            return None
    return None


def attempts_for(session: Session, mistake_ids: list[int]) -> dict[int, dict]:
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
        .where(PuzzleAttempt.mistake_id.in_(mistake_ids))
        .group_by(PuzzleAttempt.mistake_id)
    ).all()
    return {
        mistake_id: {"attempts": int(total), "solved": int(correct)}
        for mistake_id, total, correct in rows
    }


def to_puzzle(mistake: Mistake, tally: Optional[dict] = None) -> Optional[dict]:
    board = board_for(mistake)
    if board is None:
        return None
    tally = tally or {}
    return {
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
    category: Optional[str] = None,
    severity: Optional[str] = None,
    player: Optional[str] = None,
):
    statement = select(Mistake).where(Mistake.fen.is_not(None))
    if category:
        statement = statement.where(Mistake.category == category)
    if severity:
        statement = statement.where(Mistake.severity == severity)
    if player:
        statement = statement.where(Mistake.player == player)
    return statement


def list_puzzles(
    session: Session,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    player: Optional[str] = None,
    unseen_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    tally = (
        select(
            PuzzleAttempt.mistake_id.label("mistake_id"),
            func.count(PuzzleAttempt.id).label("attempts"),
            func.coalesce(
                func.sum(case((PuzzleAttempt.correct.is_(True), 1), else_=0)), 0
            ).label("solved"),
        )
        .group_by(PuzzleAttempt.mistake_id)
        .subquery()
    )
    seen = func.coalesce(tally.c.attempts, 0)

    statement = puzzle_query(category, severity, player).outerjoin(
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

    puzzles = []
    for mistake, attempts, solved in rows:
        puzzle = to_puzzle(mistake, {"attempts": attempts, "solved": solved})
        if puzzle is not None:
            puzzles.append(puzzle)

    return puzzles, total


def get_mistake(session: Session, mistake_id: int) -> Optional[Mistake]:
    return session.get(Mistake, mistake_id)


def attempt_summary(session: Session, mistake_id: int) -> dict:
    return attempts_for(session, [mistake_id]).get(
        mistake_id, {"attempts": 0, "solved": 0}
    )


def grade(
    session: Session,
    mistake: Mistake,
    uci: str,
    player: Optional[str] = None,
    engine_path: Optional[str] = None,
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
            outcome = _grade_with_engine(
                mistake, board, after, engine_path, limit, notes
            )
            correct = outcome["correct"]
            verdict = outcome["verdict"]
            loss_vs_best = outcome["loss_vs_best"]
            graded_engine = outcome["engine"]
        except FileNotFoundError:
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
            mistake_id=mistake.id,
            player=player or mistake.player,
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
    result["attempts"] = attempt_summary(session, mistake.id)
    return result


def _grade_with_engine(
    mistake: Mistake,
    board: chess.Board,
    after: chess.Board,
    engine_path: Optional[str],
    limit: Optional[SearchLimit],
    notes: list[str],
) -> dict:
    search = limit or analysis_service.default_limit()
    entries = analysis_service.load_verify_cache()

    with ChessEngine(find_stockfish(engine_path), search) as engine:
        engine_name = engine.name
        cp_before = analysis_service.position_score(
            engine, board, entries, engine_name, search
        )
        cp_after = analysis_service.position_score(
            engine, after, entries, engine_name, search
        )

    analysis_service.save_verify_cache(entries)

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


def stats(session: Session, player: Optional[str] = None) -> dict:
    filters = [PuzzleAttempt.player == player] if player else []

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
        session.scalar(select(func.count(Mistake.id)).where(Mistake.fen.is_not(None))) or 0
    )

    return {
        "player": player,
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


def recent_attempts(session: Session, limit: int = 20, player: Optional[str] = None) -> list[PuzzleAttempt]:
    statement = select(PuzzleAttempt)
    if player:
        statement = statement.where(PuzzleAttempt.player == player)
    statement = statement.order_by(
        PuzzleAttempt.created_at.desc(), PuzzleAttempt.id.desc()
    ).limit(max(1, min(limit, 200)))
    return list(session.scalars(statement))
