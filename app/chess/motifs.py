from __future__ import annotations

from typing import Optional

import chess

from app.chess.pieces import PIECE_NAMES, SEE_VALUES, see_value
from app.chess.see import best_exchange

DIRECTIONS = {
    chess.BISHOP: ((-1, -1), (-1, 1), (1, -1), (1, 1)),
    chess.ROOK: ((-1, 0), (1, 0), (0, -1), (0, 1)),
    chess.QUEEN: (
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
    ),
}

SLIDERS = tuple(DIRECTIONS)


def _with_side_to_move(
    board: chess.Board, color: chess.Color
) -> Optional[chess.Board]:
    probe = board.copy(stack=False)
    if probe.turn == color:
        return probe
    if probe.is_check() or probe.is_game_over():
        return None
    probe.push(chess.Move.null())
    return probe


def describe(piece: chess.Piece) -> str:
    return PIECE_NAMES[piece.piece_type]


def mate_threats(board: chess.Board) -> list[dict]:
    found = []
    for move in board.legal_moves:
        if not board.gives_check(move):
            continue
        board.push(move)
        try:
            if not board.is_checkmate():
                continue
            king_square = board.king(board.turn)
            back_rank = king_square is not None and chess.square_rank(king_square) in (0, 7)
        finally:
            board.pop()
        found.append(
            {
                "kind": "mate",
                "move": move.uci(),
                "back_rank": back_rank,
                "at": chess.square_name(move.to_square),
            }
        )
    return found


def forks(board: chess.Board) -> list[dict]:
    found = []
    mover = board.turn

    for move in board.legal_moves:
        board.push(move)
        try:
            piece = board.piece_at(move.to_square)
            if piece is None:
                continue
            attacker = see_value(piece)
            gives_check = board.is_check()

            victims = []
            for square in board.attacks(move.to_square):
                target = board.piece_at(square)
                if target is None or target.color == piece.color:
                    continue
                if target.piece_type == chess.KING:
                    values = 0
                else:
                    defended = bool(board.attackers(not piece.color, square))
                    if defended and see_value(target) <= attacker:
                        continue
                    values = see_value(target)
                victims.append(
                    {
                        "square": chess.square_name(square),
                        "piece": target.symbol(),
                        "name": describe(target),
                        "value": values,
                    }
                )

            if len(victims) < 2:
                continue

            if gives_check:
                safe = True
            else:
                cost, _ = best_exchange(board, move.to_square)
                safe = cost == 0
            if not safe:
                continue

            found.append(
                {
                    "kind": "fork",
                    "move": move.uci(),
                    "at": chess.square_name(move.to_square),
                    "piece": piece.symbol(),
                    "name": describe(piece),
                    "check": gives_check,
                    "victims": victims,
                }
            )
        finally:
            board.pop()
    return found


def _ray_targets(
    board: chess.Board, square: chess.Square, piece_type: int
) -> list[tuple[chess.Square, chess.Square]]:
    pairs = []
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)

    for file_step, rank_step in DIRECTIONS[piece_type]:
        seen: list[chess.Square] = []
        file_cursor = file_index + file_step
        rank_cursor = rank_index + rank_step
        while 0 <= file_cursor <= 7 and 0 <= rank_cursor <= 7:
            cursor = chess.square(file_cursor, rank_cursor)
            if board.piece_at(cursor) is not None:
                seen.append(cursor)
                if len(seen) == 2:
                    break
            file_cursor += file_step
            rank_cursor += rank_step
        if len(seen) == 2:
            pairs.append((seen[0], seen[1]))
    return pairs


def pins_and_skewers(board: chess.Board) -> list[dict]:
    found = []
    ours = board.turn

    for square, piece in board.piece_map().items():
        if piece.color != ours or piece.piece_type not in SLIDERS:
            continue
        for front, back in _ray_targets(board, square, piece.piece_type):
            front_piece = board.piece_at(front)
            back_piece = board.piece_at(back)
            if front_piece.color == ours or back_piece.color == ours:
                continue

            detail = {
                "attacker": chess.square_name(square),
                "attacker_piece": piece.symbol(),
                "front": chess.square_name(front),
                "front_piece": front_piece.symbol(),
                "back": chess.square_name(back),
                "back_piece": back_piece.symbol(),
            }

            if back_piece.piece_type == chess.KING:
                found.append({**detail, "kind": "pin", "absolute": True})
            elif see_value(back_piece) > see_value(front_piece):
                found.append({**detail, "kind": "pin", "absolute": False})
            elif see_value(front_piece) > see_value(back_piece):
                found.append({**detail, "kind": "skewer", "absolute": False})

    return found


def detect_motifs(board: chess.Board, color: chess.Color) -> list[dict]:
    probe = _with_side_to_move(board, color)
    if probe is None:
        return []
    motifs = mate_threats(probe)
    motifs.extend(forks(probe))
    motifs.extend(pins_and_skewers(probe))
    for motif in motifs:
        motif["detail"] = describe_motif(motif)
    return motifs


def motif_kinds(motifs: list[dict]) -> list[str]:
    order = ("mate", "fork", "pin", "skewer")
    present = {motif["kind"] for motif in motifs}
    return [kind for kind in order if kind in present]


def summarise(motifs: list[dict]) -> list[str]:
    return [describe_motif(motif) for motif in motifs]


def describe_motif(motif: dict) -> str:
    if motif["kind"] == "mate":
        where = " on the back rank" if motif.get("back_rank") else ""
        return f"mate in one{where} with {motif['move']}"
    if motif["kind"] == "fork":
        names = ", ".join(victim["name"] for victim in motif["victims"])
        check = " with check" if motif.get("check") else ""
        return f"fork {motif['move']}{check} winning {names}"
    if motif["kind"] == "pin":
        kind = "absolute" if motif.get("absolute") else "relative"
        return (
            f"{kind} pin: {motif['front_piece']} on {motif['front']} "
            f"held by {motif['attacker_piece']} on {motif['attacker']}"
        )
    if motif["kind"] == "skewer":
        return (
            f"skewer: {motif['attacker_piece']} on {motif['attacker']} takes "
            f"{motif['front_piece']} on {motif['front']}, exposing "
            f"{motif['back_piece']} on {motif['back']}"
        )
    return motif["kind"]
