from __future__ import annotations

from typing import Optional

import chess

from app import settings
from app.chess.motifs import (
    back_rank_weakness,
    discovered_attacks,
    forks,
    pins_and_skewers,
    _with_side_to_move,
)
from app.chess.pieces import SEE_VALUES
from app.chess.see import captures_onto, static_exchange, swap_gain

THEME_ORDER = (
    "mate",
    "back_rank",
    "fork",
    "pin",
    "skewer",
    "discovered_attack",
    "hanging_piece",
    "trapped_piece",
    "sacrifice",
    "zwischenzug",
    "deflection",
    "remove_defender",
    "interference",
    "overloaded_defender",
    "promotion",
    "passed_pawn",
    "capture_chain",
)


def ordered_themes(themes: set[str]) -> list[str]:
    return [theme for theme in THEME_ORDER if theme in themes]


def material(board: chess.Board, color: chess.Color) -> int:
    own = 0
    other = 0
    for piece in board.piece_map().values():
        if piece.piece_type == chess.KING:
            continue
        if piece.color == color:
            own += SEE_VALUES[piece.piece_type]
        else:
            other += SEE_VALUES[piece.piece_type]
    return own - other


def _later_gain(work: chess.Board, line: list[chess.Move], index: int) -> int:
    if index + 2 >= len(line):
        return 0
    capture = line[index + 2]
    probe = work.copy(stack=False)
    for move in (line[index], line[index + 1]):
        if move not in probe.legal_moves:
            return 0
        probe.push(move)
    if capture not in probe.legal_moves or not probe.is_capture(capture):
        return 0
    return static_exchange(probe, capture)


def _defender_themes(
    work: chess.Board, line: list[chess.Move], index: int
) -> tuple[set[str], list[int]]:
    themes: set[str] = set()
    squares: list[int] = []
    move = line[index]
    if index + 2 >= len(line):
        return themes, squares
    target = line[index + 2].to_square
    ours = work.turn
    theirs = not ours
    before = work.attackers(theirs, target)

    if _later_gain(work, line, index) <= 0:
        return themes, squares

    probe = work.copy(stack=False)
    probe.push(move)
    after_move = probe.attackers(theirs, target)

    if work.is_capture(move) and move.to_square in before:
        themes.add("remove_defender")
        squares.extend([move.to_square, target])
        return themes, squares

    for slider in before:
        if slider in after_move:
            continue
        piece = work.piece_at(slider)
        if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        between = chess.SquareSet(chess.between(slider, target))
        if move.to_square in between:
            themes.add("interference")
            squares.extend([slider, move.to_square, target])
            return themes, squares

    reply = line[index + 1]
    if reply in probe.legal_moves:
        probe.push(reply)
        after_reply = probe.attackers(theirs, target)
        if reply.from_square in before and reply.from_square not in after_reply:
            if reply.to_square not in after_reply:
                themes.add("deflection")
                squares.extend([reply.from_square, reply.to_square, target])
    return themes, squares


def _move_themes(
    work: chess.Board,
    line: list[chess.Move],
    index: int,
    previous_capture: Optional[chess.Square],
) -> tuple[set[str], list[int], bool]:
    move = line[index]
    themes: set[str] = set()
    squares: list[int] = []
    uci = move.uci()

    for fork in forks(work):
        if fork["move"] == uci:
            themes.add("fork")
            squares.extend(chess.parse_square(name) for name in fork["squares"])

    for found in discovered_attacks(work):
        if found["move"] == uci:
            themes.add("discovered_attack")
            squares.extend(chess.parse_square(name) for name in found["squares"])

    if move.promotion is not None:
        themes.add("promotion")
        squares.extend([move.from_square, move.to_square])

    sacrificed = static_exchange(work, move) <= -150 if work.is_capture(move) else False
    if not work.is_capture(move) and move.promotion is None:
        probe = work.copy(stack=False)
        probe.push(move)
        sacrificed = swap_gain(probe, move.to_square) >= 150

    checkmate = False
    probe = work.copy(stack=False)
    probe.push(move)
    if probe.is_checkmate():
        checkmate = True
        themes.add("mate")
        squares.extend([move.from_square, move.to_square])
        king = probe.king(probe.turn)
        if king is not None:
            squares.append(king)
            rank = chess.square_rank(king)
            if rank in (0, 7) and all(
                chess.square_rank(c) == rank for c in probe.checkers()
            ):
                themes.add("back_rank")
    else:
        mover = probe.turn
        after = _with_side_to_move(probe, not mover)
        if after is not None:
            for pin in pins_and_skewers(after):
                if pin["attacker"] == chess.square_name(move.to_square):
                    themes.add(pin["kind"])
                    squares.extend(chess.parse_square(name) for name in pin["squares"])

    if previous_capture is not None:
        recaptures = captures_onto(work, previous_capture)
        if recaptures and move not in recaptures:
            if work.gives_check(move) or work.is_capture(move):
                themes.add("zwischenzug")
                squares.extend([move.from_square, move.to_square, previous_capture])

    defender_themes, defender_squares = _defender_themes(work, line, index)
    themes |= defender_themes
    squares.extend(defender_squares)

    if sacrificed:
        themes.add("sacrifice_candidate")
    return themes, squares, checkmate


def classify_line(board: chess.Board, line: list[chess.Move]) -> dict:
    mover = board.turn
    work = board.copy(stack=False)
    start = material(work, mover)
    themes: set[str] = set()
    squares: list[int] = []
    names: list[str] = []
    captures = 0
    previous_capture: Optional[chess.Square] = None
    last_capture_square: Optional[chess.Square] = None
    last_was_ours_capture = False
    mate = False
    mover_moves = 0

    for index, move in enumerate(line):
        if move not in work.legal_moves:
            break
        ours = work.turn == mover
        names.append(work.san(move))
        capturing = work.is_capture(move)
        if ours:
            mover_moves += 1
            found, spots, checkmate = _move_themes(work, line, index, previous_capture)
            themes |= found
            squares.extend(spots)
            mate = mate or checkmate
        if capturing:
            captures += 1
        previous_capture = move.to_square if (capturing and not ours) else None
        last_was_ours_capture = ours and capturing
        last_capture_square = move.to_square if capturing else None
        work.push(move)

    gain = material(work, mover) - start
    if last_was_ours_capture and last_capture_square is not None and not work.is_game_over():
        gain -= swap_gain(work, last_capture_square)
    if captures >= 3:
        themes.add("capture_chain")

    outcome = "none"
    if work.is_checkmate() and work.turn != mover:
        outcome = "mate"
    elif gain >= settings.tactic_min_gain_cp():
        outcome = "wins_material"
    elif "promotion" in themes:
        outcome = "promotion"

    if "sacrifice_candidate" in themes:
        themes.discard("sacrifice_candidate")
        if outcome in ("mate", "wins_material", "promotion") and gain >= 0:
            themes.add("sacrifice")
    if outcome not in ("mate", "wins_material", "promotion"):
        themes -= {"zwischenzug", "deflection", "remove_defender", "interference"}

    unique: list[str] = []
    for square in squares:
        name = chess.square_name(square)
        if name not in unique:
            unique.append(name)

    return {
        "outcome": outcome,
        "mate_in": mover_moves if outcome == "mate" else None,
        "gain_cp": int(gain),
        "san": names,
        "themes": ordered_themes(themes),
        "squares": unique[:10],
    }


def back_rank_flag(board: chess.Board, color: chess.Color) -> bool:
    return bool(back_rank_weakness(board, color))
