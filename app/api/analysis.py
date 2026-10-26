from __future__ import annotations

import asyncio
import json
import threading
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, settings
from app.api.common import read_upload
from app.api.games import (
    IMPORTS_PER_HOUR,
    UPLOADS_PER_HOUR,
    ImportRequest,
    import_remote,
    import_text,
    require_usable,
    throttle,
)
from app.database.database import get_db, session_scope
from app.database.models import Game, Mistake, User
from app.sample import SAMPLE_PGN, SAMPLE_PLAYER
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
    rating_aware: bool = False
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
    rating_aware: bool = False,
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
            "rating_aware": rating_aware,
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
        request.rating_aware,
    )
    return {"job": start_job(db, user, params)}


def params_for(
    db: Session,
    user: User,
    result: dict,
    player: Optional[str],
    color: str,
    depth: Optional[int],
    time_limit: Optional[float],
    min_loss: float,
    time_pressure: float,
    ignore_decided: bool,
    rating_aware: bool = False,
) -> dict:
    rows = game_service.games_by_fingerprint(db, user.id, result["fingerprints"])
    return build_params(
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
        True,
        rating_aware,
    )


def launch(db: Session, user: User, result: dict, params: dict) -> dict:
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
    rating_aware: bool = Form(default=False),
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    throttle(user, "upload", UPLOADS_PER_HOUR, "uploads")
    limit = build_limit(depth, time_limit)
    text = await read_upload(file)
    result = import_text(db, user, file.filename or "upload.pgn", text)
    require_usable(db, result)
    db.commit()
    params = params_for(
        db,
        user,
        result,
        player,
        color,
        depth,
        time_limit,
        min_loss,
        time_pressure,
        ignore_decided,
        rating_aware,
    )
    params["limit"] = limit
    return launch(db, user, result, params)


@router.post("/import", status_code=202)
def import_and_analyze(
    request: ImportRequest,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    throttle(user, "import", IMPORTS_PER_HOUR, "imports")
    result = import_remote(db, user, request)
    require_usable(db, result)
    db.commit()
    params = params_for(
        db, user, result, request.username.strip(), "both", None, None, 1.0, 30.0, True
    )
    return launch(db, user, result, params)


@router.post("/sample", status_code=202)
def analyze_sample(
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
) -> dict:
    throttle(user, "upload", UPLOADS_PER_HOUR, "uploads")
    result = import_text(db, user, "sample.pgn", SAMPLE_PGN)
    require_usable(db, result)
    db.commit()
    params = params_for(
        db, user, result, SAMPLE_PLAYER, "both", None, None, 1.0, 30.0, True
    )
    return launch(db, user, result, params)


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


def job_snapshot(owner_id: int, job_id: int) -> Optional[dict]:
    with session_scope() as session:
        job = job_service.get_job(session, owner_id, job_id)
        return job_service.job_payload(job) if job is not None else None


MAX_STREAMS_PER_USER = 4
STREAM_SECONDS = 3600
_streams: dict[int, int] = {}
_streams_lock = threading.Lock()


def open_stream(owner_id: int) -> bool:
    with _streams_lock:
        if _streams.get(owner_id, 0) >= MAX_STREAMS_PER_USER:
            return False
        _streams[owner_id] = _streams.get(owner_id, 0) + 1
        return True


def close_stream(owner_id: int) -> None:
    with _streams_lock:
        remaining = _streams.get(owner_id, 0) - 1
        if remaining > 0:
            _streams[owner_id] = remaining
        else:
            _streams.pop(owner_id, None)

STREAM_TICK = 1.0
STREAM_HEARTBEAT = 15


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: int,
    request: Request,
    user: User = Depends(auth.current_user),
) -> StreamingResponse:
    owner_id = user.id
    if not open_stream(owner_id):
        raise HTTPException(
            status_code=429,
            detail="too many live progress connections; close another tab and try again",
            headers={"Retry-After": "5"},
        )

    async def events():
        last = None
        elapsed = 0.0
        quiet = 0.0
        try:
            while elapsed < STREAM_SECONDS:
                if await request.is_disconnected():
                    return
                payload = await run_in_threadpool(job_snapshot, owner_id, job_id)
                if payload is None:
                    yield "event: gone\ndata: {}\n\n"
                    return
                blob = json.dumps(payload)
                if blob != last:
                    last = blob
                    quiet = 0.0
                    yield f"data: {blob}\n\n"
                elif quiet >= STREAM_HEARTBEAT:
                    quiet = 0.0
                    yield ": keep-alive\n\n"
                if payload["status"] in job_service.FINISHED_STATUSES:
                    return
                await asyncio.sleep(STREAM_TICK)
                elapsed += STREAM_TICK
                quiet += STREAM_TICK
        finally:
            close_stream(owner_id)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


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
