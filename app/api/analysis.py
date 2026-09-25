from __future__ import annotations

from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chess.engine import SearchLimit
from app.database.database import get_db
from app.database.models import Game
from app.mining.mistake_detector import MinerConfig
from app.services import analysis_service, export_service, game_service

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisRequest(BaseModel):
    game_ids: Optional[list[int]] = None
    player: Optional[str] = None
    color: str = "both"
    depth: Optional[int] = Field(default=None, ge=1, le=40)
    time_limit: Optional[float] = Field(default=None, gt=0)
    min_loss: float = Field(default=1.0, ge=0)
    time_pressure: float = Field(default=30.0, ge=0)
    inaccuracy: float = Field(default=0.5, ge=0)
    mistake: float = Field(default=1.0, ge=0)
    blunder: float = Field(default=2.0, ge=0)
    ignore_decided: bool = True
    use_cache: bool = True
    rebuild_cache: bool = False
    stockfish_path: Optional[str] = None
    workers: int = Field(default=1, ge=1, le=64)
    verify_with: Optional[str] = None
    book: Optional[str] = None
    exclude_book: bool = False


class ExportRequest(AnalysisRequest):
    format: str = "csv"


def _config_from(request: AnalysisRequest) -> MinerConfig:
    return _config(
        request.player,
        request.color,
        request.min_loss,
        request.time_pressure,
        request.inaccuracy,
        request.mistake,
        request.blunder,
        request.ignore_decided,
        request.book,
        request.exclude_book,
    )


def _config(
    player: Optional[str],
    color: str,
    min_loss: float,
    time_pressure: float,
    inaccuracy: float,
    mistake: float,
    blunder: float,
    ignore_decided: bool,
    book: Optional[str] = None,
    exclude_book: bool = False,
) -> MinerConfig:
    return MinerConfig(
        min_loss=min_loss,
        time_pressure=time_pressure,
        player=player or None,
        color=color,
        inaccuracy=inaccuracy,
        mistake=mistake,
        blunder=blunder,
        ignore_decided=ignore_decided,
        book=book,
        exclude_book=exclude_book,
    )


def _limit(depth: Optional[int], time_limit: Optional[float]) -> SearchLimit:
    if time_limit is not None:
        return SearchLimit("time", time_limit)
    return SearchLimit("depth", float(depth or analysis_service.DEFAULT_DEPTH))


def _report_summary(report: dict) -> dict:
    return {
        "engine": report.get("engine"),
        "limit": report.get("limit"),
        "counts": report.get("counts"),
        "persistence": report.get("persistence"),
        "errors": report.get("errors", []),
        "context": report.get("context", {}),
        "config": report.get("config", {}),
        "book": report.get("book", {}),
        "verify": report.get("verify", {}),
        "profile": report.get("profile", {}),
        "patterns": report.get("patterns", {}),
        "recurring": report.get("recurring", {}),
        "largest": report.get("largest"),
        "mistakes": report.get("mistakes", []),
    }


@router.post("/run")
def run_analysis(request: AnalysisRequest, db: Session = Depends(get_db)) -> dict:
    config = _config_from(request)
    try:
        report = analysis_service.reanalyze(
            session=db,
            game_ids=request.game_ids,
            config=config,
            limit=_limit(request.depth, request.time_limit),
            engine_path=request.stockfish_path,
            use_cache=request.use_cache,
            rebuild_cache=request.rebuild_cache,
            book=request.book,
            workers=request.workers,
            verify_with=request.verify_with,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.commit()
    return _report_summary(report)


EXPORT_FILENAMES = {
    "json": "chess-mistakes.json",
    "csv": "chess-mistakes.csv",
    "jsonl": "chess-mistakes.jsonl",
}


@router.post("/export")
def export_mistakes(request: ExportRequest, db: Session = Depends(get_db)) -> Response:
    fmt = request.format.strip().lower()
    if fmt not in export_service.FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown export format {fmt!r}; expected one of "
                f"{', '.join(export_service.FORMATS)}"
            ),
        )
    try:
        report = analysis_service.reanalyze(
            session=db,
            game_ids=request.game_ids,
            config=_config_from(request),
            limit=_limit(request.depth, request.time_limit),
            engine_path=request.stockfish_path,
            use_cache=request.use_cache,
            rebuild_cache=request.rebuild_cache,
            book=request.book,
            workers=request.workers,
            verify_with=request.verify_with,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.commit()
    return Response(
        content=export_service.render(report, fmt),
        media_type=export_service.content_type(fmt),
        headers={
            "Content-Disposition": f'attachment; filename="{EXPORT_FILENAMES[fmt]}"',
            "X-Mistake-Count": str(len(report.get("mistakes") or [])),
        },
    )


@router.post("/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    player: Optional[str] = Form(default=None),
    color: str = Form(default="both"),
    depth: Optional[int] = Form(default=None),
    time_limit: Optional[float] = Form(default=None),
    min_loss: float = Form(default=1.0),
    time_pressure: float = Form(default=30.0),
    ignore_decided: bool = Form(default=True),
    use_cache: bool = Form(default=True),
    rebuild_cache: bool = Form(default=False),
    stockfish_path: Optional[str] = Form(default=None),
    workers: int = Form(default=1),
    verify_with: Optional[str] = Form(default=None),
    book: Optional[str] = Form(default=None),
    exclude_book: bool = Form(default=False),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    try:
        path = game_service.save_upload(file.filename or "upload.pgn", content)
        report = analysis_service.analyze_source(
            session=db,
            text=content.decode("utf-8", errors="replace"),
            source=path.name,
            config=_config(
                player,
                color,
                min_loss,
                time_pressure,
                0.5,
                1.0,
                2.0,
                ignore_decided,
                book,
                exclude_book,
            ),
            limit=_limit(depth, time_limit),
            engine_path=stockfish_path,
            use_cache=use_cache,
            rebuild_cache=rebuild_cache,
            persist=True,
            workers=max(1, workers),
            verify_with=verify_with,
            book=book,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.commit()
    summary = _report_summary(report)
    summary["uploaded"] = path.name
    summary["parsed"] = report.get("analyzed_games", 0)
    return summary


@router.get("/cache")
def cache_info() -> dict:
    cache = analysis_service.load_cache()
    games = cache.get("games") or {}
    moves = sum(len(entry.get("moves") or []) for entry in games.values())
    return {
        "path": str(analysis_service.cache_file()),
        "meta": cache.get("meta") or {},
        "games": len(games),
        "moves": moves,
    }


@router.delete("/cache")
def clear_cache() -> dict:
    path = analysis_service.cache_file()
    if path.exists():
        path.unlink()
        return {"cleared": str(path)}
    return {"cleared": None}


@router.get("/mistakes")
def list_mistakes(
    game_id: Optional[int] = Query(default=None),
    category: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    player: Optional[str] = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    rows = analysis_service.list_mistakes(
        db,
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
def analyzed_game(game_id: int, db: Session = Depends(get_db)) -> dict:
    return game_service.game_detail(_game_or_404(db, game_id))


def _game_or_404(db: Session, game_id: int) -> Game:
    game = db.scalar(select(Game).where(Game.id == game_id))
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game
