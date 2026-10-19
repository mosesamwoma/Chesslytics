from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import auth, security, settings
from app.database.database import get_db
from app.database.models import User
from app.services import analysis_service, coach_service

router = APIRouter(prefix="/api/coach", tags=["coach"])

COACH_PER_MINUTE = 4


@router.get("")
def get_insight(
    player: Optional[str] = Query(default=None, max_length=128),
    refresh: bool = Query(default=False),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    profile = analysis_service.latest_profile(db, user.id, player=player)
    if profile is None:
        raise HTTPException(status_code=404, detail="no profile has been generated yet")

    existing = None if refresh else coach_service.latest_insight(db, profile.id)
    if existing is not None and existing.model != coach_service.gemini_model():
        existing = None
    if existing is not None:
        return coach_service.insight_payload(existing)

    wait = security.limiter.consume(f"coach:{user.id}", COACH_PER_MINUTE, 60)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"slow down; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )
    daily = settings.coach_daily_limit()
    if user.role != "admin" and coach_service.generated_today(db, user.id) >= daily:
        raise HTTPException(
            status_code=429,
            detail=f"you have used your {daily} coaching reports for today; try again tomorrow",
        )

    try:
        insight = coach_service.generate(db, profile)
    except RuntimeError as exc:
        db.rollback()
        message = str(exc)
        if "GEMINI_API_KEY" in message or "not installed" in message:
            raise HTTPException(
                status_code=503, detail="AI coaching is not enabled on this server"
            ) from exc
        raise HTTPException(status_code=502, detail=message) from exc

    db.commit()
    return coach_service.insight_payload(insight)
