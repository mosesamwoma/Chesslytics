from __future__ import annotations

import hashlib
import io
import os
from typing import IO, Optional

import chess
import chess.pgn


def parse_pgn(text: str) -> tuple[list[chess.pgn.Game], list[str]]:
    return _read_stream(io.StringIO(text))


def load_games(path: str) -> tuple[list[chess.pgn.Game], list[str]]:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return _read_stream(handle)


def _read_stream(stream: IO[str]) -> tuple[list[chess.pgn.Game], list[str]]:
    games: list[chess.pgn.Game] = []
    errors: list[str] = []
    index = 0

    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception as exc:
            errors.append(f"game #{index + 1}: unreadable ({exc})")
            break
        if game is None:
            break
        index += 1
        try:
            if game.errors:
                raise ValueError("; ".join(str(error) for error in game.errors))
            if not game.headers.get("White") and not game.headers.get("Black"):
                raise ValueError("no player headers")
            games.append(game)
        except Exception as exc:
            errors.append(f"game #{index}: skipped ({exc})")

    return games, errors


def game_fingerprint(game: chess.pgn.Game) -> str:
    digest = hashlib.sha1()
    for key in sorted(game.headers):
        digest.update(f"{key}={game.headers[key]}\n".encode("utf-8"))
    for node in game.mainline():
        digest.update((node.move.uci() if node.move else "").encode("ascii"))
        digest.update(b"|")
    return digest.hexdigest()


def clock_of(node: Optional[chess.pgn.GameNode]) -> Optional[float]:
    if node is None:
        return None
    try:
        return node.clock()
    except Exception:
        return None


def opening_name(headers) -> Optional[str]:
    for key in ("Opening", "ECO", "Variation"):
        value = headers.get(key)
        if value and value not in ("?", "-"):
            return value
    return None


def game_metadata(game: chess.pgn.Game) -> dict:
    headers = game.headers
    return {
        "fingerprint": game_fingerprint(game),
        "white": headers.get("White", ""),
        "black": headers.get("Black", ""),
        "result": headers.get("Result", ""),
        "date": headers.get("Date", ""),
        "event": headers.get("Event", ""),
        "site": headers.get("Site", ""),
        "eco": headers.get("ECO", ""),
        "opening": headers.get("Opening", ""),
        "variation": headers.get("Variation", ""),
        "time_control": headers.get("TimeControl", ""),
        "white_elo": headers.get("WhiteElo", ""),
        "black_elo": headers.get("BlackElo", ""),
    }


def players(metadata: dict) -> list[str]:
    return [name for name in (metadata.get("white"), metadata.get("black")) if name]
