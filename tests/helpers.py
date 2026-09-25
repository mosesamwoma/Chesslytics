from __future__ import annotations

import io

import chess
import chess.pgn

CLOCK_PGN = """[Event "Test"]
[White "Alice"]
[Black "Bob"]
[Result "*"]

1. e4 {[%clk 0:09:58]} e5 {[%clk 0:09:57]} 2. Nf3 {[%clk 0:09:50]} *
"""

SYNTHETIC_PGN = '[White "Alice"]\n[Black "Bob"]\n\n1. e4 e5 2. Nf3 Nc6 *\n'

FOOLS_MATE_PGN = '[White "A"]\n[Black "B"]\n\n1. f3 e5 2. g4 Qh4# *\n'


def game_from(text: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(io.StringIO(text))
    assert game is not None
    return game


def fen_after(*moves: str) -> str:
    board = chess.Board()
    for move in moves:
        board.push_san(move)
    return board.fen()
