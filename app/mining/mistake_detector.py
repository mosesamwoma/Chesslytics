from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import chess

from app.chess.book import BookReader
from app.chess.features import newly_hanging

DECIDED_WIN_PCT = 90.0
MOVE_BUCKETS = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 10_000)]


@dataclass
class MinerConfig:
    min_loss: float = 1.0
    time_pressure: float = 30.0
    player: Optional[str] = None
    color: str = "both"
    inaccuracy: float = 0.5
    mistake: float = 1.0
    blunder: float = 2.0
    ignore_decided: bool = True
    book: Optional[str] = None
    exclude_book: bool = False

    def as_dict(self) -> dict:
        return {
            "min_loss": self.min_loss,
            "time_pressure": self.time_pressure,
            "player": self.player,
            "color": self.color,
            "inaccuracy": self.inaccuracy,
            "mistake": self.mistake,
            "blunder": self.blunder,
            "ignore_decided": self.ignore_decided,
            "book": self.book,
            "exclude_book": self.exclude_book,
        }


def severity_for(loss_pawns: float, config: MinerConfig) -> str:
    if loss_pawns >= config.blunder:
        return "blunder"
    if loss_pawns >= config.mistake:
        return "mistake"
    if loss_pawns >= config.inaccuracy:
        return "inaccuracy"
    return "normal"


def is_decided(win_before: float, win_after: float) -> bool:
    winning_before = win_before >= DECIDED_WIN_PCT
    winning_after = win_after >= DECIDED_WIN_PCT
    losing_before = win_before <= (100.0 - DECIDED_WIN_PCT)
    losing_after = win_after <= (100.0 - DECIDED_WIN_PCT)
    return (winning_before and winning_after) or (losing_before and losing_after)


def move_bucket(move_number: int) -> str:
    for low, high in MOVE_BUCKETS:
        if low <= move_number <= high:
            return f"{low}-{high}" if high < 10_000 else f"{low}+"
    return "unknown"


def player_color(metadata: dict, player: str) -> Optional[str]:
    wanted = player.strip().lower()
    if (metadata.get("white") or "").strip().lower() == wanted:
        return "white"
    if (metadata.get("black") or "").strip().lower() == wanted:
        return "black"
    return None


def describe_piece(piece: Optional[dict]) -> str:
    if not piece:
        return "piece"
    return f"{piece.get('name', piece.get('piece', 'piece'))} on {piece.get('square', '?')}"


MOTIF_ORDER = ("mate", "fork", "pin", "skewer")


def motif_phrase(facts: dict, exclude: tuple = ()) -> str:
    present = {
        motif["kind"] for motif in (facts.get("motifs_allowed") or [])
    }
    kinds = [kind for kind in MOTIF_ORDER if kind in present and kind not in exclude]
    if not kinds:
        return ""
    if len(kinds) == 1:
        return f" and hands the opponent a {kinds[0]}"
    return " and hands the opponent a " + ", a ".join(kinds[:-1]) + f" and a {kinds[-1]}"


def categorize(record: dict, config: MinerConfig) -> tuple[str, str]:
    facts = record["facts"]
    tactics = motif_phrase(facts)

    if facts.get("allows_mate"):
        return (
            "allowed_mate",
            f"this move lets the opponent mate{motif_phrase(facts, exclude=('mate',))}",
        )

    if facts["best_move_was_mate"]:
        return (
            "missed_mate",
            "the engine had an immediate checkmate and a different move was played",
        )

    if facts.get("newly_hanging"):
        piece = facts["hung_piece"]
        see = piece.get("see_pawns") if piece else None
        worth = f", worth {see:g} pawns by static exchange" if see else ""
        return (
            "hanging_piece",
            f"this move left the {describe_piece(piece)} en prise{worth}{tactics}",
        )

    if facts["hangs_piece"]:
        return (
            "hanging_piece",
            f"the {describe_piece(facts['hung_piece'])} was already en prise before "
            f"this move and still is{tactics}",
        )

    if facts["best_move_was_capture"] and not facts["is_capture"]:
        return (
            "missed_capture",
            "the engine's preferred move was a capture; a quiet move was played instead",
        )

    if record["in_time_pressure"]:
        remaining = record["time_remaining"]
        return (
            "time_pressure",
            f"played with {remaining:.0f}s left on the clock, against a "
            f"{config.time_pressure:.0f}s threshold",
        )

    return (
        record["phase"],
        f"no more specific cause identified; the move lost ground in the "
        f"{record['phase']}{tactics}",
    )


def book_facts(reader: Optional[BookReader], fen: Optional[str]) -> tuple[Optional[bool], Optional[str]]:
    if reader is None or not fen:
        return None, None
    try:
        board = chess.Board(fen)
    except ValueError:
        return None, None
    if board.is_game_over():
        return False, None
    move = reader.move_for(board)
    if move is None:
        return False, None
    try:
        return True, board.san(move)
    except Exception:
        return True, None


def build_records(
    games: dict[str, dict],
    config: MinerConfig,
    reader: Optional[BookReader] = None,
) -> tuple[list[dict], dict]:
    mistakes: list[dict] = []
    context: dict[str, Any] = {
        "games_analyzed": 0,
        "games_matched_player": 0,
        "games_with_clock": 0,
        "games_with_book": 0,
        "moves_scored": 0,
        "moves_failed": 0,
        "book_positions": 0,
        "moves_in_book": 0,
        "excluded_decided": 0,
        "excluded_not_played_by_color": 0,
        "excluded_book": 0,
        "mistakes_in_book": 0,
        "book_depths": [],
        "book": None,
        "player_not_found": False,
    }

    if reader is not None:
        context["book"] = reader.name

    player_wanted = bool(config.player)

    for game_id, (game_key, game) in enumerate(games.items(), start=1):
        metadata = game.get("metadata", {})
        moves = game.get("moves", [])
        context["games_analyzed"] += 1

        if any(move.get("clock_after") is not None for move in moves):
            context["games_with_clock"] += 1

        played_color: Optional[str] = None
        if player_wanted:
            played_color = player_color(metadata, config.player)
            if played_color is None:
                continue
            context["games_matched_player"] += 1

        opening = metadata.get("opening") or metadata.get("eco") or None
        book_plies: list[int] = []

        for move in moves:
            if move.get("error"):
                context["moves_failed"] += 1
                continue
            if "eval_before_cp" not in move:
                continue

            context["moves_scored"] += 1

            if config.color != "both" and move["color"] != config.color:
                context["excluded_not_played_by_color"] += 1
                continue
            if player_wanted and move["color"] != played_color:
                context["excluded_not_played_by_color"] += 1
                continue

            in_book, book_move = book_facts(reader, move.get("fen_before"))
            if reader is not None:
                context["book_positions"] += 1
                if in_book:
                    context["moves_in_book"] += 1
                    book_plies.append(move["ply"])

            loss_cp = move["loss_cp"]
            loss_pawns = max(loss_cp, 0) / 100.0
            if loss_pawns < config.min_loss:
                continue

            win_before = move["winpct_before"]
            win_after = move["winpct_after"]
            decided = is_decided(win_before, win_after)

            if decided and config.ignore_decided:
                context["excluded_decided"] += 1
                continue

            hanging_after = move.get("hanging_after") or []
            hanging_was = move.get("hanging_before") or []
            hanging_new = newly_hanging(hanging_was, hanging_after)
            motifs_allowed = move.get("motifs_allowed") or []
            mate_after = move.get("eval_after_mate")
            allows_mate = any(
                motif["kind"] == "mate" for motif in motifs_allowed
            ) or (mate_after is not None and mate_after < 0)
            clock_before = move.get("clock_before")

            record = {
                "game_id": game_id,
                "game_key": game_key,
                "move_number": move["move_number"],
                "ply": move["ply"],
                "color": move["color"],
                "played_move": move["san"],
                "played_uci": move.get("uci"),
                "best_move": move.get("best_move_san") or move.get("best_move_uci"),
                "best_move_uci": move.get("best_move_uci"),
                "eval_before": round(move["eval_before_cp"] / 100.0, 2),
                "eval_after": round(move["eval_after_cp"] / 100.0, 2),
                "loss": round(loss_pawns, 2),
                "loss_cp": loss_cp,
                "winpct_before": round(win_before, 1),
                "winpct_after": round(win_after, 1),
                "winpct_loss": round(win_before - win_after, 1),
                "severity": severity_for(loss_pawns, config),
                "fen": move["fen_before"],
                "fen_after": move.get("fen_after"),
                "phase": move["phase"],
                "opening": opening,
                "in_book": in_book,
                "book_move": book_move,
                "game_decided": decided,
                "mate_before": move.get("eval_before_mate"),
                "mate_after": move.get("eval_after_mate"),
                "facts": {
                    "is_capture": move.get("is_capture", False),
                    "is_check": move.get("is_check", False),
                    "is_mate": move.get("is_mate", False),
                    "is_promotion": move.get("is_promotion", False),
                    "is_castling": move.get("is_castling", False),
                    "hangs_piece": bool(hanging_after),
                    "hung_piece": (hanging_new or hanging_after or [None])[0],
                    "newly_hanging": hanging_new,
                    "hanging_before": hanging_was,
                    "hanging_after": hanging_after,
                    "motifs_allowed": motifs_allowed,
                    "motifs_before": move.get("motifs_before") or [],
                    "allows_mate": allows_mate,
                    "best_move_was_capture": move.get("best_move_was_capture", False),
                    "best_move_was_check": move.get("best_move_was_check", False),
                    "best_move_was_mate": move.get("best_move_was_mate", False),
                    "move_bucket": move_bucket(move["move_number"]),
                    "material_before": move.get("material_before"),
                    "material_after": move.get("material_after"),
                    "king_safety_after": move.get("king_safety_after"),
                },
                "time_remaining": clock_before,
                "clock_after": move.get("clock_after"),
                "in_time_pressure": (
                    clock_before is not None and clock_before < config.time_pressure
                ),
                "player": metadata.get(move["color"]),
                "opponent": (
                    metadata.get("black")
                    if move["color"] == "white"
                    else metadata.get("white")
                ),
            }
            record["category"], record["category_basis"] = categorize(record, config)
            if config.exclude_book and in_book:
                context["excluded_book"] += 1
                continue
            mistakes.append(record)

        if book_plies:
            context["games_with_book"] += 1
            context["book_depths"].append(max(book_plies))

    if player_wanted and context["games_matched_player"] == 0:
        context["player_not_found"] = True

    context["mistakes_in_book"] = sum(
        1 for mistake in mistakes if mistake["in_book"]
    )
    mistakes.sort(key=lambda item: -item["loss_cp"])
    return mistakes, context
