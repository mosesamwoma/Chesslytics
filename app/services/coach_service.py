from __future__ import annotations

import json
import os
from typing import Optional

from groq import Groq, GroqError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import CoachInsight, Mistake, PlayerProfile
from app.mining.profiler import label_for

DEFAULT_MODEL = "llama-3.3-70b-versatile"
MAX_MISTAKES = 6
MAX_PATTERNS = 8

SYSTEM_PROMPT = (
    "You are a chess coach reviewing statistical evidence mined from a player's own "
    "games by a Stockfish-based analysis tool. You never invent facts, moves, or "
    "psychology beyond what the evidence supports, and you never claim to have seen "
    "positions that are not described to you. Base every sentence only on the JSON "
    "evidence you are given. Write in a direct, encouraging coaching voice aimed at "
    "the player, using \"you\". Respond with a single JSON object and nothing else, "
    "matching exactly this shape: {\"summary\": string, \"focus_drill\": string, "
    "\"sections\": [{\"title\": string, \"body\": string}, ...]}. \"summary\" is two "
    "to three sentences on the single biggest pattern in the evidence. \"focus_drill\" "
    "is one concrete, practical exercise the player can do this week to address that "
    "pattern. \"sections\" should contain three to five entries, each covering a "
    "different recurring category, phase, or opening drawn from the evidence, with a "
    "short title and a two-to-four sentence body."
)


def groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return Groq(api_key=api_key)


def groq_model() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


def _mistake_row(mistake: Mistake) -> dict:
    return {
        "game_id": mistake.game_id,
        "move_number": mistake.move_number,
        "color": mistake.color,
        "category": label_for(mistake.category),
        "phase": mistake.phase,
        "severity": mistake.severity,
        "loss_pawns": round(mistake.loss, 2),
        "played_move": mistake.played_move,
        "best_move": mistake.best_move,
        "opening": mistake.opening,
        "in_time_pressure": mistake.in_time_pressure,
    }


def top_mistakes(session: Session, profile: PlayerProfile) -> list[dict]:
    statement = select(Mistake).order_by(Mistake.loss.desc()).limit(MAX_MISTAKES)
    if profile.player:
        statement = statement.where(Mistake.player == profile.player)
    rows = list(session.scalars(statement))
    return [_mistake_row(row) for row in rows]


def build_context(session: Session, profile: PlayerProfile) -> dict:
    payload = profile.payload or {}
    patterns = sorted(
        profile.patterns,
        key=lambda row: (-row.games, -row.count),
    )[:MAX_PATTERNS]
    return {
        "player": profile.player or "the analyzed side",
        "color": profile.color,
        "games_analyzed": profile.games_analyzed,
        "mistake_count": profile.mistake_count,
        "average_loss_pawns": round(profile.average_loss, 2),
        "most_common_categories": payload.get("most_common_categories", []),
        "tactical_weaknesses": payload.get("tactical_weaknesses", []),
        "opening_patterns": payload.get("opening_patterns", []),
        "phase_breakdown": payload.get("phase_breakdown", []),
        "time_pressure": payload.get("time_pressure", {}),
        "observations": payload.get("observations", []),
        "recurring_patterns": [
            {
                "kind": row.kind,
                "key": row.key,
                "count": row.count,
                "games": row.games,
                "description": row.description,
            }
            for row in patterns
        ],
        "worst_mistakes": top_mistakes(session, profile),
    }


def build_messages(context: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(context)},
    ]


def _validate_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("coach response was not a JSON object")
    summary = data.get("summary")
    focus_drill = data.get("focus_drill")
    sections = data.get("sections")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("coach response is missing a summary")
    if not isinstance(focus_drill, str) or not focus_drill.strip():
        raise ValueError("coach response is missing a focus_drill")
    if not isinstance(sections, list) or not sections:
        raise ValueError("coach response is missing sections")
    cleaned_sections = []
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        body = entry.get("body")
        if isinstance(title, str) and isinstance(body, str) and title.strip() and body.strip():
            cleaned_sections.append({"title": title.strip(), "body": body.strip()})
    if not cleaned_sections:
        raise ValueError("coach response had no usable sections")
    return {
        "summary": summary.strip(),
        "focus_drill": focus_drill.strip(),
        "sections": cleaned_sections,
    }


def request_completion(context: dict) -> tuple[dict, str]:
    client = groq_client()
    model = groq_model()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=build_messages(context),
            temperature=0.4,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except GroqError as exc:
        raise RuntimeError(f"Groq request failed: {exc}") from exc

    raw = response.choices[0].message.content or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Groq response was not valid JSON") from exc

    return _validate_payload(parsed), raw


def latest_insight(session: Session, profile_id: int) -> Optional[CoachInsight]:
    statement = (
        select(CoachInsight)
        .where(CoachInsight.profile_id == profile_id)
        .order_by(CoachInsight.created_at.desc(), CoachInsight.id.desc())
        .limit(1)
    )
    return session.scalars(statement).first()


def generate(session: Session, profile: PlayerProfile) -> CoachInsight:
    context = build_context(session, profile)
    validated, raw = request_completion(context)

    insight = CoachInsight(
        profile_id=profile.id,
        player=profile.player,
        model=groq_model(),
        summary=validated["summary"],
        focus_drill=validated["focus_drill"],
        sections=validated["sections"],
        raw_response=raw,
    )
    session.add(insight)
    session.flush()
    return insight


def get_or_create(session: Session, profile: PlayerProfile, force: bool = False) -> CoachInsight:
    if not force:
        existing = latest_insight(session, profile.id)
        if existing is not None:
            return existing
    return generate(session, profile)


def insight_payload(insight: CoachInsight) -> dict:
    return {
        "id": insight.id,
        "profile_id": insight.profile_id,
        "player": insight.player,
        "model": insight.model,
        "summary": insight.summary,
        "focus_drill": insight.focus_drill,
        "sections": insight.sections or [],
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
    }
