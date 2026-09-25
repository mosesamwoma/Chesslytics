from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Game
from app.services import game_service

router = APIRouter(prefix="/api/games", tags=["games"])


@router.post("/upload")
async def upload_games(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    try:
        path = game_service.save_upload(file.filename or "upload.pgn", content)
        result = game_service.import_pgn(
            db,
            text=content.decode("utf-8", errors="replace"),
            source=path.name,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()

    stored = list(
        db.scalars(select(Game).where(Game.fingerprint.in_(result["fingerprints"])))
    )
    return {
        "uploaded": path.name,
        "parsed": result["parsed"],
        "stored": result["stored"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "games": [game_service.game_summary(game) for game in stored],
    }


@router.get("")
def list_games(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    rows = game_service.list_games(db, limit=limit, offset=offset)
    return {
        "total": game_service.count_games(db),
        "limit": limit,
        "offset": offset,
        "games": [game_service.game_summary(row) for row in rows],
    }


@router.get("/{game_id}")
def get_game(game_id: int, db: Session = Depends(get_db)) -> dict:
    game = game_service.get_game(db, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game_service.game_with_moves(game)


@router.delete("/{game_id}")
def delete_game(game_id: int, db: Session = Depends(get_db)) -> dict:
    if not game_service.delete_game(db, game_id):
        raise HTTPException(status_code=404, detail="game not found")
    db.commit()
    return {"deleted": game_id}
