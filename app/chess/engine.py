from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import chess
import chess.engine


class Engine(Protocol):
    def analyse(self, board: chess.Board, limit: Any = None, **kwargs: Any) -> dict:
        ...


@dataclass(frozen=True)
class SearchLimit:
    kind: str
    value: float

    def to_engine_limit(self) -> chess.engine.Limit:
        if self.kind == "depth":
            return chess.engine.Limit(depth=int(self.value))
        if self.kind == "time":
            return chess.engine.Limit(time=float(self.value))
        raise ValueError(f"unknown limit kind: {self.kind!r}")

    def as_key(self) -> dict:
        return {"type": self.kind, "value": self.value}

    def describe(self) -> str:
        if self.kind == "depth":
            return f"depth {int(self.value)}"
        return f"{self.value:.3g}s per position"


def find_stockfish(explicit: Optional[str] = None) -> str:
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError(
                f"Stockfish not found at {explicit!r}. Pass a valid path with --stockfish."
            )
        return explicit

    from_env = os.environ.get("STOCKFISH_PATH")
    if from_env:
        if not os.path.exists(from_env):
            raise FileNotFoundError(
                f"STOCKFISH_PATH points at {from_env!r}, which does not exist."
            )
        return from_env

    found = shutil.which("stockfish")
    if found:
        return found

    raise FileNotFoundError(
        "Could not find Stockfish.\n"
        "  Fedora:  sudo dnf install stockfish\n"
        "  Debian:  sudo apt install stockfish\n"
        "  macOS:   brew install stockfish\n"
        "Or set STOCKFISH_PATH, or pass --stockfish /path/to/stockfish."
    )


class ChessEngine:
    def __init__(
        self, path: str, limit: SearchLimit, threads: Optional[int] = None
    ) -> None:
        self.path = path
        self.limit = limit
        self.threads = threads
        self._engine: Optional[chess.engine.SimpleEngine] = None

    def start(self) -> ChessEngine:
        self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
        if self.threads is not None:
            self.configure({"Threads": self.threads})
        return self

    def configure(self, options: dict) -> dict:
        if self._engine is None:
            raise RuntimeError("engine is not running")
        supported = {name.lower(): name for name in self._engine.options}
        wanted = {
            supported[key.lower()]: value
            for key, value in options.items()
            if key.lower() in supported
        }
        if wanted:
            self._engine.configure(wanted)
        return wanted

    def close(self) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def __enter__(self) -> ChessEngine:
        return self.start()

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    @property
    def running(self) -> bool:
        return self._engine is not None

    @property
    def name(self) -> str:
        if self._engine is None:
            return "unknown"
        return self._engine.id.get("name", "unknown")

    def analyse(self, board: chess.Board, limit: Any = None, **kwargs: Any) -> dict:
        if self._engine is None:
            raise RuntimeError("engine is not running")
        target = limit if limit is not None else self.limit.to_engine_limit()
        return self._engine.analyse(board, target, **kwargs)

    def best_move(self, board: chess.Board) -> Optional[chess.Move]:
        info = self.analyse(board)
        pv = info.get("pv") or []
        return pv[0] if pv else None
