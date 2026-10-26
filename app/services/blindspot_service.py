from __future__ import annotations

from typing import Optional

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chess.lines import THEME_ORDER
from app.database.models import Mistake
from app.services import progress_service

PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
MIN_FOR_INSIGHT = 3


def region_of(square: chess.Square) -> str:
    file_index = chess.square_file(square)
    if file_index <= 2:
        return "queenside"
    if file_index >= 5:
        return "kingside"
    return "center"


def _piece_and_square(mistake: Mistake) -> tuple[Optional[str], Optional[chess.Square]]:
    if not mistake.fen or not mistake.played_uci:
        return None, None
    try:
        board = chess.Board(mistake.fen)
        move = chess.Move.from_uci(mistake.played_uci)
    except ValueError:
        return None, None
    piece = board.piece_at(move.from_square)
    if piece is None:
        return None, move.to_square
    return PIECE_NAMES[piece.piece_type], move.to_square


def _loose_square(mistake: Mistake) -> Optional[chess.Square]:
    hung = (mistake.facts or {}).get("hung_piece") or {}
    name = hung.get("square")
    if not name:
        return None
    try:
        return chess.parse_square(name)
    except ValueError:
        return None


def blindspots(session: Session, user_id: int) -> dict:
    player = progress_service.tracked_player(session, user_id)
    rows = list(
        session.scalars(
            select(Mistake).where(Mistake.user_id == user_id, Mistake.fen.is_not(None))
        )
    )
    if player:
        wanted = player.strip().lower()
        rows = [row for row in rows if (row.player or "").strip().lower() == wanted]

    theme_counts: dict[str, int] = {}
    piece_counts: dict[str, int] = {}
    region_counts: dict[str, int] = {"queenside": 0, "center": 0, "kingside": 0}
    pair_counts: dict[tuple[str, str], int] = {}
    region_theme: dict[tuple[str, str], int] = {}
    loose = [0] * 64
    landing = [0] * 64

    for mistake in rows:
        tactics = (mistake.facts or {}).get("tactics") or {}
        themes = list(tactics.get("themes") or [])
        piece, destination = _piece_and_square(mistake)
        region = region_of(destination) if destination is not None else None
        if piece:
            piece_counts[piece] = piece_counts.get(piece, 0) + 1
        if region:
            region_counts[region] += 1
        if destination is not None:
            landing[destination] += 1
        spot = _loose_square(mistake)
        if spot is not None:
            loose[spot] += 1
        for theme in themes:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            if piece:
                pair_counts[(theme, piece)] = pair_counts.get((theme, piece), 0) + 1
            if region:
                region_theme[(theme, region)] = region_theme.get((theme, region), 0) + 1

    total = len(rows)
    order = {theme: index for index, theme in enumerate(THEME_ORDER)}
    themes_sorted = sorted(theme_counts.items(), key=lambda item: (-item[1], order.get(item[0], 99)))

    insights: list[dict] = []
    for (theme, piece), count in sorted(pair_counts.items(), key=lambda item: -item[1])[:3]:
        if count >= MIN_FOR_INSIGHT:
            insights.append({"kind": "theme_piece", "theme": theme, "piece": piece, "count": count})
    for (theme, region), count in sorted(region_theme.items(), key=lambda item: -item[1])[:3]:
        if count >= MIN_FOR_INSIGHT and theme_counts.get(theme, 0) and count / theme_counts[theme] >= 0.5:
            insights.append({"kind": "theme_region", "theme": theme, "region": region, "count": count})
    if piece_counts:
        piece, count = max(piece_counts.items(), key=lambda item: item[1])
        if count >= MIN_FOR_INSIGHT and total and count / total >= 0.35:
            insights.append({"kind": "piece", "piece": piece, "count": count})

    return {
        "player": player,
        "total": total,
        "themes": [{"theme": theme, "count": count} for theme, count in themes_sorted],
        "pieces": [
            {"piece": piece, "count": count}
            for piece, count in sorted(piece_counts.items(), key=lambda item: -item[1])
        ],
        "regions": [{"region": region, "count": count} for region, count in region_counts.items()],
        "loose_squares": loose,
        "landing_squares": landing,
        "insights": insights,
    }
