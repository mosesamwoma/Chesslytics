from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, security, settings
from app.chess.engine import SearchLimit
from app.database.database import get_db
from app.database.models import User
from app.services import analysis_service, training_service

router = APIRouter(prefix="/api/training", tags=["training"])

ATTEMPTS_PER_MINUTE = 40


class AttemptRequest(BaseModel):
    uci: str = Field(min_length=4, max_length=5, pattern=r"^[a-hA-H][1-8][a-hA-H][1-8][qrbnQRBN]?$")
    depth: Optional[int] = Field(default=None, ge=1, le=40)
    time_limit: Optional[float] = Field(default=None, gt=0, le=60)


def _limit(depth: Optional[int], time_limit: Optional[float]) -> SearchLimit:
    if time_limit is not None:
        if time_limit > settings.max_analysis_seconds():
            raise HTTPException(status_code=400, detail="time_limit is too large")
        return SearchLimit("time", time_limit)
    if depth:
        if depth > settings.max_analysis_depth():
            raise HTTPException(status_code=400, detail="depth is too large")
        return SearchLimit("depth", float(depth))
    return analysis_service.default_limit()


def _mistake_or_404(db: Session, user: User, puzzle_id: int):
    mistake = training_service.get_mistake(db, user.id, puzzle_id)
    if mistake is None:
        raise HTTPException(status_code=404, detail="puzzle not found")
    return mistake


@router.get("/puzzles")
def list_puzzles(
    category: Optional[str] = Query(default=None, max_length=32),
    severity: Optional[str] = Query(default=None, max_length=16),
    player: Optional[str] = Query(default=None, max_length=128),
    unseen_only: bool = Query(default=False),
    practice: Literal["all", "queue", "due", "new"] = Query(default="all"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    puzzles, total = training_service.list_puzzles(
        db,
        user.id,
        category=category,
        severity=severity,
        player=player,
        unseen_only=unseen_only,
        limit=limit,
        offset=offset,
        practice=practice,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "puzzles": puzzles,
        "tolerance_winpct": training_service.tolerance(),
    }


@router.get("/puzzles/{puzzle_id}")
def get_puzzle(
    puzzle_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)
) -> dict:
    mistake = _mistake_or_404(db, user, puzzle_id)
    puzzle = training_service.to_puzzle(
        mistake,
        training_service.attempt_summary(db, user.id, mistake.id),
        training_service.review_states(db, user.id, [mistake.id]).get(mistake.id),
    )
    if puzzle is None:
        raise HTTPException(
            status_code=422, detail="this mistake has no stored position to replay"
        )
    return puzzle


@router.post("/puzzles/{puzzle_id}/attempt")
def attempt_puzzle(
    puzzle_id: int,
    request: AttemptRequest,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    wait = security.limiter.consume(f"attempt:{user.id}", ATTEMPTS_PER_MINUTE, 60)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"slow down; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )
    mistake = _mistake_or_404(db, user, puzzle_id)
    try:
        result = training_service.grade(
            db,
            user.id,
            mistake,
            request.uci,
            limit=_limit(request.depth, request.time_limit),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except training_service.EngineBusy as exc:
        db.rollback()
        raise HTTPException(
            status_code=503, detail=str(exc), headers={"Retry-After": "5"}
        ) from exc

    db.commit()
    return result


@router.get("/puzzles/{puzzle_id}/solution")
def reveal_solution(
    puzzle_id: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)
) -> dict:
    mistake = _mistake_or_404(db, user, puzzle_id)
    return training_service.solution(mistake)


@router.get("/attempts")
def list_attempts(
    limit: int = Query(20, ge=1, le=200),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = training_service.recent_attempts(db, user.id, limit=limit)
    return {"attempts": [training_service.attempt_to_dict(row) for row in rows]}


@router.get("/stats")
def training_stats(
    user: User = Depends(auth.current_user), db: Session = Depends(get_db)
) -> dict:
    return training_service.stats(db, user.id)
