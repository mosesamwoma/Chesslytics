from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import chess

MIN_WEIGHT = 1


class BookUnavailable(ValueError):
    pass


class BookReader:
    def __init__(self, path: str) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_file():
            raise BookUnavailable(f"no opening book at {self.path}")
        try:
            import chess.polyglot
        except ImportError as exc:
            raise BookUnavailable(
                "this python-chess install has no polyglot support"
            ) from exc
        self._reader = chess.polyglot.open_reader(str(self.path))

    @property
    def name(self) -> str:
        return self.path.name

    def close(self) -> None:
        self._reader.close()

    def __enter__(self) -> BookReader:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def move_for(self, board: chess.Board) -> Optional[chess.Move]:
        try:
            entry = self._reader.find(board, minimum_weight=MIN_WEIGHT)
        except (IndexError, KeyError):
            return None
        if entry is None:
            return None
        return entry.move

    def san_for(self, board: chess.Board) -> Optional[str]:
        move = self.move_for(board)
        if move is None:
            return None
        try:
            return board.san(move)
        except Exception:
            return None

    def covers(self, board: chess.Board) -> bool:
        return self.move_for(board) is not None


def book_path(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit
    return os.environ.get("BOOK_PATH") or None


def open_book(explicit: Optional[str] = None) -> Optional[BookReader]:
    chosen = book_path(explicit)
    if not chosen:
        return None
    return BookReader(chosen)


def describe(reader: Optional[BookReader]) -> str:
    return reader.name if reader is not None else "none"
