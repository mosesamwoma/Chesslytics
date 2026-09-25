from __future__ import annotations

import os

import chess
import pytest

from app.chess.engine import ChessEngine, SearchLimit, find_stockfish
from app.chess.evaluator import analyze_games
from app.chess.pgn_parser import load_games
from app.mining.mistake_detector import MinerConfig
from app.mining.pattern_miner import mine_patterns

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "data", "sample_games.pgn")
DEPTH = 10


@pytest.fixture(scope="module")
def analyzed():
    try:
        path = find_stockfish()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))

    games, errors = load_games(SAMPLE)
    assert errors == []
    assert len(games) == 3

    limit = SearchLimit("depth", DEPTH)
    engine = ChessEngine(path, limit)
    with engine:
        results, counts = analyze_games(games, engine, limit)

    assert counts["games_analyzed"] == 3
    return results


@pytest.fixture(scope="module")
def report(analyzed):
    return mine_patterns(analyzed, MinerConfig())


def test_the_scholars_mate_blunder_is_detected(report):
    black = [
        item
        for item in report["mistakes"]
        if item["game_id"] == 1 and item["color"] == "black"
    ]
    assert black

    worst = max(black, key=lambda item: item["loss_cp"])
    assert worst["move_number"] == 3
    assert worst["severity"] == "blunder"
    assert worst["best_move"]


def test_the_queen_blunder_in_the_bullet_game_is_detected(report):
    white = [
        item
        for item in report["mistakes"]
        if item["game_id"] == 2 and item["color"] == "white"
    ]
    assert white

    worst = max(white, key=lambda item: item["loss_cp"])
    assert worst["move_number"] == 3
    assert worst["severity"] == "blunder"


def test_quiet_book_theory_produces_no_blunders(report):
    game3 = [item for item in report["mistakes"] if item["game_id"] == 3]
    blunders = [item for item in game3 if item["severity"] == "blunder"]

    assert blunders == []


def test_clocks_are_read_from_real_chess_com_annotations(report):
    assert report["context"]["games_with_clock"] == 3

    game2 = [item for item in report["mistakes"] if item["game_id"] == 2]
    assert game2
    assert all(item["time_remaining"] is not None for item in game2)


def test_time_pressure_is_identified_in_the_bullet_game(report):
    game2 = [item for item in report["mistakes"] if item["game_id"] == 2]

    assert [item for item in game2 if item["in_time_pressure"]]


def test_the_mating_move_is_never_reported_as_a_mistake(analyzed):
    report = mine_patterns(analyzed, MinerConfig(min_loss=0.1, ignore_decided=False))
    mating = [
        item for item in report["mistakes"] if (item["played_move"] or "").endswith("#")
    ]

    assert mating == []


def test_every_mistake_carries_a_valid_position_and_a_suggested_move(analyzed):
    report = mine_patterns(analyzed, MinerConfig(min_loss=0.5))

    assert report["mistakes"]
    for mistake in report["mistakes"]:
        board = chess.Board(mistake["fen"])
        assert board.is_valid()
        assert mistake["best_move"]
        assert mistake["category_basis"].strip()


def test_a_real_game_scores_every_move(analyzed):
    for game in analyzed.values():
        moves = game["moves"]
        assert moves
        assert all(move.get("error") is None for move in moves)
        assert all(move.get("fen_before") for move in moves)
