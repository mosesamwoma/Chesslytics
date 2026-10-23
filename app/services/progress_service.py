from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database.models import Game, Mistake, Move, PlayerProfile

RESULT_POINTS = {"1-0": ("white", 1.0), "0-1": ("black", 1.0), "1/2-1/2": (None, 0.5)}
MIN_MOVES_FOR_TREND = 20
TREND_WEEKS = 4


def tracked_player(session: Session, user_id: int) -> Optional[str]:
    profile = session.scalar(
        select(PlayerProfile)
        .where(PlayerProfile.user_id == user_id)
        .order_by(PlayerProfile.created_at.desc(), PlayerProfile.id.desc())
        .limit(1)
    )
    if profile is None or not profile.player:
        return None
    return profile.player


def _colors_for(white: str, black: str, player: Optional[str]) -> list[str]:
    if not player:
        return ["white", "black"]
    wanted = player.strip().lower()
    colors = []
    if (white or "").strip().lower() == wanted:
        colors.append("white")
    if (black or "").strip().lower() == wanted:
        colors.append("black")
    return colors[:1]


def _game_day(raw: Optional[str], created: Optional[datetime]) -> Optional[date]:
    if raw:
        parts = raw.strip().split(".")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                pass
    if created is not None:
        return created.date()
    return None


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _game_stats(session: Session, user_id: int) -> tuple[dict, dict, list, list]:
    move_rows = session.execute(
        select(
            Move.game_id,
            Move.color,
            func.count(Move.id),
            func.coalesce(func.sum(case((Move.loss_cp > 0, Move.loss_cp), else_=0)), 0),
        )
        .join(Game, Game.id == Move.game_id)
        .where(Game.user_id == user_id, Move.loss_cp.is_not(None))
        .group_by(Move.game_id, Move.color)
    ).all()
    moves = {(game_id, color): (int(count), int(total)) for game_id, color, count, total in move_rows}

    mistake_rows = session.execute(
        select(Mistake.game_id, Mistake.color, Mistake.move_number, Mistake.category).where(
            Mistake.user_id == user_id
        )
    ).all()
    mistakes: dict[tuple[int, str], int] = {}
    for game_id, color, _number, _category in mistake_rows:
        mistakes[(game_id, color)] = mistakes.get((game_id, color), 0) + 1

    games = session.execute(
        select(
            Game.id,
            Game.white,
            Game.black,
            Game.result,
            Game.date,
            Game.created_at,
            Game.opening,
            Game.eco,
        ).where(Game.user_id == user_id, Game.analyzed_at.is_not(None))
    ).all()
    return moves, mistakes, list(games), list(mistake_rows)


def _aggregate(buckets: list[dict]) -> dict:
    moves = sum(bucket["moves"] for bucket in buckets)
    loss = sum(bucket["loss_cp"] for bucket in buckets)
    mistakes = sum(bucket["mistakes"] for bucket in buckets)
    return {
        "games": sum(bucket["games"] for bucket in buckets),
        "moves": moves,
        "mistakes": mistakes,
        "mistakes_per_100": round(100.0 * mistakes / moves, 1) if moves else None,
        "average_loss": round(loss / 100.0 / moves, 3) if moves else None,
    }


TIME_CONTROL_ORDER = ["ultrabullet", "bullet", "blitz", "rapid", "classical", "daily", "unknown"]


def classify_time_control(raw: Optional[str]) -> str:
    text = (raw or "").strip()
    if not text or text in {"-", "?"}:
        return "unknown"
    if "/" in text:
        return "daily"
    base, _, bonus = text.partition("+")
    try:
        seconds = int(base)
        increment = int(bonus) if bonus else 0
    except ValueError:
        return "unknown"
    if seconds < 0 or increment < 0:
        return "unknown"
    estimate = seconds + 40 * increment
    if estimate < 30:
        return "ultrabullet"
    if estimate < 180:
        return "bullet"
    if estimate < 480:
        return "blitz"
    if estimate < 1500:
        return "rapid"
    return "classical"


def time_controls(session: Session, user_id: int) -> dict:
    player = tracked_player(session, user_id)
    moves, mistakes, games, mistake_rows = _game_stats(session, user_id)
    controls = {
        game_id: control
        for game_id, control in session.execute(
            select(Game.id, Game.time_control).where(
                Game.user_id == user_id, Game.analyzed_at.is_not(None)
            )
        ).all()
    }
    categories: dict[tuple[int, str], list[str]] = {}
    for game_id, color, _number, category in mistake_rows:
        categories.setdefault((game_id, color), []).append(category)

    groups: dict[str, dict] = {}
    for game_id, white, black, result, _date, _created, _opening, _eco in games:
        colors = _colors_for(white, black, player)
        if player and not colors:
            continue
        key = classify_time_control(controls.get(game_id))
        group = groups.setdefault(
            key,
            {
                "games": 0,
                "moves": 0,
                "loss_cp": 0,
                "mistakes": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "categories": Counter(),
            },
        )
        group["games"] += 1
        for color in colors:
            count, total = moves.get((game_id, color), (0, 0))
            group["moves"] += count
            group["loss_cp"] += total
            group["mistakes"] += mistakes.get((game_id, color), 0)
            group["categories"].update(categories.get((game_id, color), []))
        if player and colors:
            winner, points = RESULT_POINTS.get(result or "", (None, None))
            if points is None:
                continue
            if winner is None:
                group["draws"] += 1
            elif winner == colors[0]:
                group["wins"] += 1
            else:
                group["losses"] += 1

    rows = []
    for key in TIME_CONTROL_ORDER:
        group = groups.get(key)
        if group is None:
            continue
        decided = group["wins"] + group["draws"] + group["losses"]
        points = group["wins"] + 0.5 * group["draws"]
        top = None
        if group["categories"]:
            top = min(group["categories"].items(), key=lambda item: (-item[1], item[0]))[0]
        rows.append(
            {
                "key": key,
                "games": group["games"],
                "moves": group["moves"],
                "mistakes": group["mistakes"],
                "mistakes_per_100": (
                    round(100.0 * group["mistakes"] / group["moves"], 1)
                    if group["moves"]
                    else None
                ),
                "average_loss": (
                    round(group["loss_cp"] / 100.0 / group["moves"], 3)
                    if group["moves"]
                    else None
                ),
                "win_rate": round(100.0 * points / decided, 1) if player and decided else None,
                "top_category": top,
            }
        )
    return {"player": player, "time_controls": rows}


def progress(session: Session, user_id: int, weeks: int = 26) -> dict:
    player = tracked_player(session, user_id)
    moves, mistakes, games, _ = _game_stats(session, user_id)

    buckets: dict[date, dict] = {}
    for game_id, white, black, _result, raw_date, created, _opening, _eco in games:
        colors = _colors_for(white, black, player)
        if player and not colors:
            continue
        move_count = 0
        loss_total = 0
        mistake_count = 0
        for color in colors:
            count, total = moves.get((game_id, color), (0, 0))
            move_count += count
            loss_total += total
            mistake_count += mistakes.get((game_id, color), 0)
        if move_count == 0:
            continue
        day = _game_day(raw_date, created)
        if day is None:
            continue
        bucket = buckets.setdefault(
            _week_start(day),
            {"games": 0, "moves": 0, "mistakes": 0, "loss_cp": 0},
        )
        bucket["games"] += 1
        bucket["moves"] += move_count
        bucket["mistakes"] += mistake_count
        bucket["loss_cp"] += loss_total

    ordered = sorted(buckets.items())[-weeks:]
    series = []
    for start, bucket in ordered:
        row = _aggregate([bucket])
        row["week_start"] = start.isoformat()
        series.append(row)

    trend = None
    if len(ordered) >= 2:
        recent_buckets = [bucket for _, bucket in ordered[-TREND_WEEKS:]]
        earlier_buckets = [bucket for _, bucket in ordered[-2 * TREND_WEEKS : -TREND_WEEKS]]
        recent = _aggregate(recent_buckets)
        earlier = _aggregate(earlier_buckets) if earlier_buckets else None
        if (
            earlier is not None
            and recent["moves"] >= MIN_MOVES_FOR_TREND
            and earlier["moves"] >= MIN_MOVES_FOR_TREND
        ):
            trend = {"weeks": TREND_WEEKS, "recent": recent, "earlier": earlier}

    return {"player": player, "weeks": series, "trend": trend}


def openings(session: Session, user_id: int, min_games: int = 1, limit: int = 100) -> dict:
    player = tracked_player(session, user_id)
    moves, mistakes, games, mistake_rows = _game_stats(session, user_id)

    mistakes_by_game: dict[tuple[int, str], list[tuple[int, str]]] = {}
    for game_id, color, number, category in mistake_rows:
        mistakes_by_game.setdefault((game_id, color), []).append((number, category))

    groups: dict[str, dict] = {}
    for game_id, white, black, result, _date, _created, opening, eco in games:
        colors = _colors_for(white, black, player)
        if player and not colors:
            continue
        name = (opening or "").strip() or (eco or "").strip() or "Unknown opening"
        group = groups.setdefault(
            name,
            {
                "opening": name,
                "eco": (eco or "").strip() or None,
                "games": 0,
                "as_white": 0,
                "as_black": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "moves": 0,
                "loss_cp": 0,
                "mistakes": 0,
                "numbers": Counter(),
                "categories": Counter(),
            },
        )
        group["games"] += 1
        if not group["eco"] and eco:
            group["eco"] = eco.strip() or None
        for color in colors:
            count, total = moves.get((game_id, color), (0, 0))
            group["moves"] += count
            group["loss_cp"] += total
            for number, category in mistakes_by_game.get((game_id, color), []):
                group["mistakes"] += 1
                group["numbers"][number] += 1
                group["categories"][category] += 1
        if player and colors:
            color = colors[0]
            group["as_white" if color == "white" else "as_black"] += 1
            winner, points = RESULT_POINTS.get(result or "", (None, None))
            if points is None:
                continue
            if winner is None:
                group["draws"] += 1
            elif winner == color:
                group["wins"] += 1
            else:
                group["losses"] += 1

    rows = []
    for group in groups.values():
        if group["games"] < min_games:
            continue
        decided = group["wins"] + group["draws"] + group["losses"]
        points = group["wins"] + 0.5 * group["draws"]
        worst_number, worst_count = None, 0
        if group["numbers"]:
            worst_number, worst_count = min(
                group["numbers"].items(), key=lambda item: (-item[1], item[0])
            )
        top_category = None
        if group["categories"]:
            top_category = min(
                group["categories"].items(), key=lambda item: (-item[1], item[0])
            )[0]
        rows.append(
            {
                "opening": group["opening"],
                "eco": group["eco"],
                "games": group["games"],
                "as_white": group["as_white"],
                "as_black": group["as_black"],
                "wins": group["wins"],
                "draws": group["draws"],
                "losses": group["losses"],
                "win_rate": round(100.0 * points / decided, 1) if player and decided else None,
                "average_loss": (
                    round(group["loss_cp"] / 100.0 / group["moves"], 3)
                    if group["moves"]
                    else None
                ),
                "mistakes": group["mistakes"],
                "mistakes_per_game": round(group["mistakes"] / group["games"], 2),
                "worst_move": worst_number,
                "worst_move_mistakes": worst_count,
                "top_category": top_category,
            }
        )
    rows.sort(key=lambda row: (-row["games"], row["opening"]))
    return {"player": player, "openings": rows[:limit]}
