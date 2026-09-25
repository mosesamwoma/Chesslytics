from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median
from typing import Any, Callable, Iterable, Optional

from app.chess.book import BookReader
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


def tally_many(mistakes: Iterable[dict], key: Callable[[dict], list]) -> list[dict]:
    counts: Counter = Counter()
    games: dict[Any, set] = defaultdict(set)

    for mistake in mistakes:
        for value in key(mistake) or []:
            if value is None:
                continue
            counts[value] += 1
            games[value].add(mistake["game_id"])

    return [
        {"key": value, "count": count, "games": len(games[value])}
        for value, count in counts.most_common()
    ]


def book_summary(context: dict) -> dict:
    depths = context.pop("book_depths", []) or []
    middle = int(median(depths)) if depths else None
    return {
        "path": context.get("book"),
        "positions": context.get("book_positions", 0),
        "in_book": context.get("moves_in_book", 0),
        "mistakes_in_book": context.get("mistakes_in_book", 0),
        "excluded": context.get("excluded_book", 0),
        "games_following_book": context.get("games_with_book", 0),
        "median_book_ply": middle,
        "median_book_move": (middle + 1) // 2 if middle else None,
    }


def mine_patterns(
    games: dict[str, dict],
    config: Optional[MinerConfig] = None,
    reader: Optional[BookReader] = None,
) -> dict:
    config = config or MinerConfig()
    mistakes, context = build_records(games, config, reader)

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
        "motif": tally_many(
            mistakes,
            lambda item: [
                motif["kind"] for motif in (item["facts"].get("motifs_allowed") or [])
            ],
        ),
    }

    recurring = {
        name: [row for row in rows if row["games"] >= MIN_GAMES_FOR_PATTERN]
        for name, rows in patterns.items()
    }

    return {
        "config": config.as_dict(),
        "context": context,
        "book": book_summary(context),
        "mistakes": mistakes,
        "patterns": patterns,
        "recurring": recurring,
        "largest": mistakes[0] if mistakes else None,
    }
