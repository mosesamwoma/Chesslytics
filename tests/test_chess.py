from __future__ import annotations

import chess
import chess.engine
import pytest

from app.chess.engine import SearchLimit
from app.chess.evaluator import (
    MATE_SCORE_CP,
    MAX_LOSS_CP,
    analyze_games,
    clamp_loss,
    evaluate_game,
    score_to_cp,
    win_percent,
)
from app.chess.features import find_hanging_pieces, game_phase
from app.chess.pgn_parser import game_fingerprint, load_games, parse_pgn
from app.services.analysis_service import (
    SCHEMA_VERSION,
    cache_is_compatible,
    load_cache,
    save_cache,
)
from fake_engine import ScriptedEngine
from helpers import CLOCK_PGN, FOOLS_MATE_PGN, SYNTHETIC_PGN, game_from

LIMIT = SearchLimit("depth", 12)

STALEMATE_PGN = """[White "A"]
[Black "B"]
[SetUp "1"]
[FEN "k7/8/8/2Q5/8/8/8/7K w - - 0 1"]

1. Qb6 *
"""


def analyze(text: str, engine) -> dict:
    return evaluate_game(game_from(text), engine, LIMIT)


def test_scores_are_reported_from_the_movers_perspective():
    report = analyze(CLOCK_PGN, ScriptedEngine(default_cp=100))

    first = report["moves"][0]
    assert first["color"] == "white"
    assert first["eval_before_cp"] == 100
    assert first["eval_after_cp"] == -100
    assert first["loss_cp"] == 200


def test_metadata_is_read_from_the_headers():
    report = analyze(CLOCK_PGN, ScriptedEngine())

    assert report["metadata"]["white"] == "Alice"
    assert report["metadata"]["black"] == "Bob"
    assert report["metadata"]["fingerprint"] == game_fingerprint(game_from(CLOCK_PGN))


def test_mate_scores_use_the_ceiling_and_keep_their_sign():
    ahead = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    behind = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)

    assert score_to_cp(ahead, chess.WHITE) == (MATE_SCORE_CP, 3)
    assert score_to_cp(behind, chess.WHITE) == (-MATE_SCORE_CP, -2)


def test_a_missed_mate_is_measured_as_a_maximum_loss():
    engine = ScriptedEngine(script={chess.STARTING_FEN: {"mate": 1, "best": "d1h5"}})
    record = analyze(CLOCK_PGN, engine)["moves"][0]

    assert record["eval_before_mate"] == 1
    assert record["eval_before_cp"] == MATE_SCORE_CP
    assert record["loss_cp"] == MAX_LOSS_CP
    assert record["best_move_was_mate"] is True


def test_win_percent_is_fifty_at_equality_and_symmetric():
    assert win_percent(0) == 50.0
    assert round(win_percent(150) + win_percent(-150), 9) == 100.0
    assert win_percent(2000) > 99.0
    assert win_percent(-2000) < 1.0


def test_loss_is_clamped_to_a_sane_ceiling():
    assert clamp_loss(50) == 50
    assert clamp_loss(999_999) == MAX_LOSS_CP
    assert clamp_loss(-999_999) == -MAX_LOSS_CP


def test_the_thinking_clock_is_the_parent_node():
    moves = analyze(CLOCK_PGN, ScriptedEngine())["moves"]

    assert moves[0]["clock_before"] is None
    assert moves[0]["clock_after"] == 598.0
    assert moves[2]["san"] == "Nf3"
    assert moves[2]["clock_before"] == 597.0
    assert moves[2]["clock_after"] == 590.0


def test_a_finished_game_is_not_sent_to_the_engine_again():
    engine = ScriptedEngine()
    report = analyze(FOOLS_MATE_PGN, engine)

    assert len(report["moves"]) == 4
    assert engine.call_count == 7

    last = report["moves"][3]
    assert last["is_mate"] is True
    assert last["eval_after_cp"] == MATE_SCORE_CP
    assert last["eval_after_mate"] == 0
    assert last["loss_cp"] == 0


def test_a_stalemating_move_is_evaluated_once():
    engine = ScriptedEngine()
    report = analyze(STALEMATE_PGN, engine)

    assert len(report["moves"]) == 1
    assert engine.call_count == 1
    assert report["moves"][0]["eval_after_cp"] == 0
    assert report["moves"][0]["eval_after_mate"] is None


def test_an_engine_failure_is_recorded_and_never_invented():
    engine = ScriptedEngine(script={chess.STARTING_FEN: {"error": RuntimeError("boom")}})
    report = analyze(CLOCK_PGN, engine)

    assert len(report["moves"]) == 3
    for move in report["moves"]:
        assert "boom" in move["error"]
        assert "eval_before_cp" not in move


def test_a_malformed_game_is_skipped_and_the_rest_survive():
    text = (
        '[White "C"]\n[Black "D"]\n\n1. e4 e5 2. Kd3 *\n\n'
        '[White "A"]\n[Black "B"]\n\n1. e4 e5 *\n'
    )
    games, errors = parse_pgn(text)

    assert [game.headers["White"] for game in games] == ["A"]
    assert len(errors) == 1
    assert "game #1" in errors[0]


def test_load_games_rejects_a_missing_file():
    with pytest.raises(FileNotFoundError):
        load_games("tests/data/definitely-not-here.pgn")


def test_a_hanging_piece_is_detected_when_the_capture_is_legal():
    board = chess.Board("4k3/8/4p3/3Q4/8/8/8/4K3 b - - 0 1")
    hung = find_hanging_pieces(board, chess.WHITE)

    assert len(hung) == 1
    assert hung[0]["square"] == "d5"
    assert hung[0]["piece"] == "Q"
    assert hung[0]["name"] == "queen"
    assert hung[0]["cheapest_attacker"] == 1
    assert hung[0]["defended"] is False


def test_a_pinned_attacker_does_not_make_a_piece_hanging():
    board = chess.Board("4k3/8/2p5/1B1Q4/8/8/8/4K3 b - - 0 1")

    assert board.attackers(chess.BLACK, chess.D5) == chess.SquareSet([chess.C6])
    assert find_hanging_pieces(board, chess.WHITE) == []


def test_a_piece_no_one_can_legally_take_is_not_hanging():
    board = chess.Board("4k3/8/4p3/8/3P4/8/8/4K3 b - - 0 1")

    assert find_hanging_pieces(board, chess.WHITE) == []


def test_a_defended_piece_is_still_reported_and_says_so():
    board = chess.Board("7k/8/4p3/3N4/4K3/8/8/8 b - - 0 1")
    hung = find_hanging_pieces(board, chess.WHITE)

    assert len(hung) == 1
    assert hung[0]["name"] == "knight"
    assert hung[0]["defended"] is True


def test_phase_is_derived_from_material_and_move_number():
    start = chess.Board()
    assert game_phase(start, 1) == "opening"
    assert game_phase(start, 20) == "middlegame"

    endgame = chess.Board("8/8/4k3/8/8/4K3/8/7R w - - 0 1")
    assert game_phase(endgame, 1) == "endgame"


def test_fingerprints_are_stable_and_content_sensitive():
    same = game_fingerprint(game_from(SYNTHETIC_PGN))
    assert same == game_fingerprint(game_from(SYNTHETIC_PGN))

    changed = game_fingerprint(game_from(SYNTHETIC_PGN.replace("Nf3", "Nc3")))
    assert changed != same


def test_analysis_reuses_cached_games_without_touching_the_engine():
    games, _ = parse_pgn(SYNTHETIC_PGN)
    first = ScriptedEngine()
    results, counts = analyze_games(games, first, LIMIT)

    assert counts["games_analyzed"] == 1
    assert counts["moves_reused"] == 0
    assert first.call_count == 8

    second = ScriptedEngine()
    again, reused = analyze_games(games, second, LIMIT, cache={"games": results})

    assert reused["games_reused"] == 1
    assert reused["games_analyzed"] == 0
    assert reused["moves_reused"] == 4
    assert second.call_count == 0
    assert again == results


def test_cache_roundtrips_through_disk(tmp_path):
    games, _ = parse_pgn(SYNTHETIC_PGN)
    results, _ = analyze_games(games, ScriptedEngine(), LIMIT)
    path = tmp_path / "cache.json"

    save_cache(results, "Stockfish 18", SearchLimit("time", 0.05), path=str(path))
    cache = load_cache(str(path))

    assert cache["games"] == results
    assert cache["meta"]["schema_version"] == SCHEMA_VERSION
    assert cache["meta"]["engine"] == "Stockfish 18"
    assert cache["meta"]["limit"] == {"type": "time", "value": 0.05}


def test_the_cache_key_ignores_thresholds_but_not_search_depth(tmp_path):
    path = tmp_path / "cache.json"
    save_cache({}, "Stockfish 18", SearchLimit("depth", 12), path=str(path))
    cache = load_cache(str(path))

    assert cache_is_compatible(cache, "Stockfish 18", SearchLimit("depth", 12))
    assert not cache_is_compatible(cache, "Stockfish 18", SearchLimit("depth", 14))
    assert not cache_is_compatible(cache, "Stockfish 17", SearchLimit("depth", 12))


def test_a_corrupt_cache_is_ignored_rather_than_fatal(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json at all", encoding="utf-8")

    assert load_cache(str(path)) == {}
    assert load_cache(str(tmp_path / "absent.json")) == {}
