from __future__ import annotations

import csv
import threading
from collections import Counter
from pathlib import Path
from typing import Optional

import chess

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "openings.tsv"
MAX_CLASSIFY_PLIES = 40

_lock = threading.Lock()
_names: dict[str, tuple[str, str, int]] = {}
_next: dict[str, Counter] = {}
_loaded = False


def _key(board: chess.Board) -> str:
    return board.epd()


def _load() -> None:
    global _loaded
    with _lock:
        if _loaded:
            return
        with DATA_FILE.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle, delimiter="\t")
            next(reader, None)
            for eco, name, moves in reader:
                board = chess.Board()
                parsed = [chess.Move.from_uci(item) for item in moves.split()]
                for move in parsed:
                    key = _key(board)
                    _next.setdefault(key, Counter())[move.uci()] += 1
                    board.push(move)
                final = _key(board)
                current = _names.get(final)
                if current is None or len(parsed) >= current[2]:
                    _names[final] = (eco, name, len(parsed))
        _loaded = True


def lookup(board: chess.Board) -> Optional[tuple[str, str]]:
    _load()
    found = _names.get(_key(board))
    return (found[0], found[1]) if found else None


def known(board: chess.Board) -> bool:
    _load()
    key = _key(board)
    return key in _names or key in _next


def next_moves(board: chess.Board) -> list[str]:
    _load()
    counts = _next.get(_key(board))
    if not counts:
        return []
    return [move for move, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def classify_moves(ucis: list[str]) -> Optional[tuple[str, str, int]]:
    _load()
    board = chess.Board()
    best: Optional[tuple[str, str, int]] = None
    for ply, text in enumerate(ucis[:MAX_CLASSIFY_PLIES], start=1):
        try:
            move = chess.Move.from_uci(text)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        board.push(move)
        found = _names.get(_key(board))
        if found is not None:
            best = (found[0], found[1], ply)
    return best


class EcoBook:
    name = "Lichess openings"

    def close(self) -> None:
        return None

    def __enter__(self) -> EcoBook:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def move_for(self, board: chess.Board) -> Optional[chess.Move]:
        options = next_moves(board)
        if not options:
            return None
        move = chess.Move.from_uci(options[0])
        return move if move in board.legal_moves else None

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
