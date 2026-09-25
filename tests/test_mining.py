from __future__ import annotations

from app.chess.evaluator import clamp_loss, win_percent
from app.mining.mistake_detector import (
    MinerConfig,
    build_records,
    is_decided,
    move_bucket,
    player_color,
    severity_for,
)
from app.mining.pattern_miner import mine_patterns
from app.mining.profiler import build_profile, build_observations

HUNG_QUEEN = {
    "square": "d5",
    "piece": "Q",
    "name": "queen",
    "value": 9,
    "cheapest_attacker": 1,
    "attackers": 1,
    "defended": False,
}


def cached_move(ply, move_number, color, before, after, **extra):
    record = {
        "ply": ply,
        "move_number": move_number,
        "color": color,
        "san": "Qh5",
        "uci": "d1h5",
        "fen_before": "8/8/8/8/8/8/8/8 w - - 0 1",
        "phase": "opening",
        "loss_cp": clamp_loss(before - after),
        "eval_before_cp": before,
        "eval_after_cp": after,
        "winpct_before": win_percent(before),
        "winpct_after": win_percent(after),
        "clock_before": None,
        "clock_after": None,
        "error": None,
    }
    record.update(extra)
    return record


def cached_game(moves, fingerprint="g1", **headers):
    metadata = {
        "white": "Me",
        "black": "Them",
        "result": "*",
        "date": "2024.01.01",
        "opening": "Test Opening",
    }
    metadata.update(headers)
    return {fingerprint: {"metadata": metadata, "moves": moves}}


def merge(*games):
    merged = {}
    for game in games:
        merged.update(game)
    return merged


def test_severity_bands_follow_the_configured_thresholds():
    config = MinerConfig()

    assert severity_for(0.49, config) == "normal"
    assert severity_for(0.5, config) == "inaccuracy"
    assert severity_for(0.99, config) == "inaccuracy"
    assert severity_for(1.0, config) == "mistake"
    assert severity_for(1.99, config) == "mistake"
    assert severity_for(2.0, config) == "blunder"


def test_severity_thresholds_are_configurable():
    config = MinerConfig(inaccuracy=1.0, mistake=2.0, blunder=3.0)

    assert severity_for(1.5, config) == "inaccuracy"
    assert severity_for(2.5, config) == "mistake"
    assert severity_for(3.0, config) == "blunder"


def test_move_buckets_cover_the_whole_game():
    assert move_bucket(1) == "1-10"
    assert move_bucket(10) == "1-10"
    assert move_bucket(11) == "11-20"
    assert move_bucket(45) == "41+"


def test_player_matching_is_case_insensitive():
    metadata = {"white": "Me", "black": "Them"}

    assert player_color(metadata, "me") == "white"
    assert player_color(metadata, " THEM ") == "black"
    assert player_color(metadata, "nobody") is None


def test_a_clean_run_reports_nothing_at_all():
    games = cached_game(
        [
            cached_move(1, 1, "white", 20, 15),
            cached_move(2, 1, "black", -10, -12),
        ]
    )
    report = mine_patterns(games, MinerConfig())

    assert report["mistakes"] == []
    assert report["largest"] is None
    assert report["context"]["moves_scored"] == 2
    assert report["context"]["excluded_decided"] == 0


def test_a_blunder_carries_its_own_reasoning():
    games = cached_game([cached_move(1, 1, "white", 50, -250)])
    mistake = mine_patterns(games, MinerConfig())["mistakes"][0]

    assert mistake["severity"] == "blunder"
    assert mistake["loss"] == 3.0
    assert mistake["loss_cp"] == 300
    assert mistake["category"] == "opening"
    assert mistake["category_basis"]
    assert mistake["game_id"] == 1
    assert mistake["game_key"] == "g1"
    assert mistake["player"] == "Me"
    assert mistake["opponent"] == "Them"
    assert mistake["opening"] == "Test Opening"
    assert mistake["facts"]["move_bucket"] == "1-10"


def test_missed_mate_outranks_every_other_category():
    move = cached_move(
        1,
        1,
        "white",
        900,
        0,
        best_move_was_mate=True,
        best_move_was_capture=True,
        hanging_after=[HUNG_QUEEN],
        clock_before=5.0,
        clock_after=3.0,
    )
    mistake = mine_patterns(cached_game([move]))["mistakes"][0]

    assert mistake["category"] == "missed_mate"
    assert "checkmate" in mistake["category_basis"]


def test_a_hanging_piece_is_named_with_its_square():
    move = cached_move(1, 1, "white", 50, -250, hanging_after=[HUNG_QUEEN])
    mistake = mine_patterns(cached_game([move]))["mistakes"][0]

    assert mistake["category"] == "hanging_piece"
    assert "queen on d5" in mistake["category_basis"]
    assert mistake["facts"]["hangs_piece"] is True
    assert mistake["facts"]["hung_piece"]["square"] == "d5"


def test_a_missed_capture_is_reported_as_such():
    move = cached_move(1, 1, "white", 50, -250, best_move_was_capture=True, is_capture=False)
    mistake = mine_patterns(cached_game([move]))["mistakes"][0]

    assert mistake["category"] == "missed_capture"
    assert "capture" in mistake["category_basis"]


def test_a_capture_that_was_actually_played_is_not_a_missed_capture():
    move = cached_move(1, 1, "white", 50, -250, best_move_was_capture=True, is_capture=True)
    mistake = mine_patterns(cached_game([move]))["mistakes"][0]

    assert mistake["category"] == "opening"


def test_time_pressure_requires_a_low_clock_and_real_clock_data():
    low = cached_move(1, 1, "white", 50, -250, clock_before=12.0, clock_after=8.0)
    high = cached_move(1, 1, "white", 50, -250, clock_before=300.0, clock_after=290.0)
    none = cached_move(1, 1, "white", 50, -250)

    pressurised = mine_patterns(cached_game([low]))["mistakes"][0]
    assert pressurised["category"] == "time_pressure"
    assert pressurised["in_time_pressure"] is True
    assert pressurised["time_remaining"] == 12.0
    assert "12s" in pressurised["category_basis"]

    assert mine_patterns(cached_game([high]))["mistakes"][0]["category"] == "opening"
    assert mine_patterns(cached_game([none]))["mistakes"][0]["category"] == "opening"


def test_a_decided_position_needs_both_sides_of_the_move_to_agree():
    assert is_decided(99.0, 98.0) is True
    assert is_decided(2.0, 1.0) is True
    assert is_decided(99.0, 40.0) is False
    assert is_decided(60.0, 55.0) is False


def test_mistakes_in_decided_positions_are_excluded_by_default():
    games = cached_game([cached_move(1, 1, "white", 900, 700)])
    report = mine_patterns(games, MinerConfig())

    assert report["mistakes"] == []
    assert report["context"]["excluded_decided"] == 1


def test_decided_positions_can_be_kept_when_asked_for():
    games = cached_game([cached_move(1, 1, "white", 900, 700)])
    report = mine_patterns(games, MinerConfig(ignore_decided=False))

    assert len(report["mistakes"]) == 1
    assert report["mistakes"][0]["game_decided"] is True


def test_a_genuine_collapse_is_never_treated_as_decided():
    games = cached_game([cached_move(1, 1, "white", 900, -300)])
    report = mine_patterns(games, MinerConfig())

    assert len(report["mistakes"]) == 1
    assert report["context"]["excluded_decided"] == 0


def test_a_single_occurrence_is_not_called_a_pattern():
    games = cached_game([cached_move(1, 1, "white", 50, -250)])
    report = mine_patterns(games)

    assert report["patterns"]["category"] == [{"key": "opening", "count": 1, "games": 1}]
    assert report["recurring"]["category"] == []


def test_the_same_mistake_in_two_games_is_recurring():
    report = mine_patterns(
        merge(
            cached_game([cached_move(1, 1, "white", 50, -250)], "g1"),
            cached_game([cached_move(1, 1, "white", 50, -250)], "g2"),
        )
    )

    assert report["recurring"]["category"] == [{"key": "opening", "count": 2, "games": 2}]
    assert report["patterns"]["color"] == [{"key": "white", "count": 2, "games": 2}]


def test_the_player_filter_keeps_only_that_players_moves():
    games = cached_game(
        [
            cached_move(1, 1, "white", 50, -250),
            cached_move(2, 1, "black", 50, -250),
        ]
    )

    both = mine_patterns(games, MinerConfig())
    assert len(both["mistakes"]) == 2

    mine = mine_patterns(games, MinerConfig(player="me"))
    assert [item["color"] for item in mine["mistakes"]] == ["white"]
    assert mine["context"]["games_matched_player"] == 1
    assert mine["context"]["player_not_found"] is False


def test_an_unknown_player_is_reported_rather_than_silently_empty():
    games = cached_game([cached_move(1, 1, "white", 50, -250)], white="Someone", black="Else")
    report = mine_patterns(games, MinerConfig(player="me"))

    assert report["mistakes"] == []
    assert report["context"]["player_not_found"] is True
    assert report["context"]["games_matched_player"] == 0


def test_the_color_filter_excludes_the_other_side():
    games = cached_game(
        [
            cached_move(1, 1, "white", 50, -250),
            cached_move(2, 1, "black", 50, -250),
        ]
    )
    report = mine_patterns(games, MinerConfig(color="black"))

    assert [item["color"] for item in report["mistakes"]] == ["black"]
    assert report["context"]["excluded_not_played_by_color"] == 1


def test_thresholds_are_applied_at_report_time():
    games = cached_game(
        [
            cached_move(1, 1, "white", 50, 0),
            cached_move(3, 2, "white", 50, -250),
        ]
    )

    lenient = mine_patterns(games, MinerConfig(min_loss=0.4))
    strict = mine_patterns(games, MinerConfig(min_loss=1.0))

    assert len(lenient["mistakes"]) == 2
    assert len(strict["mistakes"]) == 1
    assert strict["mistakes"][0]["severity"] == "blunder"


def test_clock_coverage_is_counted_per_game_not_per_move():
    report = mine_patterns(
        merge(
            cached_game(
                [
                    cached_move(1, 1, "white", 50, -250, clock_after=500.0),
                    cached_move(2, 1, "black", 50, -250, clock_after=480.0),
                ],
                "g1",
            ),
            cached_game([cached_move(1, 1, "white", 50, -250)], "g2"),
        )
    )

    assert report["context"]["games_analyzed"] == 2
    assert report["context"]["games_with_clock"] == 1


def test_failed_positions_are_counted_and_never_scored():
    broken = {"ply": 1, "move_number": 1, "color": "white", "error": "EngineError: boom"}
    games = cached_game([broken, cached_move(2, 1, "black", 50, -250)])
    report = mine_patterns(games)

    assert report["context"]["moves_failed"] == 1
    assert report["context"]["moves_scored"] == 1
    assert len(report["mistakes"]) == 1


def test_every_record_is_sorted_by_size_of_loss():
    games = cached_game(
        [
            cached_move(1, 1, "white", 50, 0),
            cached_move(3, 2, "white", 50, -250),
            cached_move(5, 3, "white", 50, -120),
        ]
    )
    report = mine_patterns(games, MinerConfig(min_loss=0.4))

    assert [item["loss"] for item in report["mistakes"]] == [3.0, 1.7, 0.5]
    assert report["largest"] == report["mistakes"][0]


def test_the_profile_summarises_the_report():
    games = cached_game(
        [
            cached_move(1, 1, "white", 50, -250, clock_before=10.0, clock_after=4.0),
            cached_move(3, 2, "white", 50, -250, hanging_after=[HUNG_QUEEN]),
        ]
    )
    profile = build_profile(mine_patterns(games))

    assert profile["mistake_count"] == 2
    assert profile["average_loss"] == 3.0
    assert profile["most_problematic_phase"] == {"phase": "opening", "count": 2}
    assert profile["severity_breakdown"] == [{"severity": "blunder", "count": 2}]
    assert profile["phase_breakdown"] == [{"phase": "opening", "count": 2, "games": 1}]
    assert [row["category"] for row in profile["tactical_weaknesses"]] == ["hanging_piece"]
    assert {row["category"] for row in profile["most_common_categories"]} == {
        "time_pressure",
        "hanging_piece",
    }
    assert all(row["recurring"] is False for row in profile["most_common_categories"])


def test_the_profile_reports_clock_coverage_and_share():
    games = cached_game(
        [
            cached_move(1, 1, "white", 50, -250, clock_before=10.0, clock_after=4.0),
            cached_move(3, 2, "white", 50, -250, clock_before=200.0, clock_after=180.0),
        ]
    )
    profile = build_profile(mine_patterns(games))

    assert profile["time_pressure"]["count"] == 1
    assert profile["time_pressure"]["share"] == 50.0
    assert profile["time_pressure"]["threshold_seconds"] == 30.0
    assert profile["time_pressure"]["clock_coverage"] == "1 of 1 games"


def test_observations_state_only_what_the_data_supports():
    games = merge(
        cached_game(
            [cached_move(1, 1, "white", 50, -250, clock_before=10.0, clock_after=4.0)], "g1"
        ),
        cached_game(
            [cached_move(1, 1, "white", 50, -250, clock_before=9.0, clock_after=3.0)], "g2"
        ),
    )
    report = mine_patterns(games)
    text = " ".join(build_observations(report))

    assert "Clock annotations were present in 2 of 2 games" in text
    assert "under 30s remaining" in text
    assert "Most mistakes came in the opening." in text

    lowered = text.lower()
    for banned in ("careless", "tilted", "rushed", "should have", "obviously", "always", "never"):
        assert banned not in lowered


def test_the_report_discloses_what_it_left_out():
    report = mine_patterns(cached_game([cached_move(1, 1, "white", 900, 700)]))
    observations = build_observations(report)

    assert report["context"]["excluded_decided"] == 1
    assert any("already-decided" in line for line in observations)


def test_failed_positions_are_disclosed_not_hidden():
    broken = {"ply": 1, "move_number": 1, "color": "white", "error": "EngineError: boom"}
    report = mine_patterns(cached_game([broken, cached_move(2, 1, "black", 50, -250)]))
    observations = build_observations(report)

    assert any("could not be evaluated" in line for line in observations)


def test_the_config_travels_with_the_report():
    report = mine_patterns(cached_game([cached_move(1, 1, "white", 50, -250)]), MinerConfig(min_loss=0.25))

    assert report["config"]["min_loss"] == 0.25
    assert report["config"]["ignore_decided"] is True
    assert set(report["config"]) == {
        "min_loss",
        "time_pressure",
        "player",
        "color",
        "inaccuracy",
        "mistake",
        "blunder",
        "ignore_decided",
    }


def test_build_records_returns_mistakes_and_context_separately():
    mistakes, context = build_records(cached_game([cached_move(1, 1, "white", 50, -250)]), MinerConfig())

    assert len(mistakes) == 1
    assert context["games_analyzed"] == 1
    assert context["moves_scored"] == 1
