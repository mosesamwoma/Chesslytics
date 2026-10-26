from __future__ import annotations

import csv
import io
import random
import re
import threading
import time
from pathlib import Path
from typing import Iterator, Optional

import chess
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.database import session_scope
from app.database.models import LibraryPuzzle

THEME_PATTERN = re.compile(r"^[A-Za-z0-9]{2,32}$")
FEATURED = {
    "fork": "fork",
    "pin": "pin",
    "skewer": "skewer",
    "discovered_attack": "discoveredAttack",
    "hanging_piece": "hangingPiece",
    "trapped_piece": "trappedPiece",
    "back_rank": "backRankMate",
    "mate": "mate",
    "sacrifice": "sacrifice",
    "zwischenzug": "intermezzo",
    "deflection": "deflection",
    "interference": "interference",
    "promotion": "promotion",
    "passed_pawn": "advancedPawn",
}
BATCH_SIZE = 2000
CACHE_SECONDS = 600

_cache_lock = threading.Lock()
_cache: dict = {"at": 0.0, "value": None}


class LibraryError(ValueError):
    pass


def valid_theme(value: Optional[str]) -> Optional[str]:
    if value and THEME_PATTERN.match(value):
        return value
    return None


def open_text(path: Path):
    name = path.name.lower()
    if name.endswith(".zst"):
        try:
            import zstandard
        except ImportError as exc:
            raise LibraryError(
                "reading .zst files needs the zstandard package: pip install zstandard"
            ) from exc
        raw = path.open("rb")
        reader = zstandard.ZstdDecompressor().stream_reader(raw)
        return io.TextIOWrapper(reader, encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def parse_rows(handle) -> Iterator[dict]:
    reader = csv.DictReader(handle)
    required = {"PuzzleId", "FEN", "Moves", "Rating", "Themes"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise LibraryError(
            "this does not look like the Lichess puzzle CSV: expected the columns "
            + ", ".join(sorted(required))
        )
    for row in reader:
        yield row


def clean_row(row: dict) -> Optional[dict]:
    puzzle_id = (row.get("PuzzleId") or "").strip()
    fen = (row.get("FEN") or "").strip()
    moves = (row.get("Moves") or "").split()
    try:
        rating = int(row.get("Rating") or 0)
        popularity = int(row.get("Popularity") or 0)
    except ValueError:
        return None
    if not puzzle_id or len(puzzle_id) > 16 or len(moves) < 2:
        return None
    try:
        board = chess.Board(fen)
        for text in moves:
            move = chess.Move.from_uci(text)
            if move not in board.legal_moves:
                return None
            board.push(move)
    except ValueError:
        return None
    themes = [item for item in (row.get("Themes") or "").split() if THEME_PATTERN.match(item)]
    return {
        "source_id": puzzle_id,
        "fen": fen,
        "moves": " ".join(moves),
        "rating": rating,
        "popularity": popularity,
        "themes_text": ("|" + "|".join(themes) + "|") if themes else None,
    }


def import_file(
    path: Path,
    limit: int = 50000,
    min_popularity: int = 0,
    min_rating: int = 0,
    max_rating: int = 4000,
    themes: Optional[list[str]] = None,
    progress=None,
) -> dict:
    wanted = [item for item in (themes or []) if valid_theme(item)]
    added = skipped = scanned = 0
    batch: list[dict] = []

    def flush() -> int:
        if not batch:
            return 0
        with session_scope() as session:
            existing = set(
                session.scalars(
                    select(LibraryPuzzle.source_id).where(
                        LibraryPuzzle.source_id.in_([item["source_id"] for item in batch])
                    )
                )
            )
            fresh = [item for item in batch if item["source_id"] not in existing]
            if fresh:
                session.bulk_insert_mappings(LibraryPuzzle, fresh)
        count = len(fresh)
        batch.clear()
        return count

    with open_text(path) as handle:
        for row in parse_rows(handle):
            scanned += 1
            if added + len(batch) >= limit:
                break
            try:
                popularity = int(row.get("Popularity") or 0)
                rating = int(row.get("Rating") or 0)
            except ValueError:
                skipped += 1
                continue
            if popularity < min_popularity or not (min_rating <= rating <= max_rating):
                continue
            if wanted:
                present = set((row.get("Themes") or "").split())
                if not present.intersection(wanted):
                    continue
            cleaned = clean_row(row)
            if cleaned is None:
                skipped += 1
                continue
            batch.append(cleaned)
            if len(batch) >= BATCH_SIZE:
                added += flush()
                if progress:
                    progress(added, scanned)
        added += flush()
    with _cache_lock:
        _cache["value"] = None
    return {"scanned": scanned, "added": added, "skipped": skipped}


def count(session: Session) -> int:
    return int(session.scalar(select(func.count(LibraryPuzzle.id))) or 0)


def theme_counts(session: Session) -> list[dict]:
    with _cache_lock:
        if _cache["value"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["value"]
    counts: dict[str, int] = {}
    for text in session.scalars(select(LibraryPuzzle.themes_text)):
        for theme in (text or "").strip("|").split("|"):
            if theme:
                counts[theme] = counts.get(theme, 0) + 1
    value = [
        {"theme": theme, "count": number}
        for theme, number in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    with _cache_lock:
        _cache["value"] = value
        _cache["at"] = time.time()
    return value


def _filtered(theme: Optional[str], min_rating: Optional[int], max_rating: Optional[int]):
    statement = select(LibraryPuzzle)
    if theme:
        statement = statement.where(LibraryPuzzle.themes_text.like(f"%|{theme}|%"))
    if min_rating is not None:
        statement = statement.where(LibraryPuzzle.rating >= min_rating)
    if max_rating is not None:
        statement = statement.where(LibraryPuzzle.rating <= max_rating)
    return statement


def pick(
    session: Session,
    theme: Optional[str],
    min_rating: Optional[int],
    max_rating: Optional[int],
    exclude: Optional[list[int]] = None,
) -> Optional[LibraryPuzzle]:
    statement = _filtered(theme, min_rating, max_rating)
    if exclude:
        statement = statement.where(LibraryPuzzle.id.not_in(exclude[:200]))
    total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    if total == 0:
        return None
    offset = random.randrange(total)
    return session.scalar(statement.order_by(LibraryPuzzle.id).offset(offset).limit(1))


def get(session: Session, puzzle_id: int) -> Optional[LibraryPuzzle]:
    return session.get(LibraryPuzzle, puzzle_id)


def _moves(puzzle: LibraryPuzzle) -> list[chess.Move]:
    return [chess.Move.from_uci(item) for item in puzzle.moves.split()]


def start(puzzle: LibraryPuzzle) -> dict:
    board = chess.Board(puzzle.fen)
    moves = _moves(puzzle)
    opener = moves[0]
    opener_san = board.san(opener)
    board.push(opener)
    themes = [item for item in (puzzle.themes_text or "").strip("|").split("|") if item]
    return {
        "id": puzzle.id,
        "source_id": puzzle.source_id,
        "rating": puzzle.rating,
        "themes": themes,
        "fen": board.fen(),
        "orientation": "white" if board.turn == chess.WHITE else "black",
        "legal_moves": sorted(move.uci() for move in board.legal_moves),
        "opponent_uci": opener.uci(),
        "opponent_san": opener_san,
        "step": 1,
        "total": len(moves) // 2,
    }


def check(puzzle: LibraryPuzzle, step: int, uci: str) -> dict:
    moves = _moves(puzzle)
    if step < 1 or step % 2 != 1 or step >= len(moves):
        raise LibraryError("that step is not part of this puzzle")
    board = chess.Board(puzzle.fen)
    for move in moves[:step]:
        board.push(move)
    try:
        played = chess.Move.from_uci(uci.strip().lower())
    except ValueError as exc:
        raise LibraryError(f"{uci!r} is not a move in UCI form") from exc
    if played not in board.legal_moves:
        raise LibraryError(f"{played.uci()} is not legal in this position")

    played_san = board.san(played)
    expected = moves[step]
    total = len(moves) // 2
    mates = False
    probe = board.copy(stack=False)
    probe.push(played)
    mates = probe.is_checkmate()
    if played != expected and not mates:
        return {"correct": False, "done": False, "step": step, "total": total, "played_san": played_san}

    board.push(played)
    following = step + 1
    if mates or following >= len(moves):
        return {
            "correct": True,
            "done": True,
            "step": step,
            "total": total,
            "played_san": played_san,
            "fen": board.fen(),
            "legal_moves": [],
        }
    reply = moves[following]
    reply_san = board.san(reply)
    board.push(reply)
    return {
        "correct": True,
        "done": False,
        "step": following + 1,
        "total": total,
        "played_san": played_san,
        "opponent_uci": reply.uci(),
        "opponent_san": reply_san,
        "fen": board.fen(),
        "legal_moves": sorted(move.uci() for move in board.legal_moves),
    }


def solution(puzzle: LibraryPuzzle) -> dict:
    board = chess.Board(puzzle.fen)
    names = []
    for move in _moves(puzzle):
        names.append(board.san(move))
        board.push(move)
    return {"id": puzzle.id, "san": names[1:], "opponent_first": names[0]}
