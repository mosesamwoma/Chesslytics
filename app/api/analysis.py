from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, security, settings
from app.api.common import read_upload
from app.api.games import UPLOADS_PER_HOUR, import_text
from app.database.database import get_db
from app.database.models import Game, Mistake, User
from app.services import (
    analysis_service,
    export_service,
    game_service,
    job_service,
    progress_service,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

EXPORT_ROW_LIMIT = 50000
Color = Literal["white", "black", "both"]


class AnalysisRequest(BaseModel):
    game_ids: Optional[list[int]] = Field(default=None, max_length=5000)
    player: Optional[str] = Field(default=None, max_length=128)
    color: Color = "both"
    depth: Optional[int] = Field(default=None, ge=1, le=40)
    time_limit: Optional[float] = Field(default=None, gt=0, le=60)
    min_loss: float = Field(default=1.0, ge=0, le=100)
    time_pressure: float = Field(default=30.0, ge=0, le=3600)
    inaccuracy: float = Field(default=0.5, ge=0, le=100)
    mistake: float = Field(default=1.0, ge=0, le=100)
    blunder: float = Field(default=2.0, ge=0, le=100)
    ignore_decided: bool = True
    update_profile: bool = True


def build_limit(depth: Optional[int], time_limit: Optional[float]) -> dict:
    if time_limit is not None:
        if time_limit > settings.max_analysis_seconds():
            raise HTTPException(
                status_code=400,
                detail=f"time_limit may not exceed {settings.max_analysis_seconds():g} seconds",
            )
        return {"kind": "time", "value": time_limit}
    if depth:
        if depth > settings.max_analysis_depth():
            raise HTTPException(
                status_code=400,
                detail=f"depth may not exceed {settings.max_analysis_depth()}",
            )
        return {"kind": "depth", "value": float(depth)}
    default = analysis_service.default_limit()
    return {"kind": default.kind, "value": default.value}


def build_params(
    game_ids: list[int],
    player: Optional[str],
    color: str,
    depth: Optional[int],
    time_limit: Optional[float],
    min_loss: float,
    time_pressure: float,
    inaccuracy: float,
    mistake: float,
    blunder: float,
    ignore_decided: bool,
    update_profile: bool = True,
) -> dict:
    return {
        "game_ids": game_ids,
        "update_profile": update_profile,
        "limit": build_limit(depth, time_limit),
        "config": {
            "player": (player or "").strip() or None,
            "color": color,
            "min_loss": min_loss,
            "time_pressure": time_pressure,
            "inaccuracy": inaccuracy,
            "mistake": mistake,
            "blunder": blunder,
            "ignore_decided": ignore_decided,
        },
    }


def start_job(db: Session, user: User, params: dict) -> dict:
    try:
        job = job_service.create_job(db, user.id, params, len(params["game_ids"]))
    except job_service.JobRejected as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    db.commit()
    job_service.submit(job.id)
    return job_service.job_payload(job)


@router.post("/run", status_code=202)
def run_analysis(
    request: AnalysisRequest,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    statement = select(Game.id).where(Game.user_id == user.id)
    if request.game_ids:
        statement = statement.where(Game.id.in_(request.game_ids))
    ids = list(db.scalars(statement.order_by(Game.id)))
    if not ids:
        raise HTTPException(status_code=400, detail="no stored games to analyze")
    params = build_params(
        ids,
        request.player or progress_service.tracked_player(db, user.id),
        request.color,
        request.depth,
        request.time_limit,
        request.min_loss,
        request.time_pressure,
        request.inaccuracy,
        request.mistake,
        request.blunder,
        request.ignore_decided,
        request.update_profile,
    )
    return {"job": start_job(db, user, params)}


@router.post("/upload", status_code=202)
async def upload_and_analyze(
    file: UploadFile = File(...),
    player: Optional[str] = Form(default=None, max_length=128),
    color: Color = Form(default="both"),
    depth: Optional[int] = Form(default=None, ge=1, le=40),
    time_limit: Optional[float] = Form(default=None, gt=0, le=60),
    min_loss: float = Form(default=1.0, ge=0, le=100),
    time_pressure: float = Form(default=30.0, ge=0, le=3600),
    ignore_decided: bool = Form(default=True),
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
    limit = build_limit(depth, time_limit)
    text = await read_upload(file)
    result = import_text(db, user, file.filename or "upload.pgn", text)
    if not result["fingerprints"]:
        db.rollback()
        detail = "no usable games found in that file"
        if result["errors"]:
            detail = f"{detail}: {result['errors'][0]}"
        raise HTTPException(status_code=400, detail=detail)
    db.commit()

    rows = game_service.games_by_fingerprint(db, user.id, result["fingerprints"])
    params = build_params(
        sorted(row.id for row in rows),
        player,
        color,
        depth,
        time_limit,
        min_loss,
        time_pressure,
        0.5,
        1.0,
        2.0,
        ignore_decided,
    )
    params["limit"] = limit

    job = None
    job_error = None
    try:
        created = job_service.create_job(db, user.id, params, len(params["game_ids"]))
        db.commit()
        job_service.submit(created.id)
        job = job_service.job_payload(created)
    except job_service.JobRejected as exc:
        db.rollback()
        job_error = str(exc)

    return {
        "uploaded": result["source"],
        "parsed": result["parsed"],
        "stored": result["stored"],
        "skipped": result["skipped"],
        "errors": result["errors"],
        "job": job,
        "job_error": job_error,
    }


@router.get("/jobs")
def list_jobs(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {
        "total": job_service.count_jobs(db, user.id),
        "limit": limit,
        "offset": offset,
        "jobs": [
            job_service.job_payload(job)
            for job in job_service.list_jobs(db, user.id, limit, offset)
        ],
    }


@router.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = job_service.get_job(db, user.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": job_service.job_payload(job)}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = job_service.get_job(db, user.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    job_service.request_cancel(db, job)
    db.commit()
    return {"job": job_service.job_payload(job)}


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(
    job_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = job_service.get_job(db, user.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in job_service.ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="that analysis is still in progress")
    try:
        params = job_service.retry_params(db, user.id, job)
    except job_service.JobRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"job": start_job(db, user, params)}


@router.get("/export")
def export_mistakes(
    format: str = Query("csv", max_length=8),
    category: Optional[str] = Query(default=None, max_length=32),
    severity: Optional[str] = Query(default=None, max_length=16),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> Response:
    fmt = format.strip().lower()
    if fmt not in export_service.FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown export format; expected one of {', '.join(export_service.FORMATS)}",
        )
    statement = (
        select(Mistake, Game.fingerprint)
        .join(Game, Game.id == Mistake.game_id)
        .where(Mistake.user_id == user.id)
    )
    if category:
        statement = statement.where(Mistake.category == category)
    if severity:
        statement = statement.where(Mistake.severity == severity)
    statement = statement.order_by(Mistake.loss_cp.desc(), Mistake.id).limit(EXPORT_ROW_LIMIT)

    records = []
    for mistake, fingerprint in db.execute(statement).all():
        record = game_service.mistake_to_dict(mistake)
        record["game_key"] = fingerprint
        records.append(record)

    return Response(
        content=export_service.render({"mistakes": records}, fmt),
        media_type=export_service.content_type(fmt),
        headers={
            "Content-Disposition": f'attachment; filename="chesslytics-mistakes.{export_service.extension(fmt)}"',
            "X-Mistake-Count": str(len(records)),
        },
    )


@router.get("/mistakes")
def list_mistakes(
    game_id: Optional[int] = Query(default=None),
    category: Optional[str] = Query(default=None, max_length=32),
    severity: Optional[str] = Query(default=None, max_length=16),
    player: Optional[str] = Query(default=None, max_length=128),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = analysis_service.list_mistakes(
        db,
        user.id,
        game_id=game_id,
        category=category,
        severity=severity,
        player=player,
        limit=limit,
        offset=offset,
    )
    return {
        "limit": limit,
        "offset": offset,
        "mistakes": [game_service.mistake_to_dict(row) for row in rows],
    }


@router.get("/games/{game_id}")
def analyzed_game(
    game_id: int,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    game = game_service.get_game(db, user.id, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game_service.game_detail(game)
