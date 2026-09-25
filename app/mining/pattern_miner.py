from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Iterable, Optional

from app.mining.mistake_detector import MinerConfig, build_records

MIN_GAMES_FOR_PATTERN = 2


def tally(mistakes: Iterable[dict], key: Callable[[dict], Any]) -> list[dict]:
    counts: Counter = Counter()
    games: dict[Any, set] = defaultdict(set)

    for mistake in mistakes:
        value = key(mistake)
        if value is None:
            continue
        counts[value] += 1
        games[value].add(mistake["game_id"])

    return [
        {"key": value, "count": count, "games": len(games[value])}
        for value, count in counts.most_common()
    ]


def mine_patterns(
    games: dict[str, dict], config: Optional[MinerConfig] = None
) -> dict:
    config = config or MinerConfig()
    mistakes, context = build_records(games, config)

    patterns = {
        "category": tally(mistakes, lambda item: item["category"]),
        "severity": tally(mistakes, lambda item: item["severity"]),
        "phase": tally(mistakes, lambda item: item["phase"]),
        "color": tally(mistakes, lambda item: item["color"]),
        "opening": tally(mistakes, lambda item: item["opening"]),
        "move_bucket": tally(mistakes, lambda item: item["facts"]["move_bucket"]),
        "hung_piece": tally(
            mistakes,
            lambda item: item["facts"]["hung_piece"]
            and item["facts"]["hung_piece"].get("name", item["facts"]["hung_piece"]["piece"]),
        ),
    }

    recurring = {
        name: [row for row in rows if row["games"] >= MIN_GAMES_FOR_PATTERN]
        for name, rows in patterns.items()
    }

    return {
        "config": config.as_dict(),
        "context": context,
        "mistakes": mistakes,
        "patterns": patterns,
        "recurring": recurring,
        "largest": mistakes[0] if mistakes else None,
    }
