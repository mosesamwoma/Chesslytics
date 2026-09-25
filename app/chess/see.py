from __future__ import annotations

from typing import Optional

import chess

from app.chess.pieces import SEE_VALUES, see_value

MAX_SWAP_DEPTH = 32


def captures_onto(board: chess.Board, square: chess.Square) -> list[chess.Move]:
    moves = [
        move
        for move in board.legal_moves
        if move.to_square == square and board.is_capture(move)
    ]
    moves.sort(key=lambda move: _capturer_value(board, move))
    return moves


def _capturer_value(board: chess.Board, move: chess.Move) -> int:
    if move.promotion is not None:
        return SEE_VALUES[move.promotion]
    return see_value(board.piece_at(move.from_square))


def victim_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return SEE_VALUES[chess.PAWN]
    return see_value(board.piece_at(move.to_square))


def promotion_gain(move: chess.Move) -> int:
    if move.promotion is None:
        return 0
    return SEE_VALUES[move.promotion] - SEE_VALUES[chess.PAWN]


def swap_gain(board: chess.Board, square: chess.Square, depth: int = 0) -> int:
    if depth >= MAX_SWAP_DEPTH:
        return 0

    best = 0
    for move in captures_onto(board, square):
        immediate = victim_value(board, move) + promotion_gain(move)
        if immediate <= best:
            continue
        board.push(move)
        try:
            gain = immediate - swap_gain(board, square, depth + 1)
        finally:
            board.pop()
        if gain > best:
            best = gain
    return best


def static_exchange(board: chess.Board, move: chess.Move) -> int:
    if move not in board.legal_moves:
        return 0

    capturing = board.is_capture(move)
    if not capturing and move.promotion is None:
        return 0

    work = board.copy(stack=False)
    square = move.to_square
    victim = victim_value(work, move) if capturing else 0

    work.push(move)
    return victim + promotion_gain(move) - swap_gain(work, square)


def best_exchange(
    board: chess.Board, square: chess.Square
) -> tuple[int, Optional[chess.Move]]:
    best_gain = 0
    best_move: Optional[chess.Move] = None
    for move in captures_onto(board, square):
        gain = static_exchange(board, move)
        if gain > best_gain:
            best_gain = gain
            best_move = move
    return best_gain, best_move
