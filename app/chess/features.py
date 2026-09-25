from __future__ import annotations

import chess

from app.chess.pieces import PIECE_NAMES, PIECE_VALUES
from app.chess.see import static_exchange


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


def _en_passant_victim_square(move: chess.Move) -> chess.Square:
    return chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))


def find_hanging_pieces(board: chess.Board, color: chess.Color) -> list[dict]:
    opponent = not color
    best_by_square: dict[chess.Square, dict] = {}

    for move in board.legal_moves:
        if not board.is_capture(move):
            continue
        square = move.to_square
        victim = (
            board.piece_at(_en_passant_victim_square(move))
            if board.is_en_passant(move)
            else board.piece_at(square)
        )
        if victim is None or victim.color != color or victim.piece_type == chess.KING:
            continue

        gain = static_exchange(board, move)
        if gain <= 0:
            continue
        if square in best_by_square and best_by_square[square]["see"] >= gain:
            continue

        attackers = board.attackers(opponent, square)
        defenders = board.attackers(color, square)
        best_by_square[square] = {
            "square": chess.square_name(square),
            "piece": victim.symbol(),
            "name": PIECE_NAMES[victim.piece_type],
            "value": PIECE_VALUES[victim.piece_type],
            "see": gain,
            "see_pawns": round(gain / 100.0, 2),
            "cheapest_attacker": min(
                (PIECE_VALUES[board.piece_at(square_).piece_type] for square_ in attackers),
                default=0,
            ),
            "attackers": len(attackers),
            "defended": bool(defenders),
            "winning_capture": move.uci(),
        }

    return sorted(
        best_by_square.values(), key=lambda item: (-item["see"], item["square"])
    )


def hanging_before(board: chess.Board, color: chess.Color) -> list[dict]:
    probe = board.copy(stack=False)
    if probe.is_check() or probe.is_game_over():
        return []
    probe.push(chess.Move.null())
    return find_hanging_pieces(probe, color)


def newly_hanging(before: list[dict], after: list[dict]) -> list[dict]:
    seen = {(item["square"], item["piece"]) for item in before}
    return [item for item in after if (item["square"], item["piece"]) not in seen]


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
