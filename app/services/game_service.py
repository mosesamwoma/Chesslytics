from __future__ import annotations

from pathlib import Path
from typing import Optional

import chess.pgn
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import settings
from app.chess.pgn_parser import game_metadata, parse_pgn
from app.database.models import Game, Mistake, Move

ALLOWED_SUFFIXES = {".pgn", ".txt"}
EMPTY_HEADERS = {"", "?", "-"}


class QuotaExceeded(ValueError):
    pass


def fit(value: Optional[str], length: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).replace("\x00", "")
    return text[:length]


def _clean(value: Optional[str], length: int = 255) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text in EMPTY_HEADERS:
        return None
    return fit(text, length)


def _int_or_none(value: Optional[str]) -> Optional[int]:
    text = _clean(value)
    if text is None:
        return None
    try:
        number = int(text)
    except ValueError:
        return None
    if number < 0 or number > 10000:
        return None
    return number


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload.pgn").name
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in "._- ")
    cleaned = cleaned.strip().lstrip(".") or "upload"
    if Path(cleaned).suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError("only .pgn or .txt files are accepted")
    return cleaned[:200]


def pgn_text(game: chess.pgn.Game) -> Optional[str]:
    try:
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        text = game.accept(exporter)
    except Exception:
        return None
    return text or None


def game_row(
    metadata: dict,
    user_id: Optional[int] = None,
    source: Optional[str] = None,
    pgn: Optional[str] = None,
) -> Game:
    return Game(
        user_id=user_id,
        fingerprint=metadata["fingerprint"],
        white=fit(metadata.get("white") or "", 128),
        black=fit(metadata.get("black") or "", 128),
        result=fit(metadata.get("result") or "", 16),
        date=_clean(metadata.get("date"), 32),
        event=_clean(metadata.get("event")),
        site=_clean(metadata.get("site")),
        eco=_clean(metadata.get("eco"), 8),
        opening=_clean(metadata.get("opening")),
        variation=_clean(metadata.get("variation")),
        time_control=_clean(metadata.get("time_control"), 32),
        white_elo=_int_or_none(metadata.get("white_elo")),
        black_elo=_int_or_none(metadata.get("black_elo")),
        source=fit(source, 255),
        pgn=pgn,
    )


def plies_in(game: chess.pgn.Game) -> int:
    return sum(1 for _ in game.mainline_moves())


def count_games(session: Session, user_id: int) -> int:
    return int(
        session.scalar(select(func.count(Game.id)).where(Game.user_id == user_id)) or 0
    )


def store_games(
    session: Session,
    user_id: int,
    games: list[chess.pgn.Game],
    source: Optional[str] = None,
    quota: Optional[int] = None,
) -> dict:
    stored = 0
    skipped = 0
    fingerprints: list[str] = []
    metas = [game_metadata(game) for game in games]
    wanted = list({meta["fingerprint"] for meta in metas})

    known: set[str] = set()
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        known.update(
            session.scalars(
                select(Game.fingerprint).where(
                    Game.user_id == user_id, Game.fingerprint.in_(chunk)
                )
            )
        )

    seen: set[str] = set()
    fresh: list[tuple[dict, chess.pgn.Game]] = []
    for meta, game in zip(metas, games):
        fingerprint = meta["fingerprint"]
        fingerprints.append(fingerprint)
        if fingerprint in known or fingerprint in seen:
            skipped += 1
            continue
        seen.add(fingerprint)
        fresh.append((meta, game))

    if quota is not None and fresh:
        room = quota - count_games(session, user_id)
        if len(fresh) > room:
            raise QuotaExceeded(
                f"your library is limited to {quota} games; "
                f"you can add {max(room, 0)} more (delete old games to free space)"
            )

    for meta, game in fresh:
        session.add(game_row(meta, user_id, source, pgn_text(game)))
        stored += 1

    session.flush()
    return {
        "stored": stored,
        "skipped": skipped,
        "fingerprints": list(dict.fromkeys(fingerprints)),
    }


def import_pgn(
    session: Session,
    user_id: int,
    text: str,
    source: Optional[str] = None,
    quota: Optional[int] = None,
) -> dict:
    games, errors = parse_pgn(text)
    limit = settings.max_games_per_upload()
    if len(games) > limit:
        raise ValueError(
            f"too many games in one file ({len(games)}); the limit is {limit} per upload"
        )
    longest = settings.max_plies_per_game()
    usable: list[chess.pgn.Game] = []
    for index, game in enumerate(games, start=1):
        if plies_in(game) > longest:
            errors.append(f"game #{index}: skipped (longer than {longest} half-moves)")
            continue
        usable.append(game)

    result = store_games(session, user_id, usable, source, quota)
    result["parsed"] = len(usable)
    result["errors"] = errors[:50]
    return result


def _counts(session: Session, ids: list[int]) -> tuple[dict, dict]:
    if not ids:
        return {}, {}
    moves = dict(
        session.execute(
            select(Move.game_id, func.count(Move.id))
            .where(Move.game_id.in_(ids))
            .group_by(Move.game_id)
        ).all()
    )
    mistakes = dict(
        session.execute(
            select(Mistake.game_id, func.count(Mistake.id))
            .where(Mistake.game_id.in_(ids))
            .group_by(Mistake.game_id)
        ).all()
    )
    return moves, mistakes


def list_games(session: Session, user_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
    statement = (
        select(Game)
        .where(Game.user_id == user_id)
        .order_by(Game.date.desc().nullslast(), Game.id.desc())
        .limit(max(1, min(limit, 500)))
        .offset(max(0, offset))
    )
    rows = list(session.scalars(statement))
    moves, mistakes = _counts(session, [row.id for row in rows])
    return [
        game_summary(row, int(mistakes.get(row.id, 0)), int(moves.get(row.id, 0)))
        for row in rows
    ]


def get_game(session: Session, user_id: int, game_id: int) -> Optional[Game]:
    return session.scalar(select(Game).where(Game.id == game_id, Game.user_id == user_id))


def games_by_fingerprint(session: Session, user_id: int, fingerprints: list[str]) -> list[Game]:
    rows: list[Game] = []
    for start in range(0, len(fingerprints), 500):
        chunk = fingerprints[start : start + 500]
        rows.extend(
            session.scalars(
                select(Game).where(Game.user_id == user_id, Game.fingerprint.in_(chunk))
            )
        )
    return rows


def delete_game(session: Session, user_id: int, game_id: int) -> bool:
    game = get_game(session, user_id, game_id)
    if game is None:
        return False
    session.delete(game)
    session.flush()
    return True


def store_moves(session: Session, game: Game, moves: list[dict]) -> int:
    session.execute(delete(Move).where(Move.game_id == game.id))
    session.flush()
    for move in moves:
        session.add(_move_row(game.id, move))
    session.flush()
    return len(moves)


def _move_row(game_id: int, move: dict) -> Move:
    return Move(
        game_id=game_id,
        ply=move.get("ply") or 0,
        move_number=move.get("move_number") or 0,
        color=move.get("color") or "white",
        san=move.get("san"),
        uci=move.get("uci"),
        fen_before=move.get("fen_before"),
        fen_after=move.get("fen_after"),
        eval_before_cp=move.get("eval_before_cp"),
        eval_after_cp=move.get("eval_after_cp"),
        eval_before_mate=move.get("eval_before_mate"),
        eval_after_mate=move.get("eval_after_mate"),
        loss_cp=move.get("loss_cp"),
        winpct_before=move.get("winpct_before"),
        winpct_after=move.get("winpct_after"),
        best_move_uci=move.get("best_move_uci"),
        best_move_san=move.get("best_move_san"),
        depth_reached=move.get("depth_reached"),
        phase=move.get("phase"),
        clock_before=move.get("clock_before"),
        clock_after=move.get("clock_after"),
        material_before=move.get("material_before"),
        material_after=move.get("material_after"),
        is_capture=bool(move.get("is_capture")),
        is_check=bool(move.get("is_check")),
        is_mate=bool(move.get("is_mate")),
        is_promotion=bool(move.get("is_promotion")),
        is_castling=bool(move.get("is_castling")),
        is_en_passant=bool(move.get("is_en_passant")),
        best_move_was_capture=bool(move.get("best_move_was_capture")),
        best_move_was_check=bool(move.get("best_move_was_check")),
        best_move_was_mate=bool(move.get("best_move_was_mate")),
        hanging_after=move.get("hanging_after"),
        king_safety_after=move.get("king_safety_after"),
        error=move.get("error"),
    )


def game_summary(
    game: Game, mistake_count: Optional[int] = None, move_count: Optional[int] = None
) -> dict:
    return {
        "id": game.id,
        "fingerprint": game.fingerprint,
        "white": game.white,
        "black": game.black,
        "result": game.result,
        "date": game.date,
        "event": game.event,
        "eco": game.eco,
        "opening": game.opening,
        "variation": game.variation,
        "time_control": game.time_control,
        "white_elo": game.white_elo,
        "black_elo": game.black_elo,
        "source": game.source,
        "analyzed": game.analyzed_at is not None,
        "analyzed_at": game.analyzed_at.isoformat() if game.analyzed_at else None,
        "analyzed_depth": game.analyzed_depth,
        "move_count": move_count if move_count is not None else len(game.moves or []),
        "mistake_count": mistake_count if mistake_count is not None else len(game.mistakes or []),
    }


def move_to_dict(move: Move) -> dict:
    return {
        "ply": move.ply,
        "move_number": move.move_number,
        "color": move.color,
        "san": move.san,
        "uci": move.uci,
        "fen_before": move.fen_before,
        "fen_after": move.fen_after,
        "eval_before_cp": move.eval_before_cp,
        "eval_after_cp": move.eval_after_cp,
        "eval_before_mate": move.eval_before_mate,
        "eval_after_mate": move.eval_after_mate,
        "loss_cp": move.loss_cp,
        "winpct_before": move.winpct_before,
        "winpct_after": move.winpct_after,
        "best_move_uci": move.best_move_uci,
        "best_move_san": move.best_move_san,
        "depth_reached": move.depth_reached,
        "phase": move.phase,
        "clock_before": move.clock_before,
        "clock_after": move.clock_after,
        "material_before": move.material_before,
        "material_after": move.material_after,
        "is_capture": move.is_capture,
        "is_check": move.is_check,
        "is_mate": move.is_mate,
        "is_promotion": move.is_promotion,
        "is_castling": move.is_castling,
        "is_en_passant": move.is_en_passant,
        "best_move_was_capture": move.best_move_was_capture,
        "best_move_was_check": move.best_move_was_check,
        "best_move_was_mate": move.best_move_was_mate,
        "hanging_after": move.hanging_after,
        "king_safety_after": move.king_safety_after,
        "error": move.error,
    }


def mistake_to_dict(mistake: Mistake) -> dict:
    return {
        "id": mistake.id,
        "game_id": mistake.game_id,
        "ply": mistake.ply,
        "move_number": mistake.move_number,
        "color": mistake.color,
        "player": mistake.player,
        "opponent": mistake.opponent,
        "played_move": mistake.played_move,
        "played_uci": mistake.played_uci,
        "best_move": mistake.best_move,
        "best_move_uci": mistake.best_move_uci,
        "fen": mistake.fen,
        "fen_after": mistake.fen_after,
        "eval_before": mistake.eval_before,
        "eval_after": mistake.eval_after,
        "loss": mistake.loss,
        "loss_cp": mistake.loss_cp,
        "winpct_before": mistake.winpct_before,
        "winpct_after": mistake.winpct_after,
        "severity": mistake.severity,
        "category": mistake.category,
        "category_basis": mistake.category_basis,
        "phase": mistake.phase,
        "opening": mistake.opening,
        "in_time_pressure": mistake.in_time_pressure,
        "time_remaining": mistake.time_remaining,
        "game_decided": mistake.game_decided,
        "in_book": mistake.in_book,
        "book_move": mistake.book_move,
        "verified_by": mistake.verified_by,
        "verified_loss": mistake.verified_loss,
        "agreed": mistake.agreed,
        "facts": mistake.facts,
    }


def game_with_moves(game: Game) -> dict:
    detail = game_summary(game)
    moves = sorted(game.moves or [], key=lambda move: move.ply)
    detail["moves"] = [move_to_dict(move) for move in moves]
    return detail


def game_detail(game: Game) -> dict:
    detail = game_with_moves(game)
    mistakes = sorted(game.mistakes or [], key=lambda item: item.ply)
    detail["mistakes"] = [mistake_to_dict(item) for item in mistakes]
    return detail
