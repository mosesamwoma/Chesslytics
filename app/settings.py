from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger("chesslytics")

TRUE_VALUES = {"1", "true", "yes", "on"}
RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "system",
    "support",
    "moderator",
    "chesslytics",
}

_ephemeral_secret: Optional[str] = None


def env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip()


def env_first(*names: str) -> str:
    for name in names:
        value = env_str(name)
        if value:
            return value
    return ""


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_str(name)
    if not raw:
        return default
    return raw.lower() in TRUE_VALUES


def env_int(name: str, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    raw = env_str(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_float(
    name: str, default: float, minimum: float = 0.0, maximum: Optional[float] = None
) -> float:
    raw = env_str(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def secret_key() -> bytes:
    global _ephemeral_secret
    configured = env_first("SECRET_KEY", "AUTH_SECRET")
    if len(configured) >= 32:
        return configured.encode("utf-8")
    if configured:
        logger.warning("SECRET_KEY is shorter than 32 characters; it is being ignored")
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(48)
        logger.warning(
            "SECRET_KEY is not set; using a random key that changes on every restart, "
            "so every session ends when the server restarts"
        )
    return _ephemeral_secret.encode("utf-8")


def admin_username() -> str:
    return env_first("ADMIN_USERNAME", "AUTH_USERNAME")


def admin_password() -> str:
    return env_first("ADMIN_PASSWORD", "AUTH_PASSWORD")


def registration_enabled() -> bool:
    return env_bool("ALLOW_REGISTRATION", True)


def docs_enabled() -> bool:
    return env_bool("ENABLE_DOCS", False)


def session_hours() -> float:
    return env_float("SESSION_HOURS", 24.0, minimum=0.25, maximum=24.0 * 30)


def trusted_proxy_hops() -> int:
    return env_int("TRUSTED_PROXY_HOPS", 0, minimum=0, maximum=5)


def max_upload_bytes() -> int:
    return env_int("MAX_UPLOAD_MB", 8, minimum=1, maximum=64) * 1024 * 1024


def max_games_per_upload() -> int:
    return env_int("MAX_GAMES_PER_UPLOAD", 300, minimum=1, maximum=5000)


def max_games_per_user() -> int:
    return env_int("MAX_GAMES_PER_USER", 1500, minimum=1, maximum=100000)


def max_plies_per_game() -> int:
    return env_int("MAX_PLIES_PER_GAME", 600, minimum=10, maximum=2000)


def max_analysis_depth() -> int:
    return env_int("MAX_ANALYSIS_DEPTH", 18, minimum=1, maximum=40)


def max_analysis_seconds() -> float:
    return env_float("MAX_ANALYSIS_SECONDS", 2.0, minimum=0.01, maximum=60.0)


def max_concurrent_jobs() -> int:
    return env_int("MAX_CONCURRENT_JOBS", 2, minimum=1, maximum=32)


def max_queued_jobs() -> int:
    return env_int("MAX_QUEUED_JOBS", 40, minimum=1, maximum=1000)


def max_concurrent_grading() -> int:
    return env_int("MAX_CONCURRENT_GRADING", 2, minimum=1, maximum=32)


def coach_daily_limit() -> int:
    return env_int("COACH_DAILY_LIMIT", 10, minimum=0, maximum=1000)


def job_retention_days() -> int:
    return env_int("JOB_RETENTION_DAYS", 14, minimum=1, maximum=365)


def profiles_kept_per_user() -> int:
    return env_int("PROFILES_KEPT_PER_USER", 5, minimum=1, maximum=100)


def public_url() -> str:
    value = env_str("PUBLIC_URL").rstrip("/")
    if value.startswith(("http://", "https://")):
        return value
    return ""


def smtp_host() -> str:
    return env_str("SMTP_HOST")


def smtp_port() -> int:
    return env_int("SMTP_PORT", 587, minimum=1, maximum=65535)


def smtp_user() -> str:
    return env_str("SMTP_USER")


def smtp_password() -> str:
    value = os.environ.get("SMTP_PASSWORD")
    return value if value is not None else ""


def smtp_from() -> str:
    return env_str("SMTP_FROM")


def smtp_security() -> str:
    value = env_str("SMTP_SECURITY", "starttls").lower()
    return value if value in ("starttls", "ssl", "none") else "starttls"


def email_enabled() -> bool:
    return bool(smtp_host() and smtp_from() and public_url())


def daily_puzzle_goal() -> int:
    return env_int("DAILY_PUZZLE_GOAL", 5, minimum=1, maximum=100)


def import_months() -> int:
    return env_int("IMPORT_MAX_MONTHS", 6, minimum=1, maximum=24)


def max_backup_bytes() -> int:
    return env_int("MAX_BACKUP_MB", 32, minimum=1, maximum=256) * 1024 * 1024


def log_format() -> str:
    return "json" if env_str("LOG_FORMAT", "text").lower() == "json" else "text"


def sentry_dsn() -> str:
    return env_str("SENTRY_DSN")


def sentry_environment() -> str:
    return env_str("SENTRY_ENVIRONMENT", "production")


def sentry_traces_rate() -> float:
    return env_float("SENTRY_TRACES_SAMPLE_RATE", 0.0, minimum=0.0, maximum=1.0)
