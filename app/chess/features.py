from __future__ import annotations

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


def material_balance(board: chess.Board) -> dict:
    totals = {chess.WHITE: 0, chess.BLACK: 0}
    for piece in board.piece_map().values():
        totals[piece.color] += PIECE_VALUES[piece.piece_type]
    return {
        "white": totals[chess.WHITE],
        "black": totals[chess.BLACK],
        "difference": totals[chess.WHITE] - totals[chess.BLACK],
    }


def piece_counts(board: chess.Board) -> dict:
    counts: dict[str, int] = {}
    for piece in board.piece_map().values():
        symbol = piece.symbol()
        counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def game_phase(board: chess.Board, move_number: int) -> str:
    non_pawn_material = 0
    piece_count = 0
    for piece in board.piece_map().values():
        piece_count += 1
        if piece.piece_type not in (chess.PAWN, chess.KING):
            non_pawn_material += PIECE_VALUES[piece.piece_type]

    if non_pawn_material <= 13 or piece_count <= 10:
        return "endgame"
    if move_number <= 12:
        return "opening"
    return "middlegame"


def find_hanging_pieces(board: chess.Board, color: chess.Color) -> list[dict]:
    opponent = not color
    capturable = {
        move.to_square for move in board.legal_moves if board.is_capture(move)
    }

    result: list[dict] = []
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        if square not in capturable:
            continue

        attacker_squares = board.attackers(opponent, square)
        if not attacker_squares:
            continue

        piece_value = PIECE_VALUES[piece.piece_type]
        cheapest = min(
            PIECE_VALUES[board.piece_at(square_).piece_type]
            for square_ in attacker_squares
        )
        if cheapest >= piece_value:
            continue

        defenders = board.attackers(color, square)
        result.append(
            {
                "square": chess.square_name(square),
                "piece": piece.symbol(),
                "name": PIECE_NAMES[piece.piece_type],
                "value": piece_value,
                "cheapest_attacker": cheapest,
                "attackers": len(attacker_squares),
                "defended": bool(defenders),
            }
        )

    result.sort(key=lambda item: -item["value"])
    return result


def is_mate_move(board: chess.Board, move: chess.Move) -> bool:
    if move not in board.legal_moves:
        return False
    board.push(move)
    try:
        return board.is_checkmate()
    finally:
        board.pop()


def king_safety(board: chess.Board, color: chess.Color) -> dict:
    king_square = board.king(color)
    if king_square is None:
        return {
            "king_square": None,
            "attacked_ring": 0,
            "ring_size": 0,
            "on_back_rank": False,
        }

    ring = chess.SquareSet(chess.BB_KING_ATTACKS[king_square])
    opponent = not color
    attacked = sum(1 for square in ring if board.is_attacked_by(opponent, square))

    return {
        "king_square": chess.square_name(king_square),
        "attacked_ring": attacked,
        "ring_size": len(ring),
        "on_back_rank": chess.square_rank(king_square) in (0, 7),
    }


def castling_rights(board: chess.Board) -> dict:
    return {
        "white_kingside": board.has_kingside_castling_rights(chess.WHITE),
        "white_queenside": board.has_queenside_castling_rights(chess.WHITE),
        "black_kingside": board.has_kingside_castling_rights(chess.BLACK),
        "black_queenside": board.has_queenside_castling_rights(chess.BLACK),
    }


def move_facts(board: chess.Board, move: chess.Move) -> dict:
    return {
        "is_capture": board.is_capture(move),
        "is_check": board.gives_check(move),
        "is_promotion": move.promotion is not None,
        "is_castling": board.is_castling(move),
        "is_en_passant": board.is_en_passant(move),
    }
