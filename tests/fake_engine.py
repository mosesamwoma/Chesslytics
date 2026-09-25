from __future__ import annotations

from typing import Any, Optional

import chess
import chess.engine


class ScriptedEngine:
    def __init__(
        self,
        script: Optional[dict[str, Any]] = None,
        default_cp: int = 0,
        default_best: Optional[str] = None,
    ) -> None:
        self.script = script or {}
        self.default_cp = default_cp
        self.default_best = default_best
        self.calls: list[str] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def analyse(self, board: chess.Board, limit: Any = None, **kwargs: Any) -> dict:
        self.calls.append(board.fen())

        entry = self.script.get(board.fen(), {})
        if callable(entry):
            entry = entry(board)

        if "error" in entry:
            raise entry["error"]

        mate = entry.get("mate")
        score: chess.engine.Score = (
            chess.engine.Mate(mate)
            if mate is not None
            else chess.engine.Cp(entry.get("cp", self.default_cp))
        )

        info: dict[str, Any] = {
            "score": chess.engine.PovScore(score, board.turn),
            "depth": entry.get("depth", 12),
            "pv": [],
        }

        best_uci = entry.get("best", self.default_best)
        if best_uci:
            info["pv"] = [chess.Move.from_uci(best_uci)]
        return info


class FakeChessEngine:
    def __init__(self, path: Optional[str] = None, limit: Any = None, scripted: Any = None) -> None:
        self.path = path
        self.limit = limit
        self.scripted = scripted if scripted is not None else ScriptedEngine()

    def __enter__(self) -> "FakeChessEngine":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def start(self) -> "FakeChessEngine":
        return self

    def close(self) -> None:
        return None

    @property
    def running(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "Fake Engine 1"

    def analyse(self, board: chess.Board, limit: Any = None, **kwargs: Any) -> dict:
        return self.scripted.analyse(board, limit, **kwargs)

    def best_move(self, board: chess.Board) -> Optional[chess.Move]:
        pv = self.analyse(board).get("pv") or []
        return pv[0] if pv else None
