from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.database.database import get_db
from app.database.models import Game, Mistake, PlayerProfile, User
from app.services import analysis_service, progress_service

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _grouped(db: Session, user_id: int, column) -> list[dict]:
    rows = db.execute(
        select(column, func.count(Mistake.id))
        .where(Mistake.user_id == user_id, column.is_not(None))
        .group_by(column)
        .order_by(func.count(Mistake.id).desc())
    ).all()
    return [{"key": key, "count": count} for key, count in rows]


@router.get("/overview")
def overview(user: User = Depends(auth.current_user), db: Session = Depends(get_db)) -> dict:
    uid = user.id
    total_games = int(db.scalar(select(func.count(Game.id)).where(Game.user_id == uid)) or 0)
    analyzed = int(
        db.scalar(
            select(func.count(Game.id)).where(
                Game.user_id == uid, Game.analyzed_at.is_not(None)
            )
        )
        or 0
    )
    mistakes = int(db.scalar(select(func.count(Mistake.id)).where(Mistake.user_id == uid)) or 0)
    average = db.scalar(select(func.avg(Mistake.loss)).where(Mistake.user_id == uid))
    pressured = int(
        db.scalar(
            select(func.count(Mistake.id)).where(
                Mistake.user_id == uid, Mistake.in_time_pressure.is_(True)
            )
        )
        or 0
    )

    return {
        "games": total_games,
        "games_analyzed": analyzed,
        "mistakes": mistakes,
        "average_loss": round(float(average), 2) if average is not None else 0.0,
        "time_pressure_mistakes": pressured,
        "by_category": _grouped(db, uid, Mistake.category),
        "by_severity": _grouped(db, uid, Mistake.severity),
        "by_phase": _grouped(db, uid, Mistake.phase),
        "by_color": _grouped(db, uid, Mistake.color),
        "top_openings": _grouped(db, uid, Mistake.opening)[:10],
    }


@router.get("/progress")
def progress(
    weeks: int = Query(26, ge=2, le=104),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    return progress_service.progress(db, user.id, weeks)


@router.get("/openings")
def openings(
    min_games: int = Query(1, ge=1, le=100),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    return progress_service.openings(db, user.id, min_games)


@router.get("/profiles")
def list_profiles(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = analysis_service.list_profiles(db, user.id, limit=limit)
    return {
        "profiles": [
            {
                "id": profile.id,
                "player": profile.player,
                "color": profile.color,
                "games_analyzed": profile.games_analyzed,
                "mistake_count": profile.mistake_count,
                "average_loss": profile.average_loss,
                "engine": profile.engine,
                "depth": profile.depth,
                "created_at": profile.created_at.isoformat()
                if profile.created_at
                else None,
            }
            for profile in rows
        ]
    }


@router.get("/profile")
def latest_profile(
    player: Optional[str] = Query(default=None, max_length=128),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    profile = analysis_service.latest_profile(db, user.id, player=player)
    if profile is None:
        raise HTTPException(status_code=404, detail="no profile has been generated yet")
    return analysis_service.profile_payload(profile)


@router.get("")
def list_patterns(
    profile_id: Optional[int] = Query(default=None),
    kind: Optional[str] = Query(default=None, max_length=32),
    recurring_only: bool = Query(default=False),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    if profile_id is None:
        profile = analysis_service.latest_profile(db, user.id)
        if profile is None:
            return {"profile_id": None, "patterns": []}
        profile_id = profile.id

    profile = db.get(PlayerProfile, profile_id)
    if profile is None or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="profile not found")

    patterns = [analysis_service.pattern_to_dict(row) for row in profile.patterns]
    if kind:
        patterns = [row for row in patterns if row["kind"] == kind]
    if recurring_only:
        patterns = [row for row in patterns if row["recurring"]]
    patterns.sort(key=lambda row: (-row["games"], -row["count"], row["key"]))

    return {"profile_id": profile_id, "patterns": patterns}
