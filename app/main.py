from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import auth, observability, security, settings
from app.api import (
    account,
    admin,
    analysis,
    auth as auth_api,
    coach,
    games,
    patterns,
    training,
)
from app.chess.engine import SearchLimit
from app.database.database import init_db, session_scope
from app.mining.mistake_detector import MinerConfig
from app.mining.profiler import CATEGORY_LABELS, motif_label
from app.services import (
    analysis_service,
    export_service,
    job_service,
    token_service,
    user_service,
)

observability.configure_logging()
observability.init_sentry()
logger = logging.getLogger("chesslytics")

DEFAULT_PGN = os.path.join("data", "Jude254_vs_manmusaa_2026.09.30.pgn")
JSON_BODY_LIMIT = 1024 * 1024
UPLOAD_OVERHEAD = 1024 * 1024
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        limit = JSON_BODY_LIMIT
        if path.endswith("/upload"):
            limit = settings.max_upload_bytes() + UPLOAD_OVERHEAD
        elif path.endswith("/restore"):
            limit = settings.max_backup_bytes() + UPLOAD_OVERHEAD

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await self._reject(send)
            return

        received = 0
        started = False
        rejected = False

        async def limited_receive():
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    if not started and not rejected:
                        rejected = True
                        await self._reject(send)
                    raise BodyTooLarge()
            return message

        async def tracking_send(message) -> None:
            nonlocal started
            if rejected:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if not started and not rejected:
                await self._reject(send)

    @staticmethod
    async def _reject(send) -> None:
        body = b'{"detail":"request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with session_scope() as session:
        user_service.bootstrap_admin(session)
        user_service.prune_audit(session)
        token_service.prune(session)
    job_service.recover_interrupted()
    yield
    job_service.shutdown()


def cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "")
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        logger.warning("CORS_ORIGINS contains '*', which is not allowed with credentials; ignored")
        origins = [origin for origin in origins if origin != "*"]
    return origins


def allowed_hosts() -> list[str]:
    raw = os.environ.get("ALLOWED_HOSTS", "")
    return [host.strip() for host in raw.split(",") if host.strip()]


docs_on = settings.docs_enabled()
app = FastAPI(
    title="Chesslytics",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if docs_on else None,
    redoc_url=None,
    openapi_url="/openapi.json" if docs_on else None,
)


@app.middleware("http")
async def protect(request: Request, call_next):
    path = request.url.path
    is_api = path.startswith("/api/")
    if (
        is_api
        and request.method not in auth.SAFE_METHODS
        and not request.headers.get(auth.CSRF_HEADER)
    ):
        response = JSONResponse({"detail": "missing request protection header"}, status_code=403)
    else:
        response = await call_next(request)

    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if not (docs_on and path in DOC_PATHS):
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if security.is_https(request):
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    if is_api:
        response.headers["Cache-Control"] = "no-store"
    elif path.startswith("/assets/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    else:
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "internal server error"}, status_code=500)


if cors_origins():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Protection"],
        expose_headers=["Content-Disposition", "X-Mistake-Count", "Retry-After"],
    )
if allowed_hosts():
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(observability.RequestContextMiddleware)

app.include_router(auth_api.router)
app.include_router(account.router)
app.include_router(admin.router)
app.include_router(games.router)
app.include_router(analysis.router)
app.include_router(patterns.router)
app.include_router(training.router)
app.include_router(coach.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "chesslytics"}


class SinglePageFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def mount_frontend() -> None:
    directory = Path(os.environ.get("FRONTEND_DIST", "frontend/dist")).expanduser()
    if directory.is_dir():
        app.mount("/", SinglePageFiles(directory=str(directory), html=True), name="frontend")


mount_frontend()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chesslytics",
        description=(
            "Analyze many completed chess games and mine the mistakes you repeat."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python -m app.main --pgn data/Jude254_vs_manmusaa_2026.09.30.pgn\n"
            "  python -m app.main --player YourChessComName\n"
            "  python -m app.main --depth 16 --min-loss 0.5\n"
            "  python -m app.main --limit-time 0.05 --output report.json\n"
        ),
    )
    parser.add_argument("--pgn", default=DEFAULT_PGN, help="PGN file to read")
    parser.add_argument(
        "--cache",
        default=None,
        help="analysis cache file (default: $ANALYSIS_CACHE, else "
        "<ANALYSIS_DIR>/eval_cache.json). The web app reads the same file.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="engine search depth per position (default: $STOCKFISH_DEPTH, else 12)",
    )
    parser.add_argument(
        "--limit-time",
        type=float,
        default=None,
        help="search time in seconds per position; overrides --depth. Much faster "
        "on large collections, less reproducible.",
    )
    parser.add_argument(
        "--min-loss",
        type=float,
        default=1.0,
        help="minimum evaluation loss in pawns to report (default: 1.0). Below "
        "about 1.0 at depth 12, engine noise is comparable to the signal.",
    )
    parser.add_argument(
        "--player",
        default=None,
        help="only report mistakes by this player (matched against PGN headers). "
        "Without it, both sides are reported.",
    )
    parser.add_argument(
        "--color",
        choices=["white", "black", "both"],
        default="both",
        help="restrict to one side (default: both)",
    )
    parser.add_argument(
        "--time-pressure",
        type=float,
        default=30.0,
        help="seconds remaining below which a move counts as time-pressured "
        "(default: 30)",
    )
    parser.add_argument("--stockfish", default=None, help="path to the Stockfish binary")
    parser.add_argument(
        "--workers",
        type=int,
        default=_env_int("PARALLEL_WORKERS", 1),
        help="analyze this many games in parallel, each in its own engine process "
        "(default: 1, or $PARALLEL_WORKERS). Above 1 every worker is pinned to a single "
        "thread, because Stockfish otherwise uses every core on its own.",
    )
    parser.add_argument(
        "--verify-with",
        default=os.environ.get("VERIFY_WITH") or None,
        help="a second engine binary; every mistake is re-checked with it and marked "
        "agreed or disputed. One engine call per position re-checked, cached separately "
        "from the evaluation cache.",
    )
    parser.add_argument(
        "--book",
        default=None,
        help="Polyglot (.bin) opening book; mistakes played while the book still had a "
        "move are marked as theory (default: $BOOK_PATH)",
    )
    parser.add_argument(
        "--exclude-book",
        action="store_true",
        help="drop mistakes played while still in the opening book from every count",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="write the mistake records to a file; the format follows the file "
        "extension (.json, .csv, .jsonl)",
    )
    parser.add_argument(
        "--output-format",
        choices=export_service.FORMATS,
        default=None,
        help="override the format implied by the --output extension",
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="do not read or write the cache"
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="ignore any existing cache and re-analyze everything",
    )
    parser.add_argument(
        "--include-decided",
        action="store_true",
        help="also count mistakes made in already-decided positions",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="store the games and results in the database as well (requires --user)",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="username that owns the saved games; the account must already exist",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    return parser.parse_args(argv)


def describe_limit(limit: dict | None) -> str:
    if not limit:
        return "unknown"
    if limit.get("type") == "depth":
        return f"depth {int(limit['value'])}"
    return f"{float(limit['value']):.3g}s per position"


def format_report(report: dict, config: MinerConfig) -> str:
    lines: list[str] = []
    context = report.get("context") or {}
    mistakes = report.get("mistakes") or []
    profile = report.get("profile") or {}

    lines.append("")
    lines.append("Chesslytics")
    lines.append("=" * 11)
    lines.append("")
    lines.append(f"Engine: {report.get('engine')}  |  search: {describe_limit(report.get('limit'))}")
    workers = report.get("workers") or 1
    if workers > 1:
        lines.append(f"Workers: {workers} engine processes")
    lines.append(f"Games analyzed: {context.get('games_analyzed', 0)}")
    if config.player:
        lines.append(f"Games with {config.player}: {context.get('games_matched_player', 0)}")
    lines.append(f"Moves evaluated: {context.get('moves_scored', 0)}")
    lines.append(f"Mistakes found: {len(mistakes)} (loss >= {config.min_loss} pawns)")

    if config.player and context.get("player_not_found"):
        lines.append("")
        lines.append(
            f'  WARNING: no game in this file has "{config.player}" as a player. '
            f"Check the spelling against the PGN headers."
        )

    if not mistakes:
        lines.append("")
        lines.append(
            "No mistakes above the threshold. Either the games were played well, "
            "or the threshold is set high for the search depth used."
        )
        return "\n".join(lines)

    lines.append("")
    lines.append("Recurring patterns")
    lines.append("-" * 18)

    recurring = report.get("recurring", {}).get("category", [])
    if recurring:
        for index, row in enumerate(recurring, start=1):
            label = CATEGORY_LABELS.get(row["key"], row["key"])
            suffix = f"({row['games']} games)" if row["games"] > 1 else "(1 game)"
            lines.append(f"{index}. {label:<28} {row['count']:>4}  {suffix}")
    else:
        lines.append(
            "  Nothing recurs across independent games yet. Single occurrences "
            "are listed under the breakdown below."
        )

    lines.append("")
    lines.append("All categories")
    lines.append("-" * 14)
    for row in report.get("patterns", {}).get("category", []):
        label = CATEGORY_LABELS.get(row["key"], row["key"])
        lines.append(f"  {label:<28} {row['count']:>4}")

    phases = report.get("patterns", {}).get("phase", [])
    if phases:
        lines.append("")
        lines.append(f"Most common mistake phase: {phases[0]['key']}")

    severity = report.get("patterns", {}).get("severity", [])
    if severity:
        rendered = ", ".join(f"{row['key']} {row['count']}" for row in severity)
        lines.append(f"By severity: {rendered}")

    motifs = report.get("patterns", {}).get("motif", [])
    if motifs:
        lines.append("")
        lines.append("Tactics handed to the opponent")
        lines.append("-" * 30)
        for row in motifs:
            lines.append(
                f"  {motif_label(row['key']):<24} {row['count']:>4}  "
                f"({row['games']} game{'s' if row['games'] != 1 else ''})"
            )

    openings = report.get("recurring", {}).get("opening", [])
    if openings:
        lines.append("")
        lines.append("Openings where mistakes repeat")
        lines.append("-" * 30)
        for row in openings[:5]:
            lines.append(f"  {row['key']:<34} {row['count']:>4} ({row['games']} games)")

    largest = report.get("largest")
    if largest:
        lines.append("")
        lines.append("Largest single evaluation loss")
        lines.append("-" * 30)
        lines.append(
            f"  Game {largest['game_id']}, move {largest['move_number']} "
            f"({largest['color']})"
        )
        lines.append(f"  Played: {largest['played_move']}")
        lines.append(f"  Best:   {largest['best_move']}")
        if largest.get("book_move"):
            lines.append(f"  Book:   {largest['book_move']}")
        lines.append(
            f"  Loss:   {largest['loss']:.2f} pawns "
            f"({largest['eval_before']:+.2f} -> {largest['eval_after']:+.2f})"
        )
        lines.append(f"  Why:    {largest['category_basis']}")
        if largest.get("mate_before") is not None:
            lines.append(f"  Note:   mate in {largest['mate_before']} was available")
        if largest.get("agreed") is False:
            lines.append(
                f"  Note:   {largest.get('verified_by')} did not score this as a loss "
                f"(it measured {largest.get('verified_loss'):.2f} pawns)"
            )

    verify = report.get("verify") or {}
    if verify.get("verified"):
        lines.append("")
        lines.append("Engine agreement")
        lines.append("-" * 16)
        lines.append(
            f"  Verified with {verify['engine']} "
            f"({describe_limit(verify.get('limit'))})"
        )
        lines.append(
            f"  Agreed: {verify['agreed']} of {verify['verified']} mistakes "
            f"({verify.get('agreement')}%)"
        )
        lines.append(f"  Disputed: {verify['disputed']}")
        if verify.get("unverified"):
            lines.append(f"  Not checked: {verify['unverified']} (no stored position)")

    book = report.get("book") or {}
    if book.get("path"):
        lines.append("")
        lines.append("Opening book")
        lines.append("-" * 12)
        lines.append(f"  Book: {book['path']}")
        lines.append(
            f"  A book move existed in {book.get('in_book', 0)} of "
            f"{book.get('positions', 0)} positions examined"
        )
        if book.get("mistakes_in_book"):
            lines.append(
                f"  Mistakes played while still in book: {book['mistakes_in_book']}"
            )
        if book.get("median_book_move"):
            lines.append(
                f"  Book ran out at a median of move {book['median_book_move']} "
                f"({book.get('games_following_book', 0)} games reached it)"
            )
        if book.get("excluded"):
            lines.append(
                f"  Excluded from every count above: {book['excluded']} (still theory)"
            )

    if profile:
        lines.append("")
        lines.append("Profile")
        lines.append("-" * 7)
        lines.append(f"  Average loss per mistake: {profile.get('average_loss', 0.0):.2f} pawns")
        pressure = profile.get("time_pressure") or {}
        if pressure.get("count"):
            lines.append(
                f"  Time pressure: {pressure['count']} mistakes ({pressure['share']}%) "
                f"below {pressure.get('threshold_seconds')}s"
            )
        weakest = profile.get("tactical_weaknesses") or []
        if weakest:
            rendered = ", ".join(f"{row['label']} {row['count']}" for row in weakest)
            lines.append(f"  Tactical weaknesses: {rendered}")

    observations = profile.get("observations") or []
    if observations:
        lines.append("")
        lines.append("Observations")
        lines.append("-" * 12)
        for observation in observations:
            lines.append(f"  - {observation}")

    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = parse_args(argv)
    progress = (
        (lambda _message: None)
        if args.quiet
        else (lambda message: print(message, file=sys.stderr, flush=True))
    )

    if not os.path.exists(args.pgn):
        print(f"error: no PGN file at {args.pgn!r}", file=sys.stderr)
        print(
            f"\nExport your games from Chess.com and save them to {args.pgn}.\n"
            "  Chess.com -> Games -> select games -> Share & Export -> Download PGN",
            file=sys.stderr,
        )
        return 2

    if args.limit_time is not None:
        limit = SearchLimit("time", args.limit_time)
    elif args.depth is not None:
        limit = SearchLimit("depth", args.depth)
    else:
        limit = analysis_service.default_limit()
    config = MinerConfig(
        min_loss=args.min_loss,
        time_pressure=args.time_pressure,
        player=args.player,
        color=args.color,
        ignore_decided=not args.include_decided,
        book=args.book,
        exclude_book=args.exclude_book,
    )

    owner_id = None
    if args.save:
        if not args.user:
            print("error: --save needs --user USERNAME", file=sys.stderr)
            return 2
        init_db()
        with session_scope() as lookup:
            owner = user_service.get_by_username(lookup, args.user)
            if owner is None:
                print(f"error: no account named {args.user!r}", file=sys.stderr)
                return 2
            owner_id = owner.id

    started = time.monotonic()
    try:
        with (session_scope() if args.save else nullcontext(None)) as session:
            report = analysis_service.analyze_source(
                session=session,
                user_id=owner_id,
                path=args.pgn,
                config=config,
                limit=limit,
                engine_path=args.stockfish,
                use_cache=not args.no_cache,
                rebuild_cache=args.rebuild_cache,
                progress=progress,
                persist=args.save,
                cache_path=args.cache,
                book=args.book,
                workers=max(1, args.workers),
                verify_with=args.verify_with,
            )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    elapsed = time.monotonic() - started

    if report.get("games") == 0:
        print(f"error: no usable games found in {args.pgn!r}", file=sys.stderr)
        for error in (report.get("errors") or [])[:5]:
            print(f"  {error}", file=sys.stderr)
        return 2

    for error in report.get("errors") or []:
        print(f"warning: {error}", file=sys.stderr)

    counts = report.get("counts") or {}
    progress(
        f"Analyzed {counts.get('moves_analyzed', 0)} moves in {elapsed:.1f}s "
        f"({counts.get('games_analyzed', 0)} new games, "
        f"{counts.get('games_reused', 0)} from cache)"
    )
    failed = (report.get("context") or {}).get("moves_failed", 0)
    if failed:
        progress(f"warning: {failed} positions failed to evaluate")
    for failure in counts.get("failures") or []:
        progress(f"warning: a game could not be evaluated: {failure}")

    print(format_report(report, config))

    if args.output:
        try:
            fmt, written = export_service.write_report(
                report, args.output, args.output_format
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 5
        print(f"Wrote {written} records to {args.output} as {fmt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
