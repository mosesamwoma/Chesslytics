from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from app import settings

logger = logging.getLogger("chesslytics")
access_logger = logging.getLogger("chesslytics.access")

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
QUIET_PREFIXES = ("/assets/",)
QUIET_PATHS = ("/api/health",)
STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "request_id"}
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-csrf-protection"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(RequestIdFilter())
    if settings.log_format() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
            )
        )
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True


def _scrub(event: dict, _hint: dict) -> Optional[dict]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                name: value
                for name, value in headers.items()
                if name.lower() not in SENSITIVE_HEADERS
            }
    event.pop("user", None)
    return event


def init_sentry() -> bool:
    dsn = settings.sentry_dsn()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; error tracking is off")
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment(),
        traces_sample_rate=settings.sentry_traces_rate(),
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=_scrub,
    )
    logger.info("error tracking enabled")
    return True


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = ""
        for name, value in scope.get("headers") or []:
            if name == b"x-request-id":
                supplied = value.decode("latin-1")
                break
        request_id = supplied if REQUEST_ID_PATTERN.match(supplied) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = {"code": 500}

        async def tracking_send(message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        finally:
            path = scope.get("path", "")
            if path not in QUIET_PATHS and not path.startswith(QUIET_PREFIXES):
                access_logger.info(
                    "%s %s %s",
                    scope.get("method", "-"),
                    path,
                    status["code"],
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status["code"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            request_id_var.reset(token)
