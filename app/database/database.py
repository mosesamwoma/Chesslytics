from __future__ import annotations

import logging
import os
import socket
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import settings

logger = logging.getLogger("chesslytics")

DEFAULT_POSTGRES_USER = "postgres"
DEFAULT_POSTGRES_PASSWORD = ""
DEFAULT_POSTGRES_DB = "chesslytics_db"
DEFAULT_POSTGRES_PORT = "5432"
DEFAULT_SQLITE_URL = "sqlite:///./data/chess_mistakes.db"
INIT_DB_RETRIES = 15
INIT_DB_RETRY_DELAY = 2.0
ADVISORY_LOCK_KEY = 727274201

USER_OWNED_TABLES = (
    "games",
    "mistakes",
    "puzzle_attempts",
    "player_profiles",
    "coach_insights",
)

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


class Base(DeclarativeBase):
    pass


def _resolve_postgres_host(explicit: Optional[str]) -> str:
    if explicit and explicit.lower() != "auto":
        return explicit
    try:
        socket.gethostbyname("postgres")
        return "postgres"
    except OSError:
        return "127.0.0.1"


def _postgres_url_from_env() -> str:
    user = os.environ.get("POSTGRES_USER", "").strip() or DEFAULT_POSTGRES_USER
    password = os.environ.get("POSTGRES_PASSWORD", DEFAULT_POSTGRES_PASSWORD)
    db = os.environ.get("POSTGRES_DB", "").strip() or DEFAULT_POSTGRES_DB
    port = os.environ.get("POSTGRES_PORT", "").strip() or DEFAULT_POSTGRES_PORT
    host = _resolve_postgres_host(os.environ.get("POSTGRES_HOST", "").strip() or None)
    credentials = quote_plus(user)
    if password:
        credentials = f"{credentials}:{quote_plus(password)}"
    return f"postgresql+psycopg2://{credentials}@{host}:{port}/{quote_plus(db)}"


def _normalize_url(url: str) -> str:
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix) :]
    return url


def database_urls() -> list[str]:
    urls: list[str] = []
    explicit = os.environ.get("DATABASE_URL", "").strip()
    if explicit:
        urls.append(_normalize_url(explicit))
    if os.environ.get("POSTGRES_USER", "").strip():
        urls.append(_postgres_url_from_env())
    if not urls:
        urls.append(DEFAULT_SQLITE_URL)
    return list(dict.fromkeys(urls))


def database_url() -> str:
    return database_urls()[0]


def describe_url(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "unparseable database url"


def _sqlite_file(url: str) -> Optional[Path]:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix) :]
    if not raw or raw == ":memory:":
        return None
    return Path(raw).expanduser()


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


def _build_engine(url: str) -> Engine:
    if _is_sqlite(url):
        path = _sqlite_file(url)
        if path is not None and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            future=True,
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            if path is not None:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine

    return create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        pool_recycle=settings.env_int("DB_POOL_RECYCLE", 300, minimum=30),
        pool_size=settings.env_int("DB_POOL_SIZE", 5, minimum=1, maximum=50),
        max_overflow=settings.env_int("DB_MAX_OVERFLOW", 5, minimum=0, maximum=50),
        connect_args={"connect_timeout": settings.env_int("DB_CONNECT_TIMEOUT", 15, minimum=1)},
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine(database_url())
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def ensure_columns() -> list[str]:
    from app.database.models import Base as ModelBase

    engine = get_engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    preparer = engine.dialect.identifier_preparer
    added: list[str] = []

    for table in ModelBase.metadata.sorted_tables:
        if table.name not in tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        missing = [
            column
            for column in table.columns
            if column.name not in present and not column.primary_key
        ]
        if not missing:
            continue
        with engine.begin() as connection:
            for column in missing:
                kind = column.type.compile(engine.dialect)
                connection.execute(
                    text(
                        f"ALTER TABLE {preparer.quote(table.name)} "
                        f"ADD COLUMN {preparer.quote(column.name)} {kind}"
                    )
                )
                added.append(f"{table.name}.{column.name}")

    return added


def migrate_schema() -> list[str]:
    engine = get_engine()
    inspector = inspect(engine)
    applied: list[str] = []

    with engine.begin() as connection:
        for index in inspector.get_indexes("games"):
            if index.get("name") == "ix_games_fingerprint" and index.get("unique"):
                connection.execute(text("DROP INDEX IF EXISTS ix_games_fingerprint"))
                applied.append("dropped unique index ix_games_fingerprint")
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_games_fingerprint ON games (fingerprint)")
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_games_user_fingerprint "
                "ON games (user_id, fingerprint)"
            )
        )
        for table in USER_OWNED_TABLES:
            connection.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id)")
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_verified_email "
                "ON users (email_key) WHERE email_verified_at IS NOT NULL"
            )
        )

    return applied


def _connect_first_available() -> Engine:
    global _engine, _session_factory
    urls = database_urls()
    last_error: Optional[OperationalError] = None
    for attempt in range(1, INIT_DB_RETRIES + 1):
        for url in urls:
            candidate = _build_engine(url)
            try:
                with candidate.connect():
                    pass
            except OperationalError as exc:
                last_error = exc
                candidate.dispose()
                continue
            if _engine is not None:
                _engine.dispose()
            _engine = candidate
            _session_factory = None
            return candidate
        if attempt < INIT_DB_RETRIES:
            logger.warning(
                "database not reachable (attempt %s/%s), retrying", attempt, INIT_DB_RETRIES
            )
            time.sleep(INIT_DB_RETRY_DELAY)
    if last_error is not None:
        raise last_error
    raise RuntimeError("no database url configured")


def init_db() -> None:
    from app.database.models import Base as ModelBase

    engine = _connect_first_available()
    logger.info("database ready: %s", describe_url(str(engine.url)))
    lock_connection = None
    try:
        if engine.dialect.name == "postgresql":
            lock_connection = engine.connect()
            lock_connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
            )
        ModelBase.metadata.create_all(bind=engine)
        ensure_columns()
        migrate_schema()
    finally:
        if lock_connection is not None:
            try:
                lock_connection.rollback()
            finally:
                lock_connection.close()
