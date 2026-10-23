from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth, security, settings
from app.api.common import read_upload
from app.database.database import get_db
from app.database.models import User
from app.services import game_service, import_service, progress_service, user_service

router = APIRouter(prefix="/api/games", tags=["games"])

UPLOADS_PER_HOUR = 30
IMPORTS_PER_HOUR = 8


class GameUpdate(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=4000)
    tags: Optional[list[str]] = Field(default=None, max_length=40)


class ImportRequest(BaseModel):
    source: Literal["chesscom", "lichess"]
    username: str = Field(min_length=2, max_length=40)
    max_games: int = Field(default=50, ge=1, le=500)
    months: int = Field(default=1, ge=1, le=24)
    analyze: bool = False


def quota_for(user: User) -> int | None:
    if user.role == user_service.ROLE_ADMIN:
        return None
    return settings.max_games_per_user()


def throttle(user: User, name: str, limit: int, noun: str) -> None:
    wait = security.limiter.consume(f"{name}:{user.id}", limit, 3600)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"too many {noun}; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )


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


def import_remote(db: Session, user: User, request: ImportRequest) -> dict:
    try:
        games, errors = import_service.download(
            request.source, request.username, request.max_games, request.months
        )
        label = import_service.source_label(request.source, request.username.strip())
        result = game_service.import_games(
            db, user.id, games, errors, label, quota_for(user)
        )
    except import_service.InvalidUsername as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except import_service.ImportFailed as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except game_service.QuotaExceeded as exc:
        db.rollback()
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["source"] = label
    return result


def require_usable(db: Session, result: dict) -> None:
    if result["fingerprints"]:
        return
    db.rollback()
    detail = "no usable games found in that file"
    if result["errors"]:
        detail = f"{detail}: {result['errors'][0]}"
    raise HTTPException(status_code=400, detail=detail)


def upload_response(db: Session, user: User, result: dict) -> dict:
    stored = game_service.games_by_fingerprint(db, user.id, result["fingerprints"])
    return {
        "uploaded": result["source"],
        "parsed": result["parsed"],
        "stored": result["stored"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "games": [game_service.game_summary(game, 0, 0) for game in stored[:200]],
    }


@router.post("/upload")
async def upload_games(
    file: UploadFile = File(...),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    throttle(user, "upload", UPLOADS_PER_HOUR, "uploads")
    text = await read_upload(file)
    result = import_text(db, user, file.filename or "upload.pgn", text)
    require_usable(db, result)
    db.commit()
    return upload_response(db, user, result)


@router.post("/import")
def import_games(
    request: ImportRequest,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    throttle(user, "import", IMPORTS_PER_HOUR, "imports")
    result = import_remote(db, user, request)
    require_usable(db, result)
    db.commit()
    return upload_response(db, user, result)


@router.get("")
def list_games(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(default=None, max_length=80),
    result: Optional[Literal["1-0", "0-1", "1/2-1/2", "*", "won", "lost", "drawn"]] = Query(
        default=None
    ),
    analyzed: Optional[bool] = Query(default=None),
    opening: Optional[str] = Query(default=None, max_length=80),
    color: Optional[Literal["white", "black"]] = Query(default=None),
    tag: Optional[str] = Query(default=None, max_length=24),
    sort: Literal["date_desc", "date_asc", "mistakes_desc", "opening_asc"] = Query(
        default="date_desc"
    ),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    player = progress_service.tracked_player(db, user.id)
    filters = dict(
        q=q,
        result=result,
        analyzed=analyzed,
        opening=opening,
        color=color,
        player=player,
        tag=tag,
    )
    total = game_service.count_games_filtered(db, user.id, **filters)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "player": player,
        "games": game_service.list_games(
            db, user.id, limit=limit, offset=offset, sort=sort, **filters
        ),
    }


@router.get("/tags")
def list_tags(
    user: User = Depends(auth.current_user), db: Session = Depends(get_db)
) -> dict:
    return {"tags": game_service.all_tags(db, user.id)}


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


@router.get("/{game_id}/pgn")
def get_pgn(
    game_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    game = game_service.get_game(db, user.id, game_id)
    if game is None or not game.pgn:
        raise HTTPException(status_code=404, detail="no PGN is stored for this game")
    return {"pgn": game.pgn}


@router.patch("/{game_id}")
def update_game(
    game_id: int,
    payload: GameUpdate,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    game = game_service.get_game(db, user.id, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    fields = payload.model_fields_set
    try:
        if "notes" in fields:
            game.notes = game_service.clean_notes(payload.notes)
        if "tags" in fields:
            game.tags = game_service.clean_tags(payload.tags)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return game_service.game_summary(game)


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
