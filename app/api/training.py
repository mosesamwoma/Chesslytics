from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.chess.engine import SearchLimit
from app.database.database import get_db
from app.services import analysis_service, training_service

router = APIRouter(prefix="/api/training", tags=["training"])


class AttemptRequest(BaseModel):
    uci: str
    player: Optional[str] = None
    depth: Optional[int] = Field(default=None, ge=1, le=40)
    time_limit: Optional[float] = Field(default=None, gt=0)
    stockfish_path: Optional[str] = None


def _limit(depth: Optional[int], time_limit: Optional[float]) -> SearchLimit:
    if time_limit is not None:
        return SearchLimit("time", time_limit)
    return SearchLimit("depth", float(depth or analysis_service.DEFAULT_DEPTH))


def _mistake_or_404(db: Session, puzzle_id: int):
    mistake = training_service.get_mistake(db, puzzle_id)
    if mistake is None:
        raise HTTPException(status_code=404, detail="puzzle not found")
    return mistake


@router.get("/puzzles")
def list_puzzles(
    category: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    player: Optional[str] = Query(default=None),
    unseen_only: bool = Query(default=False),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    puzzles, total = training_service.list_puzzles(
        db,
        category=category,
        severity=severity,
        player=player,
        unseen_only=unseen_only,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "puzzles": puzzles,
        "tolerance_winpct": training_service.tolerance(),
    }


@router.get("/puzzles/{puzzle_id}")
def get_puzzle(puzzle_id: int, db: Session = Depends(get_db)) -> dict:
    mistake = _mistake_or_404(db, puzzle_id)
    puzzle = training_service.to_puzzle(
        mistake, training_service.attempt_summary(db, mistake.id)
    )
    if puzzle is None:
        raise HTTPException(
            status_code=422, detail="this mistake has no stored position to replay"
        )
    return puzzle


@router.post("/puzzles/{puzzle_id}/attempt")
def attempt_puzzle(
    puzzle_id: int, request: AttemptRequest, db: Session = Depends(get_db)
) -> dict:
    mistake = _mistake_or_404(db, puzzle_id)
    try:
        result = training_service.grade(
            db,
            mistake,
            request.uci,
            player=request.player,
            engine_path=request.stockfish_path,
            limit=_limit(request.depth, request.time_limit),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.commit()
    return result


@router.get("/puzzles/{puzzle_id}/solution")
def reveal_solution(puzzle_id: int, db: Session = Depends(get_db)) -> dict:
    mistake = _mistake_or_404(db, puzzle_id)
    return training_service.solution(mistake)


@router.get("/attempts")
def list_attempts(
    player: Optional[str] = Query(default=None),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    rows = training_service.recent_attempts(db, limit=limit, player=player)
    return {"attempts": [training_service.attempt_to_dict(row) for row in rows]}


@router.get("/stats")
def training_stats(
    player: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    return training_service.stats(db, player=player)
