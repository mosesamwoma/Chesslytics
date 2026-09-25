from __future__ import annotations

from statistics import mean

from app.mining.pattern_miner import MIN_GAMES_FOR_PATTERN

CATEGORY_LABELS = {
    "missed_mate": "Missed mates",
    "hanging_piece": "Hanging pieces",
    "missed_capture": "Missed captures",
    "time_pressure": "Time-pressure mistakes",
    "opening": "Opening mistakes",
    "middlegame": "Middlegame mistakes",
    "endgame": "Endgame mistakes",
}


def label_for(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


def build_profile(report: dict) -> dict:
    mistakes = report["mistakes"]
    context = report["context"]
    config = report["config"]

    profile = {
        "games_analyzed": context["games_analyzed"],
        "moves_scored": context["moves_scored"],
        "moves_failed": context["moves_failed"],
        "mistake_count": len(mistakes),
        "games_with_clock": context["games_with_clock"],
        "excluded_decided": context["excluded_decided"],
        "most_common_categories": [],
        "most_problematic_phase": None,
        "tactical_weaknesses": [],
        "opening_patterns": [],
        "phase_breakdown": [],
        "severity_breakdown": [],
        "time_pressure": {
            "count": 0,
            "share": 0.0,
            "threshold_seconds": config["time_pressure"],
            "clock_coverage": f"{context['games_with_clock']} of {context['games_analyzed']} games",
        },
        "average_loss": 0.0,
        "average_loss_by_phase": [],
        "observations": [],
    }

    profile["observations"] = build_observations(report)

    if not mistakes:
        return profile

    profile["most_common_categories"] = [
        {
            "category": row["key"],
            "label": label_for(row["key"]),
            "count": row["count"],
            "games": row["games"],
            "recurring": row["games"] >= MIN_GAMES_FOR_PATTERN,
        }
        for row in report["patterns"]["category"]
    ]

    phases = report["patterns"]["phase"]
    if phases:
        profile["most_problematic_phase"] = {
            "phase": phases[0]["key"],
            "count": phases[0]["count"],
        }

    tactical = [
        row for row in report["patterns"]["category"]
        if row["key"] in ("hanging_piece", "missed_capture", "missed_mate")
    ]
    profile["tactical_weaknesses"] = [
        {"category": row["key"], "label": label_for(row["key"]), "count": row["count"], "games": row["games"]}
        for row in tactical
    ]

    profile["opening_patterns"] = [
        {"opening": row["key"], "count": row["count"], "games": row["games"]}
        for row in report["patterns"]["opening"][:10]
    ]

    profile["phase_breakdown"] = [
        {"phase": row["key"], "count": row["count"], "games": row["games"]}
        for row in report["patterns"]["phase"]
    ]

    profile["severity_breakdown"] = [
        {"severity": row["key"], "count": row["count"]}
        for row in report["patterns"]["severity"]
    ]

    pressured = [item for item in mistakes if item["in_time_pressure"]]
    profile["time_pressure"]["count"] = len(pressured)
    profile["time_pressure"]["share"] = round(100.0 * len(pressured) / len(mistakes), 1)

    profile["average_loss"] = round(mean(item["loss"] for item in mistakes), 2)
    profile["average_loss_by_phase"] = _average_loss_by_phase(mistakes)

    return profile


def _average_loss_by_phase(mistakes: list[dict]) -> list[dict]:
    grouped: dict[str, list[float]] = {}
    for mistake in mistakes:
        grouped.setdefault(mistake["phase"], []).append(mistake["loss"])
    return [
        {"phase": phase, "average_loss": round(mean(losses), 2), "count": len(losses)}
        for phase, losses in sorted(grouped.items(), key=lambda item: -len(item[1]))
    ]


def build_observations(report: dict) -> list[str]:
    mistakes = report["mistakes"]
    context = report["context"]
    total = len(mistakes)

    observations: list[str] = []

    top = report["recurring"]["category"]
    if top and total:
        leader = top[0]
        observations.append(
            f"Most frequent recurring category: {leader['key']} "
            f"({leader['count']} of {total} mistakes across {leader['games']} games)."
        )

    pressured = [item for item in mistakes if item["in_time_pressure"]]
    if pressured and context["games_with_clock"]:
        share = 100.0 * len(pressured) / total
        observations.append(
            f"{len(pressured)} mistakes ({share:.0f}%) were played with under "
            f"{report['config']['time_pressure']:.0f}s remaining. Clock annotations were "
            f"present in {context['games_with_clock']} of {context['games_analyzed']} games, "
            f"so this describes only those."
        )

    phases = report["patterns"]["phase"]
    if phases and total:
        observations.append(f"Most mistakes came in the {phases[0]['key']}.")

    hung = report["patterns"]["hung_piece"]
    if hung:
        leaders = ", ".join(f"{row['key']} x{row['count']}" for row in hung[:3])
        observations.append(f"Pieces left loose, by piece: {leaders}.")

    if report["config"]["ignore_decided"]:
        if context["excluded_decided"]:
            observations.append(
                f"{context['excluded_decided']} mistakes in already-decided positions were "
                f"excluded from every count above, because losing evaluation there does not "
                f"change the result."
            )
    else:
        kept = [item for item in mistakes if item["game_decided"]]
        if kept:
            observations.append(
                f"{len(kept)} of the counted mistakes were made in already-decided "
                f"positions and are included above."
            )

    if context["moves_failed"]:
        observations.append(
            f"{context['moves_failed']} positions could not be evaluated and are not "
            f"represented here."
        )

    return observations
