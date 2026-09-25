from __future__ import annotations

from typing import Optional

import chess

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

SEE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}


def piece_name(piece: chess.Piece) -> str:
    return PIECE_NAMES[piece.piece_type]


def pawn_value(piece: Optional[chess.Piece]) -> int:
    if piece is None:
        return 0
    return PIECE_VALUES[piece.piece_type]


def see_value(piece: Optional[chess.Piece]) -> int:
    if piece is None:
        return 0
    return SEE_VALUES[piece.piece_type]
