from __future__ import annotations

import multiprocessing
import queue
from concurrent.futures import ProcessPoolExecutor, wait
import math
from typing import Any, Optional

import chess
import chess.engine
import chess.pgn

from app.chess.engine import ChessEngine, Engine, SearchLimit
from app.chess.features import (
    castling_rights,
    find_hanging_pieces,
    game_phase,
    hanging_before,
    is_mate_move,
    king_safety,
    material_balance,
    move_facts,
)
from app.chess.motifs import detect_motifs
from app.chess.pgn_parser import clock_of, game_fingerprint, game_metadata

MATE_SCORE_CP = 10_000
MAX_LOSS_CP = 2_000
WORKER_THREADS = 1
START_METHOD = "spawn"
CLEAR_HASH = {"Clear Hash": None}

_PROGRESS = None


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
        record["hanging_before"] = hanging_before(board, color)
        record["motifs_before"] = detect_motifs(board, color)
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
            record["motifs_allowed"] = detect_motifs(board, board.turn)
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


def split_cache(
    games: list[chess.pgn.Game], cached: dict, notify
) -> tuple[dict[str, dict], dict, list[tuple[int, str, chess.pgn.Game]]]:
    results: dict[str, dict] = {}
    counts = {
        "games_analyzed": 0,
        "games_reused": 0,
        "moves_analyzed": 0,
        "moves_reused": 0,
        "failures": [],
    }
    pending: list[tuple[int, str, chess.pgn.Game]] = []
    total = len(games)

    for position, game in enumerate(games, start=1):
        fingerprint = game_fingerprint(game)
        if fingerprint in cached:
            results[fingerprint] = cached[fingerprint]
            counts["games_reused"] += 1
            counts["moves_reused"] += len(cached[fingerprint].get("moves", []))
            notify(f"[{position}/{total}] cached")
            continue
        pending.append((position, fingerprint, game))

    return results, counts, pending


def analyze_games(
    games: list[chess.pgn.Game],
    engine: Engine,
    limit: SearchLimit,
    cache: Optional[dict] = None,
    progress=None,
) -> tuple[dict[str, dict], dict]:
    notify = progress or (lambda _message: None)
    cached = (cache or {}).get("games", {})
    results, counts, pending = split_cache(games, cached, notify)
    total = len(games)

    for position, fingerprint, game in pending:
        metadata = game_metadata(game)
        notify(f"[{position}/{total}] analyzing {metadata['white']} vs {metadata['black']}")
        results[fingerprint] = evaluate_game(game, engine, limit)
        counts["games_analyzed"] += 1
        counts["moves_analyzed"] += len(results[fingerprint]["moves"])

    return results, counts


def _init_worker(updates) -> None:
    global _PROGRESS
    _PROGRESS = updates


def _report(message: str) -> None:
    if _PROGRESS is not None:
        try:
            _PROGRESS.put(message)
        except Exception:
            pass


def _game_plies(game: chess.pgn.Game) -> int:
    try:
        return game.end().ply()
    except Exception:
        return 0


def split_slices(
    pending: list[tuple[int, str, chess.pgn.Game]], workers: int
) -> list[list[tuple[int, str, chess.pgn.Game]]]:
    bins: list[list[tuple[int, str, chess.pgn.Game]]] = [
        [] for _ in range(max(1, workers))
    ]
    load = [0] * len(bins)
    longest_first = sorted(
        range(len(pending)), key=lambda index: (-_game_plies(pending[index][2]), index)
    )
    for index in longest_first:
        _position, _fingerprint, game = pending[index]
        target = min(range(len(bins)), key=lambda slot: (load[slot], slot))
        bins[target].append(pending[index])
        load[target] += _game_plies(game)
    return [sorted(slot, key=lambda item: item[0]) for slot in bins if slot]


def _analyze_slice(task: tuple) -> tuple[list, list]:
    entries, engine_path, kind, value = task
    limit = SearchLimit(kind, value)
    results: list[tuple[str, dict]] = []
    failures: list[tuple[str, str]] = []

    try:
        engine = ChessEngine(engine_path, limit, threads=WORKER_THREADS).start()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return [], [(fingerprint, error) for _position, fingerprint, _game in entries]

    try:
        for _position, fingerprint, game in entries:
            try:
                engine.configure(CLEAR_HASH)
                payload = evaluate_game(game, engine, limit)
            except Exception as exc:
                failures.append((fingerprint, f"{type(exc).__name__}: {exc}"))
                continue
            results.append((fingerprint, payload))
            metadata = payload.get("metadata") or {}
            _report(f"{metadata.get('white')} vs {metadata.get('black')}")
    finally:
        engine.close()

    return results, failures


def drain(updates, notify, counter: list[int], total: int) -> None:
    while True:
        try:
            message = updates.get_nowait()
        except queue.Empty:
            return
        except (OSError, ValueError):
            return
        counter[0] += 1
        notify(f"[{counter[0]}/{total}] analyzed {message}")


def analyze_games_parallel(
    games: list[chess.pgn.Game],
    engine_path: str,
    limit: SearchLimit,
    cache: Optional[dict] = None,
    progress=None,
    workers: int = 2,
) -> tuple[dict[str, dict], dict]:
    notify = progress or (lambda _message: None)
    cached = (cache or {}).get("games", {})
    results, counts, pending = split_cache(games, cached, notify)

    if not pending:
        return results, counts

    slices = split_slices(pending, workers)
    total = len(pending)
    fresh: dict[str, dict] = {}
    failures: list[str] = []
    counter = [0]
    context = multiprocessing.get_context(START_METHOD)
    updates = None
    try:
        updates = context.Queue()
    except Exception:
        updates = None

    with ProcessPoolExecutor(
        max_workers=len(slices),
        mp_context=context,
        initializer=_init_worker,
        initargs=(updates,),
    ) as pool:
        submitted = {
            pool.submit(
                _analyze_slice, (entries, engine_path, limit.kind, limit.value)
            ): entries
            for entries in slices
        }
        remaining = set(submitted)
        while remaining:
            done, remaining = wait(remaining, timeout=0.2)
            if updates is not None:
                drain(updates, notify, counter, total)
            for future in done:
                try:
                    slice_results, slice_failures = future.result()
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    for _position, fingerprint, _game in submitted[future]:
                        failures.append(f"{fingerprint}: {error}")
                    notify(f"warning: a worker stopped early: {error}")
                    continue
                for fingerprint, payload in slice_results:
                    fresh[fingerprint] = payload
                for fingerprint, error in slice_failures:
                    failures.append(f"{fingerprint}: {error}")

    if updates is not None:
        drain(updates, notify, counter, total)
        try:
            updates.close()
            updates.join_thread()
        except Exception:
            pass

    for _position, fingerprint, _game in pending:
        if fingerprint in fresh:
            results[fingerprint] = fresh[fingerprint]
            counts["games_analyzed"] += 1
            counts["moves_analyzed"] += len(fresh[fingerprint].get("moves") or [])

    counts["failures"] = failures
    return results, counts
