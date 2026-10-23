from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app import security, settings
from app.chess.engine import SearchLimit
from app.database.database import session_scope
from app.database.models import AnalysisJob, Game, User, utcnow
from app.mining.mistake_detector import MinerConfig
from app.services import analysis_service

logger = logging.getLogger("chesslytics")

ACTIVE_STATUSES = ("queued", "running")
FINISHED_STATUSES = ("done", "failed", "cancelled")
PROGRESS_PATTERN = re.compile(r"^\[(\d+)/(\d+)\]\s*(\w*)")
JOBS_PER_HOUR = 30

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


class JobRejected(Exception):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.max_concurrent_jobs(), thread_name_prefix="analysis"
            )
        return _executor


def shutdown() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def job_duration(job: AnalysisJob) -> Optional[float]:
    started = _aware(job.started_at)
    if started is None:
        return None
    finished = _aware(job.finished_at) or utcnow()
    return round(max(0.0, (finished - started).total_seconds()), 1)


def job_options(job: AnalysisJob) -> dict:
    params = job.params or {}
    config = params.get("config") or {}
    limit = params.get("limit") or {}
    return {
        "player": config.get("player"),
        "color": config.get("color", "both"),
        "limit_kind": limit.get("kind"),
        "limit_value": limit.get("value"),
        "min_loss": config.get("min_loss"),
    }


def job_payload(job: AnalysisJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "duration_seconds": job_duration(job),
        "options": job_options(job),
        "total_games": job.total_games,
        "done_games": job.done_games,
        "message": job.message,
        "summary": job.summary,
        "error": job.error,
        "cancel_requested": bool(job.cancel_requested),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def get_job(session: Session, user_id: int, job_id: int) -> Optional[AnalysisJob]:
    return session.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user_id)
    )


def list_jobs(
    session: Session, user_id: int, limit: int = 10, offset: int = 0
) -> list[AnalysisJob]:
    return list(
        session.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.user_id == user_id)
            .order_by(AnalysisJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def count_jobs(session: Session, user_id: int) -> int:
    return int(
        session.scalar(
            select(func.count(AnalysisJob.id)).where(AnalysisJob.user_id == user_id)
        )
        or 0
    )


def retry_params(session: Session, user_id: int, job: AnalysisJob) -> dict:
    params = dict(job.params or {})
    wanted = [int(value) for value in (params.get("game_ids") or [])]
    existing = list(
        session.scalars(
            select(Game.id).where(Game.user_id == user_id, Game.id.in_(wanted or [0]))
        )
    )
    if not existing:
        raise JobRejected("the games from that analysis no longer exist", 400)
    params["game_ids"] = sorted(existing)
    limit = params.get("limit") or {}
    value = float(limit.get("value") or 0)
    too_deep = limit.get("kind") == "depth" and value > settings.max_analysis_depth()
    too_long = limit.get("kind") == "time" and value > settings.max_analysis_seconds()
    if too_deep or too_long or limit.get("kind") not in ("depth", "time"):
        default = analysis_service.default_limit()
        params["limit"] = {"kind": default.kind, "value": default.value}
    return params


def active_job(session: Session, user_id: int) -> Optional[AnalysisJob]:
    return session.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.user_id == user_id, AnalysisJob.status.in_(ACTIVE_STATUSES))
        .order_by(AnalysisJob.id.desc())
        .limit(1)
    )


def create_job(session: Session, user_id: int, params: dict, total_games: int) -> AnalysisJob:
    if active_job(session, user_id) is not None:
        raise JobRejected("an analysis is already running for your account")
    queued = int(
        session.scalar(
            select(func.count(AnalysisJob.id)).where(AnalysisJob.status == "queued")
        )
        or 0
    )
    if queued >= settings.max_queued_jobs():
        raise JobRejected("the analysis queue is full right now; try again shortly", 503)
    wait = security.limiter.consume(f"jobs:{user_id}", JOBS_PER_HOUR, 3600)
    if wait:
        raise JobRejected(f"too many analyses started; try again in {wait} seconds", 429)

    job = AnalysisJob(
        user_id=user_id,
        status="queued",
        params=params,
        total_games=total_games,
        done_games=0,
        message="waiting for a free analysis slot",
    )
    session.add(job)
    session.flush()
    return job


def submit(job_id: int) -> None:
    _pool().submit(run_job, job_id)


def request_cancel(session: Session, job: AnalysisJob) -> None:
    if job.status not in ACTIVE_STATUSES:
        return
    job.cancel_requested = True
    if job.status == "queued":
        job.message = "cancelling"
    session.flush()


def _finish(job_id: int, status: str, summary: Optional[dict] = None, error: Optional[str] = None) -> None:
    with session_scope() as session:
        job = session.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = utcnow()
        job.summary = summary
        job.error = error[:500] if error else None
        if status == "done":
            job.done_games = job.total_games
            job.message = "finished"
        elif status == "cancelled":
            job.message = "cancelled"
        else:
            job.message = "failed"


def _progress_writer(job_id: int):
    def notify(message: str) -> None:
        with session_scope() as session:
            job = session.get(AnalysisJob, job_id)
            if job is None or job.cancel_requested:
                raise analysis_service.JobCancelled()
            match = PROGRESS_PATTERN.match(message)
            if match:
                position, total, word = int(match.group(1)), int(match.group(2)), match.group(3)
                done = position - 1 if word == "analyzing" else position
                job.done_games = max(0, min(done, total))
                job.total_games = total
            job.message = message[:255]

    return notify


def _config_from(params: dict) -> MinerConfig:
    raw = params.get("config") or {}
    return MinerConfig(
        min_loss=float(raw.get("min_loss", 1.0)),
        time_pressure=float(raw.get("time_pressure", 30.0)),
        player=raw.get("player") or None,
        color=raw.get("color", "both"),
        inaccuracy=float(raw.get("inaccuracy", 0.5)),
        mistake=float(raw.get("mistake", 1.0)),
        blunder=float(raw.get("blunder", 2.0)),
        ignore_decided=bool(raw.get("ignore_decided", True)),
    )


def _limit_from(params: dict) -> SearchLimit:
    raw = params.get("limit") or {}
    kind = raw.get("kind")
    value = raw.get("value")
    if kind in ("depth", "time") and value:
        return SearchLimit(kind, float(value))
    return analysis_service.default_limit()


def _summarize(report: dict) -> dict:
    context = report.get("context") or {}
    persistence = report.get("persistence") or {}
    counts = report.get("counts") or {}
    return {
        "engine": report.get("engine"),
        "limit": report.get("limit"),
        "games": report.get("games", 0),
        "games_analyzed": context.get("games_analyzed", 0),
        "moves_scored": context.get("moves_scored", 0),
        "moves_failed": context.get("moves_failed", 0),
        "mistakes": len(report.get("mistakes") or []),
        "stored_mistakes": persistence.get("mistakes", 0),
        "failures": len(counts.get("failures") or []),
        "player_not_found": bool(context.get("player_not_found")),
    }


def _claim(job_id: int) -> Optional[dict]:
    with session_scope() as session:
        result = session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == "queued")
            .values(status="running", started_at=utcnow(), message="starting")
        )
        if not result.rowcount:
            return None
        job = session.get(AnalysisJob, job_id)
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = utcnow()
            job.message = "cancelled"
            return None
        user = session.get(User, job.user_id)
        if user is None or not user.is_active:
            job.status = "failed"
            job.finished_at = utcnow()
            job.error = "account is not available"
            return None
        return {"user_id": job.user_id, "params": dict(job.params or {})}


def run_job(job_id: int) -> None:
    try:
        claimed = _claim(job_id)
    except Exception:
        logger.exception("could not start analysis job %s", job_id)
        return
    if claimed is None:
        return

    user_id = claimed["user_id"]
    params = claimed["params"]
    try:
        with session_scope() as session:
            rows = list(
                session.scalars(
                    select(Game)
                    .where(Game.user_id == user_id, Game.id.in_(params.get("game_ids") or [0]))
                    .order_by(Game.id)
                )
            )
            games = analysis_service.games_from_rows(rows)
        if not games:
            raise ValueError("none of the selected games could be read")

        report = analysis_service.analyze_games_objects(
            session=None,
            user_id=user_id,
            games=games,
            config=_config_from(params),
            limit=_limit_from(params),
            use_cache=False,
            progress=_progress_writer(job_id),
            persist=True,
            workers=1,
            persist_scope=session_scope,
            update_profile=bool(params.get("update_profile", True)),
        )
        _finish(job_id, "done", summary=_summarize(report))
    except analysis_service.JobCancelled:
        _finish(job_id, "cancelled")
    except FileNotFoundError:
        logger.error("analysis engine not found for job %s", job_id)
        _finish(job_id, "failed", error="the analysis engine is not available on this server")
    except ValueError as exc:
        _finish(job_id, "failed", error=str(exc))
    except Exception:
        logger.exception("analysis job %s failed", job_id)
        _finish(job_id, "failed", error="the analysis failed unexpectedly; please try again")


def recover_interrupted() -> int:
    requeue: list[int] = []
    with session_scope() as session:
        session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.status == "running")
            .values(
                status="failed",
                finished_at=utcnow(),
                message="failed",
                error="interrupted by a server restart; please run the analysis again",
            )
        )
        requeue = list(
            session.scalars(
                select(AnalysisJob.id).where(AnalysisJob.status == "queued").order_by(AnalysisJob.id)
            )
        )
        cutoff = utcnow() - timedelta(days=settings.job_retention_days())
        session.execute(
            delete(AnalysisJob).where(
                AnalysisJob.status.not_in(ACTIVE_STATUSES), AnalysisJob.created_at < cutoff
            )
        )
    for job_id in requeue:
        submit(job_id)
    return len(requeue)
