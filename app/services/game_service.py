from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional

import chess.pgn
from sqlalchemy import String, cast, delete, false, func, or_, select
from sqlalchemy.orm import Session

from app import settings
from app.chess.pgn_parser import game_metadata, parse_pgn
from app.database.models import Game, Mistake, Move

ALLOWED_SUFFIXES = {".pgn", ".txt"}
EMPTY_HEADERS = {"", "?", "-"}
MAX_NOTES_CHARS = 2000
MAX_TAGS = 10
MAX_TAG_CHARS = 24
TAG_PATTERN = re.compile(r"^[\w][\w \-]*$")
RAW_RESULTS = {"1-0", "0-1", "1/2-1/2", "*"}
PLAYER_RESULTS = {"won", "lost", "drawn"}
SORTS = {"date_desc", "date_asc", "mistakes_desc", "opening_asc"}


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
    return import_games(session, user_id, games, errors, source, quota)


def import_games(
    session: Session,
    user_id: int,
    games: list[chess.pgn.Game],
    errors: list[str],
    source: Optional[str] = None,
    quota: Optional[int] = None,
) -> dict:
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


def move_accuracy(win_before: float, win_after: float) -> float:
    drop = max(win_before - win_after, 0.0)
    value = 103.1668 * math.exp(-0.04354 * drop) - 3.1669
    return max(0.0, min(100.0, value))


def _mean_accuracy(totals: dict[str, list[float]]) -> dict:
    return {
        color: (round(sum(values) / len(values), 1) if values else None)
        for color, values in totals.items()
    }


def accuracy_by_game(session: Session, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    totals: dict[int, dict[str, list[float]]] = {}
    rows = session.execute(
        select(Move.game_id, Move.color, Move.winpct_before, Move.winpct_after).where(
            Move.game_id.in_(ids),
            Move.winpct_before.is_not(None),
            Move.winpct_after.is_not(None),
        )
    ).all()
    for game_id, color, before, after in rows:
        bucket = totals.setdefault(game_id, {"white": [], "black": []})
        if color in bucket:
            bucket[color].append(move_accuracy(before, after))
    return {game_id: _mean_accuracy(bucket) for game_id, bucket in totals.items()}


def accuracy_from_moves(moves: list) -> dict:
    totals: dict[str, list[float]] = {"white": [], "black": []}
    for move in moves:
        if move.winpct_before is None or move.winpct_after is None:
            continue
        if move.color in totals:
            totals[move.color].append(move_accuracy(move.winpct_before, move.winpct_after))
    return _mean_accuracy(totals)


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filters(
    user_id: int,
    q: Optional[str],
    result: Optional[str],
    analyzed: Optional[bool],
    opening: Optional[str],
    color: Optional[str],
    player: Optional[str],
    tag: Optional[str],
) -> list:
    clauses: list = [Game.user_id == user_id]
    wanted = (player or "").strip().lower()
    white_is = func.lower(Game.white) == wanted
    black_is = func.lower(Game.black) == wanted

    if q:
        pattern = _like(q.strip())
        clauses.append(
            or_(
                Game.white.ilike(pattern, escape="\\"),
                Game.black.ilike(pattern, escape="\\"),
                Game.opening.ilike(pattern, escape="\\"),
                Game.event.ilike(pattern, escape="\\"),
            )
        )
    if result:
        if result in RAW_RESULTS:
            clauses.append(Game.result == result)
        elif result in PLAYER_RESULTS:
            if not wanted:
                clauses.append(false())
            elif result == "won":
                clauses.append(or_(white_is & (Game.result == "1-0"), black_is & (Game.result == "0-1")))
            elif result == "lost":
                clauses.append(or_(white_is & (Game.result == "0-1"), black_is & (Game.result == "1-0")))
            else:
                clauses.append((white_is | black_is) & (Game.result == "1/2-1/2"))
    if analyzed is True:
        clauses.append(Game.analyzed_at.is_not(None))
    elif analyzed is False:
        clauses.append(Game.analyzed_at.is_(None))
    if opening:
        clauses.append(Game.opening.ilike(_like(opening.strip()), escape="\\"))
    if color in ("white", "black"):
        if not wanted:
            clauses.append(false())
        else:
            clauses.append(white_is if color == "white" else black_is)
    if tag:
        wanted_tag = _like(tag.strip().lower())[1:-1]
        clauses.append(
            cast(Game.tags, String).like(f'%"{wanted_tag}"%', escape="\\")
        )
    return clauses


def count_games_filtered(
    session: Session,
    user_id: int,
    q: Optional[str] = None,
    result: Optional[str] = None,
    analyzed: Optional[bool] = None,
    opening: Optional[str] = None,
    color: Optional[str] = None,
    player: Optional[str] = None,
    tag: Optional[str] = None,
) -> int:
    clauses = _filters(user_id, q, result, analyzed, opening, color, player, tag)
    return int(session.scalar(select(func.count(Game.id)).where(*clauses)) or 0)


def list_games(
    session: Session,
    user_id: int,
    limit: int = 100,
    offset: int = 0,
    q: Optional[str] = None,
    result: Optional[str] = None,
    analyzed: Optional[bool] = None,
    opening: Optional[str] = None,
    color: Optional[str] = None,
    player: Optional[str] = None,
    tag: Optional[str] = None,
    sort: str = "date_desc",
) -> list[dict]:
    clauses = _filters(user_id, q, result, analyzed, opening, color, player, tag)
    statement = select(Game).where(*clauses)
    mistake_total = (
        select(func.count(Mistake.id)).where(Mistake.game_id == Game.id).scalar_subquery()
    )
    if sort == "date_asc":
        statement = statement.order_by(Game.date.asc().nullslast(), Game.id.asc())
    elif sort == "mistakes_desc":
        statement = statement.order_by(mistake_total.desc(), Game.id.desc())
    elif sort == "opening_asc":
        statement = statement.order_by(Game.opening.asc().nullslast(), Game.id.desc())
    else:
        statement = statement.order_by(Game.date.desc().nullslast(), Game.id.desc())
    statement = statement.limit(max(1, min(limit, 500))).offset(max(0, offset))
    rows = list(session.scalars(statement))
    ids = [row.id for row in rows]
    moves, mistakes = _counts(session, ids)
    accuracy = accuracy_by_game(session, ids)
    return [
        game_summary(
            row,
            int(mistakes.get(row.id, 0)),
            int(moves.get(row.id, 0)),
            accuracy.get(row.id),
        )
        for row in rows
    ]


def clean_notes(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    if len(text) > MAX_NOTES_CHARS:
        raise ValueError(f"notes may not be longer than {MAX_NOTES_CHARS} characters")
    return text or None


def clean_tags(values: Optional[list]) -> Optional[list[str]]:
    if values is None:
        return None
    if not isinstance(values, list):
        raise ValueError("tags must be a list")
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("every tag must be text")
        tag = " ".join(value.strip().lower().split())
        if not tag:
            continue
        if len(tag) > MAX_TAG_CHARS:
            raise ValueError(f"a tag may not be longer than {MAX_TAG_CHARS} characters")
        if not TAG_PATTERN.match(tag):
            raise ValueError("tags may contain letters, numbers, spaces, hyphens and underscores")
        if tag not in cleaned:
            cleaned.append(tag)
    if len(cleaned) > MAX_TAGS:
        raise ValueError(f"a game may have at most {MAX_TAGS} tags")
    return cleaned or None


def all_tags(session: Session, user_id: int) -> list[dict]:
    counts: dict[str, int] = {}
    for tags in session.scalars(
        select(Game.tags).where(Game.user_id == user_id, Game.tags.is_not(None))
    ):
        if not isinstance(tags, list):
            continue
        for tag in tags:
            if isinstance(tag, str):
                counts[tag] = counts.get(tag, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
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
    game: Game,
    mistake_count: Optional[int] = None,
    move_count: Optional[int] = None,
    accuracy: Optional[dict] = None,
) -> dict:
    return {
        "accuracy": accuracy or {"white": None, "black": None},
        "notes": game.notes,
        "tags": list(game.tags) if isinstance(game.tags, list) else [],
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
    moves = sorted(game.moves or [], key=lambda move: move.ply)
    detail = game_summary(game, accuracy=accuracy_from_moves(moves))
    detail["moves"] = [move_to_dict(move) for move in moves]
    return detail


def game_detail(game: Game) -> dict:
    detail = game_with_moves(game)
    mistakes = sorted(game.mistakes or [], key=lambda item: item.ply)
    detail["mistakes"] = [mistake_to_dict(item) for item in mistakes]
    return detail
