from __future__ import annotations

import io
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import chess.pgn
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import settings
from app.chess.book import open_book
from app.chess.engine import ChessEngine, SearchLimit, find_stockfish
from app.chess.evaluator import (
    MATE_SCORE_CP,
    analyze_games,
    analyze_games_parallel,
    clamp_loss,
    score_to_cp,
)
from app.chess.pgn_parser import load_games, parse_pgn
from app.database.models import (
    CoachInsight,
    Game,
    Mistake,
    Pattern,
    PlayerProfile,
    PuzzleAttempt,
)
from app.mining.mistake_detector import MinerConfig
from app.mining.pattern_miner import MIN_GAMES_FOR_PATTERN, mine_patterns
from app.mining.profiler import build_profile, label_for
from app.services import game_service

SCHEMA_VERSION = 2
DEFAULT_DEPTH = 12
DEFAULT_WORKERS = 1

_file_lock = threading.Lock()


class JobCancelled(Exception):
    pass


def analysis_dir() -> Path:
    path = Path(os.environ.get("ANALYSIS_DIR", "data/analysis")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_file() -> Path:
    override = os.environ.get("ANALYSIS_CACHE")
    if override:
        return Path(override).expanduser()
    return analysis_dir() / "eval_cache.json"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def default_limit() -> SearchLimit:
    seconds = _env_float("STOCKFISH_TIME", 0.0)
    if seconds > 0:
        return SearchLimit("time", seconds)
    return SearchLimit("depth", _env_float("STOCKFISH_DEPTH", float(DEFAULT_DEPTH)))


def _write_json(target: Path, payload: dict) -> None:
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with _file_lock:
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()


def load_cache(path: Optional[str] = None) -> dict:
    target = Path(path) if path else cache_file()
    if not target.exists():
        return {}
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def cache_is_compatible(cache: dict, engine_name: str, limit: SearchLimit) -> bool:
    meta = cache.get("meta") or {}
    if meta.get("schema_version") != SCHEMA_VERSION:
        return False
    if meta.get("engine") != engine_name:
        return False
    return meta.get("limit") == limit.as_key()


def save_cache(
    games: dict, engine_name: str, limit: SearchLimit, path: Optional[str] = None
) -> Path:
    target = Path(path) if path else cache_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "engine": engine_name,
            "limit": limit.as_key(),
            "created": datetime.now(timezone.utc).isoformat(),
        },
        "games": games,
    }
    _write_json(target, payload)
    return target


def analyze_source(
    session: Optional[Session] = None,
    user_id: Optional[int] = None,
    text: Optional[str] = None,
    path: Optional[str] = None,
    config: Optional[MinerConfig] = None,
    limit: Optional[SearchLimit] = None,
    engine_path: Optional[str] = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress=None,
    persist: bool = True,
    source: Optional[str] = None,
    cache_path: Optional[str] = None,
    book: Optional[str] = None,
    workers: int = DEFAULT_WORKERS,
    verify_with: Optional[str] = None,
) -> dict:
    if text is not None:
        games, errors = parse_pgn(text)
    elif path is not None:
        games, errors = load_games(path)
    else:
        raise ValueError("either text or path is required")

    if not games:
        return {
            "games": 0,
            "analyzed_games": 0,
            "errors": errors,
            "mistakes": [],
            "patterns": {},
            "recurring": {},
            "context": {},
            "book": {},
            "config": (config or MinerConfig()).as_dict(),
            "profile": {},
        }

    if persist and session is not None and user_id is not None:
        game_service.store_games(session, user_id, games, source)

    report = analyze_games_objects(
        session=session,
        user_id=user_id,
        games=games,
        config=config,
        limit=limit,
        engine_path=engine_path,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress=progress,
        persist=persist,
        cache_path=cache_path,
        book=book,
        workers=workers,
        verify_with=verify_with,
    )
    report["errors"] = errors
    return report


def verify_cache_file() -> Path:
    override = os.environ.get("VERIFY_CACHE")
    if override:
        return Path(override).expanduser()
    return analysis_dir() / "verify_cache.json"


def load_verify_cache() -> dict:
    path = verify_cache_file()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_verify_cache(entries: dict) -> Path:
    path = verify_cache_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "created": datetime.now(timezone.utc).isoformat(),
        },
        "positions": entries,
    }
    _write_json(path, payload)
    return path


def position_score(
    engine: ChessEngine,
    board: chess.Board,
    entries: dict,
    engine_name: str,
    limit: SearchLimit,
) -> int:
    if board.is_checkmate():
        return -MATE_SCORE_CP
    if board.is_game_over():
        return 0

    key = f"{engine_name}|{limit.kind}:{limit.value}|{board.fen()}"
    hit = entries.get(key)
    if hit is not None:
        return int(hit)

    info = engine.analyse(board, limit.to_engine_limit())
    cp, _mate = score_to_cp(info["score"], board.turn)
    entries[key] = cp
    return cp


def after_position(mistake: dict) -> Optional[chess.Board]:
    fen_after = mistake.get("fen_after")
    if fen_after:
        try:
            return chess.Board(fen_after)
        except ValueError:
            return None
    fen = mistake.get("fen")
    if not fen:
        return None
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    move = None
    if mistake.get("played_uci"):
        try:
            move = chess.Move.from_uci(mistake["played_uci"])
        except ValueError:
            move = None
    if move is None and mistake.get("played_move"):
        try:
            move = board.parse_san(mistake["played_move"])
        except ValueError:
            return None
    if move is None or move not in board.legal_moves:
        return None
    board.push(move)
    return board


def verify_mistakes(
    mistakes: list[dict],
    engine_path: str,
    limit: SearchLimit,
    notify=None,
    min_loss: float = 1.0,
) -> dict:
    notify = notify or (lambda _message: None)
    entries = load_verify_cache()
    agreed = 0
    disputed = 0
    unverified = 0
    engine_name = "unknown"

    with ChessEngine(find_stockfish(engine_path), limit) as engine:
        engine_name = engine.name
        for index, mistake in enumerate(mistakes, start=1):
            fen = mistake.get("fen")
            board = after_position(mistake)
            if not fen or board is None:
                unverified += 1
                continue

            try:
                before = chess.Board(fen)
            except ValueError:
                unverified += 1
                continue
            if before.is_game_over():
                unverified += 1
                continue

            notify(f"[{index}/{len(mistakes)}] verifying move {mistake.get('move_number')}")
            cp_before = position_score(engine, before, entries, engine_name, limit)
            cp_after = position_score(engine, board, entries, engine_name, limit)
            loss_cp = clamp_loss(cp_before + cp_after)
            loss_pawns = round(max(loss_cp, 0) / 100.0, 2)

            mistake["verified_by"] = engine_name
            mistake["verified_loss"] = loss_pawns
            mistake["agreed"] = loss_pawns >= min_loss
            if mistake["agreed"]:
                agreed += 1
            else:
                disputed += 1

    save_verify_cache(entries)
    total = agreed + disputed

    return {
        "engine": engine_name,
        "limit": limit.as_key(),
        "verified": total,
        "agreed": agreed,
        "disputed": disputed,
        "unverified": unverified,
        "agreement": round(100.0 * agreed / total, 1) if total else None,
    }


def analyze_games_objects(
    session: Optional[Session] = None,
    user_id: Optional[int] = None,
    games: Optional[list[chess.pgn.Game]] = None,
    config: Optional[MinerConfig] = None,
    limit: Optional[SearchLimit] = None,
    engine_path: Optional[str] = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress=None,
    persist: bool = True,
    cache_path: Optional[str] = None,
    book: Optional[str] = None,
    workers: int = DEFAULT_WORKERS,
    verify_with: Optional[str] = None,
    persist_scope=None,
    update_profile: bool = True,
) -> dict:
    games = games or []
    config = config or MinerConfig()
    limit = limit or default_limit()
    notify = progress or (lambda _message: None)
    binary = find_stockfish(engine_path)

    chosen_book = book or config.book
    reader = open_book(chosen_book)
    try:
        cached = {} if (rebuild_cache or not use_cache) else load_cache(cache_path)

        if workers > 1 and len(games) > 1:
            probe = ChessEngine(binary, limit)
            with probe:
                engine_name = probe.name
            if cached and not cache_is_compatible(cached, engine_name, limit):
                notify("cache was built with a different engine or search limit; re-analyzing")
                cached = {}
            results, counts = analyze_games_parallel(
                games, binary, limit, cached, notify, workers
            )
        else:
            engine = ChessEngine(binary, limit)
            with engine:
                engine_name = engine.name
                if cached and not cache_is_compatible(cached, engine_name, limit):
                    notify("cache was built with a different engine or search limit; re-analyzing")
                    cached = {}
                results, counts = analyze_games(games, engine, limit, cached, notify)

        if use_cache:
            merged = dict(cached.get("games") or {})
            merged.update(results)
            save_cache(merged, engine_name, limit, cache_path)

        report = mine_patterns(results, config, reader)
    finally:
        if reader is not None:
            reader.close()

    if verify_with:
        report["verify"] = verify_mistakes(
            report["mistakes"], verify_with, limit, notify, config.min_loss
        )

    report["profile"] = build_profile(report)
    report["engine"] = engine_name
    report["limit"] = limit.as_key()
    report["counts"] = counts
    report["workers"] = max(1, workers)
    report["games"] = len(games)
    report["analyzed_games"] = len(results)

    if persist and user_id is not None and results:
        if session is not None:
            report["persistence"] = persist_analysis(
                session, user_id, results, report, config, engine_name, limit, update_profile
            )
        elif persist_scope is not None:
            with persist_scope() as persist_session:
                report["persistence"] = persist_analysis(
                    persist_session,
                    user_id,
                    results,
                    report,
                    config,
                    engine_name,
                    limit,
                    update_profile,
                )

    return report


def games_from_rows(rows: list[Game]) -> list[chess.pgn.Game]:
    games: list[chess.pgn.Game] = []
    for row in rows:
        if not row.pgn:
            continue
        try:
            game = chess.pgn.read_game(io.StringIO(row.pgn))
        except Exception:
            continue
        if game is not None:
            games.append(game)
    return games


def reanalyze(
    session: Session,
    user_id: int,
    game_ids: Optional[list[int]] = None,
    config: Optional[MinerConfig] = None,
    limit: Optional[SearchLimit] = None,
    engine_path: Optional[str] = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress=None,
    book: Optional[str] = None,
    workers: int = DEFAULT_WORKERS,
    verify_with: Optional[str] = None,
) -> dict:
    statement = select(Game).where(Game.user_id == user_id)
    if game_ids:
        statement = statement.where(Game.id.in_(game_ids))
    rows = list(session.scalars(statement.order_by(Game.id)))
    games = games_from_rows(rows)
    if not games:
        raise ValueError("no stored games with PGN data to analyze")
    return analyze_games_objects(
        session=session,
        user_id=user_id,
        games=games,
        config=config,
        limit=limit,
        engine_path=engine_path,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress=progress,
        persist=True,
        book=book,
        workers=workers,
        verify_with=verify_with,
    )


def persist_analysis(
    session: Session,
    user_id: int,
    results: dict,
    report: dict,
    config: MinerConfig,
    engine_name: str,
    limit: SearchLimit,
    update_profile: bool = True,
) -> dict:
    fingerprints = list(results)
    rows = game_service.games_by_fingerprint(session, user_id, fingerprints)
    by_fingerprint = {row.fingerprint: row for row in rows}

    stored_moves = 0
    for fingerprint, payload in results.items():
        game = by_fingerprint.get(fingerprint)
        if game is None:
            continue
        stored_moves += game_service.store_moves(session, game, payload.get("moves") or [])
        game.analyzed_at = datetime.now(timezone.utc)
        game.analyzed_depth = int(limit.value) if limit.kind == "depth" else None
    session.flush()

    stored_ids = [game.id for game in by_fingerprint.values()]
    existing: dict[tuple[int, int], Mistake] = {}
    if stored_ids:
        for row in session.scalars(select(Mistake).where(Mistake.game_id.in_(stored_ids))):
            existing[(row.game_id, row.ply)] = row

    kept: set[tuple[int, int]] = set()
    stored_mistakes = 0
    for record in report["mistakes"]:
        game = by_fingerprint.get(record.get("game_key"))
        if game is None:
            continue
        key = (game.id, record.get("ply") or 0)
        if key in kept:
            continue
        kept.add(key)
        row = existing.get(key)
        if row is None:
            row = Mistake(game_id=game.id)
            session.add(row)
        _apply_mistake(row, user_id, record)
        stored_mistakes += 1

    stale_ids = [row.id for key, row in existing.items() if key not in kept]
    if stale_ids:
        session.execute(delete(PuzzleAttempt).where(PuzzleAttempt.mistake_id.in_(stale_ids)))
        session.execute(delete(Mistake).where(Mistake.id.in_(stale_ids)))
    session.flush()

    if not update_profile:
        return {
            "games": len(by_fingerprint),
            "moves": stored_moves,
            "mistakes": stored_mistakes,
            "patterns": 0,
            "profile_id": None,
        }

    profile = PlayerProfile(
        user_id=user_id,
        player=game_service.fit(config.player, 128),
        color=config.color,
        games_analyzed=report["context"].get("games_analyzed", 0),
        moves_scored=report["context"].get("moves_scored", 0),
        moves_failed=report["context"].get("moves_failed", 0),
        mistake_count=len(report["mistakes"]),
        average_loss=report["profile"].get("average_loss", 0.0),
        depth=int(limit.value) if limit.kind == "depth" else None,
        engine=game_service.fit(engine_name, 128),
        payload=report["profile"],
    )
    session.add(profile)
    session.flush()

    stored_patterns = _store_patterns(session, profile.id, report)
    session.flush()
    prune_profiles(session, user_id)

    return {
        "games": len(by_fingerprint),
        "moves": stored_moves,
        "mistakes": stored_mistakes,
        "patterns": stored_patterns,
        "profile_id": profile.id,
    }


def prune_profiles(session: Session, user_id: int) -> None:
    keep = settings.profiles_kept_per_user()
    old = list(
        session.scalars(
            select(PlayerProfile.id)
            .where(PlayerProfile.user_id == user_id)
            .order_by(PlayerProfile.created_at.desc(), PlayerProfile.id.desc())
            .offset(keep)
        )
    )
    if not old:
        return
    session.execute(delete(CoachInsight).where(CoachInsight.profile_id.in_(old)))
    session.execute(delete(Pattern).where(Pattern.profile_id.in_(old)))
    session.execute(delete(PlayerProfile).where(PlayerProfile.id.in_(old)))
    session.flush()


def _apply_mistake(row: Mistake, user_id: int, record: dict) -> Mistake:
    row.user_id = user_id
    row.ply = record.get("ply") or 0
    row.move_number = record.get("move_number") or 0
    row.color = record.get("color") or "white"
    row.player = game_service.fit(record.get("player"), 128)
    row.opponent = game_service.fit(record.get("opponent"), 128)
    row.played_move = game_service.fit(record.get("played_move"), 16)
    row.played_uci = game_service.fit(record.get("played_uci"), 8)
    row.best_move = game_service.fit(record.get("best_move"), 16)
    row.best_move_uci = game_service.fit(record.get("best_move_uci"), 8)
    row.fen = record.get("fen")
    row.fen_after = record.get("fen_after")
    row.eval_before = record.get("eval_before") or 0.0
    row.eval_after = record.get("eval_after") or 0.0
    row.loss = record.get("loss") or 0.0
    row.loss_cp = record.get("loss_cp") or 0
    row.winpct_before = record.get("winpct_before") or 0.0
    row.winpct_after = record.get("winpct_after") or 0.0
    row.severity = record.get("severity") or "normal"
    row.category = record.get("category") or "unknown"
    row.category_basis = record.get("category_basis")
    row.phase = record.get("phase") or "unknown"
    row.opening = game_service.fit(record.get("opening"), 255)
    row.in_time_pressure = bool(record.get("in_time_pressure"))
    row.time_remaining = record.get("time_remaining")
    row.game_decided = bool(record.get("game_decided"))
    row.book_move = game_service.fit(record.get("book_move"), 16)
    row.in_book = record.get("in_book")
    row.verified_by = game_service.fit(record.get("verified_by"), 128)
    row.verified_loss = record.get("verified_loss")
    row.agreed = record.get("agreed")
    row.facts = record.get("facts")
    return row


def _store_patterns(session: Session, profile_id: int, report: dict) -> int:
    stored = 0
    for kind, rows in (report.get("patterns") or {}).items():
        for row in rows:
            key = str(row["key"])
            session.add(
                Pattern(
                    profile_id=profile_id,
                    kind=kind,
                    key=game_service.fit(key, 255),
                    count=row["count"],
                    games=row["games"],
                    recurring=row["games"] >= MIN_GAMES_FOR_PATTERN,
                    description=label_for(key) if kind == "category" else None,
                )
            )
            stored += 1
    return stored


def list_profiles(session: Session, user_id: int, limit: int = 20) -> list[PlayerProfile]:
    statement = (
        select(PlayerProfile)
        .where(PlayerProfile.user_id == user_id)
        .order_by(PlayerProfile.created_at.desc(), PlayerProfile.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(session.scalars(statement))


def latest_profile(
    session: Session, user_id: int, player: Optional[str] = None
) -> Optional[PlayerProfile]:
    statement = select(PlayerProfile).where(PlayerProfile.user_id == user_id)
    if player:
        statement = statement.where(PlayerProfile.player == player)
    statement = statement.order_by(
        PlayerProfile.created_at.desc(), PlayerProfile.id.desc()
    ).limit(1)
    return session.scalars(statement).first()


def profile_payload(profile: PlayerProfile) -> dict:
    return {
        "id": profile.id,
        "player": profile.player,
        "color": profile.color,
        "games_analyzed": profile.games_analyzed,
        "moves_scored": profile.moves_scored,
        "moves_failed": profile.moves_failed,
        "mistake_count": profile.mistake_count,
        "average_loss": profile.average_loss,
        "depth": profile.depth,
        "engine": profile.engine,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "profile": profile.payload or {},
        "patterns": [pattern_to_dict(pattern) for pattern in profile.patterns],
    }


def pattern_to_dict(pattern: Pattern) -> dict:
    return {
        "id": pattern.id,
        "kind": pattern.kind,
        "key": pattern.key,
        "count": pattern.count,
        "games": pattern.games,
        "recurring": pattern.recurring,
        "description": pattern.description,
    }


def list_mistakes(
    session: Session,
    user_id: int,
    game_id: Optional[int] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    player: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Mistake]:
    statement = select(Mistake).where(Mistake.user_id == user_id)
    if game_id is not None:
        statement = statement.where(Mistake.game_id == game_id)
    if category:
        statement = statement.where(Mistake.category == category)
    if severity:
        statement = statement.where(Mistake.severity == severity)
    if player:
        statement = statement.where(Mistake.player == player)
    statement = (
        statement.order_by(Mistake.loss_cp.desc(), Mistake.id)
        .limit(max(1, min(limit, 500)))
        .offset(max(0, offset))
    )
    return list(session.scalars(statement))
