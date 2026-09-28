from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services import analysis_service, coach_service

router = APIRouter(prefix="/api/coach", tags=["coach"])


@router.get("")
def get_insight(
    player: Optional[str] = Query(default=None),
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    profile = analysis_service.latest_profile(db, player=player)
    if profile is None:
        raise HTTPException(status_code=404, detail="no profile has been generated yet")

    try:
        insight = coach_service.get_or_create(db, profile, force=refresh)
    except RuntimeError as exc:
        db.rollback()
        message = str(exc)
        unavailable = "GROQ_API_KEY" in message or "not installed" in message
        status_code = 503 if unavailable else 502
        raise HTTPException(status_code=status_code, detail=message) from exc

    db.commit()
    return coach_service.insight_payload(insight)
