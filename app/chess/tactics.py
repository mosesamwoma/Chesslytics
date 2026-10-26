from __future__ import annotations

from typing import Optional

import chess

from app.chess.lines import classify_line, ordered_themes
from app.chess.motifs import (
    detect_extended,
    detect_motifs,
    detect_weaknesses,
    describe_motif,
)
from app.chess.solver import forced_mate, line_to_san

MOTIF_THEME = {
    "mate": "mate",
    "fork": "fork",
    "pin": "pin",
    "skewer": "skewer",
    "discovered_attack": "discovered_attack",
    "trapped_piece": "trapped_piece",
    "back_rank_weakness": "back_rank",
    "promotion": "promotion",
    "passed_pawn": "passed_pawn",
    "overloaded_defender": "overloaded_defender",
    "remove_defender": "remove_defender",
}

MOVE_BOUND = ("mate", "fork", "discovered_attack", "promotion", "remove_defender")


def _parse_moves(board: chess.Board, ucis: list[str]) -> list[chess.Move]:
    probe = board.copy(stack=False)
    moves: list[chess.Move] = []
    for text in ucis:
        try:
            move = chess.Move.from_uci(text)
        except ValueError:
            break
        if move not in probe.legal_moves:
            break
        moves.append(move)
        probe.push(move)
    return moves


def _entry(motif: dict) -> dict:
    return {
        "kind": motif["kind"],
        "detail": motif.get("detail") or describe_motif(motif),
        "move": motif.get("move"),
        "squares": list(motif.get("squares") or []),
    }


def _theme_for(motif: dict) -> Optional[str]:
    theme = MOTIF_THEME.get(motif["kind"])
    if theme == "mate" and motif.get("back_rank"):
        return "back_rank"
    return theme


def analyze_mistake(
    fen: str,
    played_uci: Optional[str],
    best_line_ucis: list[str],
    best_uci: Optional[str],
    facts: dict,
) -> dict:
    result: dict = {
        "heuristic": True,
        "themes": [],
        "missed": [],
        "allowed": [],
        "line": None,
        "forced_mate": None,
        "exchange": None,
        "squares": [],
    }
    try:
        board = chess.Board(fen)
    except ValueError:
        return result

    mover = board.turn
    opponent = not mover
    themes: set[str] = set()
    squares: list[str] = []

    line = _parse_moves(board, best_line_ucis)
    if not line and best_uci:
        line = _parse_moves(board, [best_uci])
    best_move = line[0] if line else None
    played: Optional[chess.Move] = None
    if played_uci:
        try:
            candidate = chess.Move.from_uci(played_uci)
        except ValueError:
            candidate = None
        if candidate is not None and candidate in board.legal_moves:
            played = candidate

    if line:
        info = classify_line(board, line)
        result["line"] = info
        if info["outcome"] != "none" or info["themes"]:
            themes.update(info["themes"])
            squares.extend(info["squares"])
        if info["outcome"] == "mate":
            themes.add("mate")

    best_uci_text = best_move.uci() if best_move else best_uci
    missed_seen: set[tuple[str, str]] = set()
    if best_move is not None and (played is None or best_move != played):
        before = detect_motifs(board, mover) + detect_extended(board, mover)
        for motif in before:
            if motif.get("move") and motif["move"] == best_uci_text:
                key = (motif["kind"], motif["move"])
                if key in missed_seen:
                    continue
                missed_seen.add(key)
                result["missed"].append(_entry(motif))
                theme = _theme_for(motif)
                if theme:
                    themes.add(theme)
                squares.extend(motif.get("squares") or [])
        after_best = board.copy(stack=False)
        after_best.push(best_move)
        for weakness in detect_weaknesses(after_best, opponent):
            result["missed"].append(_entry(weakness))
            theme = _theme_for(weakness)
            if theme:
                themes.add(theme)
            squares.extend(weakness.get("squares") or [])

    after = board.copy(stack=False)
    if played is not None:
        after.push(played)
        for motif in detect_motifs(after, opponent) + detect_extended(after, opponent):
            result["allowed"].append(_entry(motif))
            theme = _theme_for(motif)
            if theme:
                themes.add(theme)
        for weakness in detect_weaknesses(after, mover):
            result["allowed"].append(_entry(weakness))
            theme = _theme_for(weakness)
            if theme:
                themes.add(theme)

    hung = facts.get("hung_piece") if facts else None
    if facts and (facts.get("newly_hanging") or facts.get("hangs_piece")) and hung:
        themes.add("hanging_piece")
        if hung.get("square"):
            squares.append(hung["square"])
        exchange = hung.get("exchange")
        if exchange:
            result["exchange"] = " ".join(exchange)

    proof = forced_mate(board, mover)
    if proof:
        result["forced_mate"] = {
            "for": "mover",
            "in": (len(proof) + 1) // 2,
            "san": line_to_san(board, proof),
        }
        themes.add("mate")
    elif played is not None:
        allowed_proof = forced_mate(after, opponent)
        if allowed_proof:
            result["forced_mate"] = {
                "for": "opponent",
                "in": (len(allowed_proof) + 1) // 2,
                "san": line_to_san(after, allowed_proof),
            }
            themes.add("mate")

    unique: list[str] = []
    for name in squares:
        if name not in unique:
            unique.append(name)
    result["themes"] = ordered_themes(themes)
    result["squares"] = unique[:10]
    return result


def themes_text(themes: list[str]) -> Optional[str]:
    if not themes:
        return None
    return "|" + "|".join(themes) + "|"
