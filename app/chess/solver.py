from __future__ import annotations

from typing import Optional

import chess

from app import settings


class BudgetExceeded(Exception):
    pass


class _Search:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.nodes = 0

    def tick(self) -> None:
        self.nodes += 1
        if self.nodes > self.budget:
            raise BudgetExceeded()


def _ordered(board: chess.Board) -> list[chess.Move]:
    moves = list(board.legal_moves)
    moves.sort(key=lambda move: (not board.gives_check(move), not board.is_capture(move)))
    return moves


def _mate_in(
    board: chess.Board, attacker: chess.Color, plies: int, search: _Search, root: bool
) -> Optional[list[chess.Move]]:
    if plies == 1:
        for move in board.legal_moves:
            if not board.gives_check(move):
                continue
            search.tick()
            board.push(move)
            try:
                if board.is_checkmate():
                    return [move]
            finally:
                board.pop()
        return None

    for move in _ordered(board):
        checking = board.gives_check(move)
        if not checking and not (plies == 3 and root):
            continue
        search.tick()
        board.push(move)
        try:
            replies = list(board.legal_moves)
            if not replies:
                if board.is_checkmate():
                    return [move]
                continue
            principal: Optional[list[chess.Move]] = None
            refuted = False
            for reply in replies:
                search.tick()
                board.push(reply)
                try:
                    follow = _mate_in(board, attacker, plies - 2, search, False)
                finally:
                    board.pop()
                if follow is None:
                    refuted = True
                    break
                if principal is None or len(follow) > len(principal) - 1:
                    principal = [reply] + follow
            if not refuted and principal is not None:
                return [move] + principal
        finally:
            board.pop()
    return None


def forced_mate(
    board: chess.Board, attacker: chess.Color, max_moves: Optional[int] = None
) -> Optional[list[chess.Move]]:
    limit = max_moves if max_moves is not None else settings.solver_max_mate()
    if board.turn != attacker or board.is_game_over():
        return None
    work = board.copy(stack=False)
    search = _Search(settings.solver_node_budget())
    try:
        for moves in range(1, max(1, min(limit, 3)) + 1):
            line = _mate_in(work, attacker, 2 * moves - 1, search, True)
            if line is not None:
                return line
    except BudgetExceeded:
        return None
    return None


def line_to_san(board: chess.Board, line: list[chess.Move]) -> list[str]:
    work = board.copy(stack=False)
    names = []
    for move in line:
        if move not in work.legal_moves:
            break
        names.append(work.san(move))
        work.push(move)
    return names
