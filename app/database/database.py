from __future__ import annotations

import os
import socket
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_POSTGRES_USER = "postgres"
DEFAULT_POSTGRES_PASSWORD = ""
DEFAULT_POSTGRES_DB = "chesslytics_db"
DEFAULT_POSTGRES_PORT = "5432"
DEFAULT_SQLITE_URL = "sqlite:///./data/chess_mistakes.db"
INIT_DB_RETRIES = 15
INIT_DB_RETRY_DELAY = 2.0

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
        # 127.0.0.1 rather than "localhost": libpq can try ::1 first and fail on
        # machines where Postgres only listens on the IPv4 loopback.
        return "127.0.0.1"


def _postgres_url_from_env() -> str:
    user = os.environ.get("POSTGRES_USER", DEFAULT_POSTGRES_USER)
    password = os.environ.get("POSTGRES_PASSWORD", DEFAULT_POSTGRES_PASSWORD)
    db = os.environ.get("POSTGRES_DB", DEFAULT_POSTGRES_DB)
    port = os.environ.get("POSTGRES_PORT", DEFAULT_POSTGRES_PORT)
    host = _resolve_postgres_host(os.environ.get("POSTGRES_HOST"))
    credentials = quote_plus(user)
    if password:
        credentials = f"{credentials}:{quote_plus(password)}"
    return f"postgresql+psycopg2://{credentials}@{host}:{port}/{db}"


def database_url() -> str:
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    if os.environ.get("POSTGRES_DB") or os.environ.get("POSTGRES_USER"):
        return _postgres_url_from_env()
    return DEFAULT_SQLITE_URL


def _sqlite_file(url: str) -> Optional[Path]:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix) :]
    if not raw or raw == ":memory:":
        return None
    return Path(raw).expanduser()


def _connect_args(url: str) -> dict:
    path = _sqlite_file(url)
    if path is None:
        return {}
    if str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    return {"check_same_thread": False}


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = database_url()
        _engine = create_engine(
            url,
            connect_args=_connect_args(url),
            future=True,
            pool_pre_ping=True,
        )
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
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {kind}'
                    )
                )
                added.append(f"{table.name}.{column.name}")

    return added


def _wait_for_engine(engine: Engine) -> None:
    last_error: Optional[OperationalError] = None
    for attempt in range(1, INIT_DB_RETRIES + 1):
        try:
            with engine.connect():
                return
        except OperationalError as exc:
            last_error = exc
            if attempt < INIT_DB_RETRIES:
                time.sleep(INIT_DB_RETRY_DELAY)
    if last_error is not None:
        raise last_error


def init_db() -> None:
    from app.database.models import Base as ModelBase

    engine = get_engine()
    _wait_for_engine(engine)
    ModelBase.metadata.create_all(bind=engine)
    ensure_columns()
