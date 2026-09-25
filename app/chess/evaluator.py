from __future__ import annotations

import math
from typing import Any, Optional

import chess
import chess.engine
import chess.pgn

from app.chess.engine import Engine, SearchLimit
from app.chess.features import (
    castling_rights,
    find_hanging_pieces,
    game_phase,
    is_mate_move,
    king_safety,
    material_balance,
    move_facts,
)
from app.chess.pgn_parser import clock_of, game_fingerprint, game_metadata

MATE_SCORE_CP = 10_000
MAX_LOSS_CP = 2_000


def score_to_cp(
    pov_score: chess.engine.PovScore, color: chess.Color
) -> tuple[int, Optional[int]]:
    score = pov_score.pov(color)
    if score.is_mate():
        return score.score(mate_score=MATE_SCORE_CP), score.mate()
    return score.score(), None


def win_percent(cp: int) -> float:
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def clamp_loss(loss_cp: int) -> int:
    return max(-MAX_LOSS_CP, min(MAX_LOSS_CP, loss_cp))


def evaluate_move(
    board: chess.Board,
    node: chess.pgn.GameNode,
    engine: Engine,
    limit: SearchLimit,
) -> dict:
    move = node.move
    color = board.turn
    move_number = board.fullmove_number
    engine_limit = limit.to_engine_limit()

    record: dict[str, Any] = {
        "ply": board.ply() + 1,
        "move_number": move_number,
        "color": "white" if color == chess.WHITE else "black",
        "san": board.san(move),
        "uci": move.uci(),
        "fen_before": board.fen(),
        "phase": game_phase(board, move_number),
        "clock_before": clock_of(node.parent),
        "clock_after": clock_of(node),
        "material_before": material_balance(board),
        "king_safety_before": king_safety(board, color),
        "castling_rights_before": castling_rights(board),
        "error": None,
    }
    record.update(move_facts(board, move))

    try:
        info_before = engine.analyse(board, engine_limit)
        eval_before, mate_before = score_to_cp(info_before["score"], color)
        pv = info_before.get("pv") or []
        best_move = pv[0] if pv else None

        board.push(move)
        try:
            record["is_mate"] = board.is_checkmate()
            record["fen_after"] = board.fen()
            record["material_after"] = material_balance(board)

            if board.is_checkmate():
                eval_after, mate_after = MATE_SCORE_CP, 0
            elif board.is_game_over():
                eval_after, mate_after = 0, None
            else:
                info_after = engine.analyse(board, engine_limit)
                eval_after, mate_after = score_to_cp(info_after["score"], color)

            record["hanging_after"] = find_hanging_pieces(board, color)
            record["king_safety_after"] = king_safety(board, color)
        finally:
            board.pop()

        if best_move is not None and best_move != move:
            record["best_move_was_capture"] = board.is_capture(best_move)
            record["best_move_was_check"] = board.gives_check(best_move)
            record["best_move_was_mate"] = is_mate_move(board, best_move)
        else:
            record["best_move_was_capture"] = False
            record["best_move_was_check"] = False
            record["best_move_was_mate"] = False

        loss_cp = clamp_loss(eval_before - eval_after)
        record.update(
            eval_before_cp=eval_before,
            eval_before_mate=mate_before,
            eval_after_cp=eval_after,
            eval_after_mate=mate_after,
            loss_cp=loss_cp,
            winpct_before=win_percent(eval_before),
            winpct_after=win_percent(eval_after),
            best_move_uci=best_move.uci() if best_move else None,
            best_move_san=(
                board.san(best_move)
                if best_move is not None and best_move in board.legal_moves
                else None
            ),
            depth_reached=info_before.get("depth"),
        )

    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"

    return record


def evaluate_game(game: chess.pgn.Game, engine: Engine, limit: SearchLimit) -> dict:
    board = game.board()
    moves: list[dict] = []

    for node in game.mainline():
        if node.move is None:
            continue
        if board.is_game_over(claim_draw=False):
            break
        if node.move not in board.legal_moves:
            moves.append(
                {
                    "ply": board.ply() + 1,
                    "move_number": board.fullmove_number,
                    "san": None,
                    "uci": node.move.uci(),
                    "error": f"illegal move in PGN: {node.move.uci()}",
                }
            )
            break

        moves.append(evaluate_move(board, node, engine, limit))
        board.push(node.move)

    return {
        "metadata": game_metadata(game),
        "moves": moves,
    }


def analyze_games(
    games: list[chess.pgn.Game],
    engine: Engine,
    limit: SearchLimit,
    cache: Optional[dict] = None,
    progress=None,
) -> tuple[dict[str, dict], dict]:
    notify = progress or (lambda _message: None)
    cached = (cache or {}).get("games", {})
    results: dict[str, dict] = {}
    counts = {"games_analyzed": 0, "games_reused": 0, "moves_analyzed": 0, "moves_reused": 0}

    total = len(games)
    for position, game in enumerate(games, start=1):
        fingerprint = game_fingerprint(game)
        if fingerprint in cached:
            results[fingerprint] = cached[fingerprint]
            counts["games_reused"] += 1
            counts["moves_reused"] += len(cached[fingerprint].get("moves", []))
            notify(f"[{position}/{total}] cached")
            continue

        metadata = game_metadata(game)
        notify(f"[{position}/{total}] analyzing {metadata['white']} vs {metadata['black']}")
        results[fingerprint] = evaluate_game(game, engine, limit)
        counts["games_analyzed"] += 1
        counts["moves_analyzed"] += len(results[fingerprint]["moves"])

    return results, counts
