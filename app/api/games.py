from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, security, settings
from app.api.common import read_upload
from app.database.database import get_db
from app.database.models import Game, User
from app.services import game_service, user_service

router = APIRouter(prefix="/api/games", tags=["games"])

UPLOADS_PER_HOUR = 30


def quota_for(user: User) -> int | None:
    if user.role == user_service.ROLE_ADMIN:
        return None
    return settings.max_games_per_user()


def import_text(db: Session, user: User, filename: str, text: str) -> dict:
    try:
        source = game_service.safe_filename(filename)
        result = game_service.import_pgn(db, user.id, text, source, quota_for(user))
    except game_service.QuotaExceeded as exc:
        db.rollback()
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["source"] = source
    return result


@router.post("/upload")
async def upload_games(
    file: UploadFile = File(...),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    wait = security.limiter.consume(f"upload:{user.id}", UPLOADS_PER_HOUR, 3600)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"too many uploads; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )
    text = await read_upload(file)
    result = import_text(db, user, file.filename or "upload.pgn", text)
    if not result["fingerprints"]:
        db.rollback()
        detail = "no usable games found in that file"
        if result["errors"]:
            detail = f"{detail}: {result['errors'][0]}"
        raise HTTPException(status_code=400, detail=detail)
    db.commit()
    stored = game_service.games_by_fingerprint(db, user.id, result["fingerprints"])
    return {
        "uploaded": result["source"],
        "parsed": result["parsed"],
        "stored": result["stored"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "games": [game_service.game_summary(game, 0, 0) for game in stored[:200]],
    }


@router.get("")
def list_games(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    total = int(
        db.scalar(select(func.count(Game.id)).where(Game.user_id == user.id)) or 0
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "games": game_service.list_games(db, user.id, limit=limit, offset=offset),
    }


@router.get("/{game_id}")
def get_game(
    game_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    game = game_service.get_game(db, user.id, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game_service.game_with_moves(game)


@router.delete("/{game_id}")
def delete_game(
    game_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not game_service.delete_game(db, user.id, game_id):
        raise HTTPException(status_code=404, detail="game not found")
    db.commit()
    return {"deleted": game_id}
