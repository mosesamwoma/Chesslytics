from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from typing import Optional

from fastapi import Header, HTTPException

DEFAULT_USERNAME = "admin"
DEFAULT_TOKEN_HOURS = 12.0
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 300
LOCKOUT_SECONDS = 300

_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def auth_username() -> str:
    return os.environ.get("AUTH_USERNAME", "").strip() or DEFAULT_USERNAME


def auth_password() -> str:
    return os.environ.get("AUTH_PASSWORD", "")


def auth_enabled() -> bool:
    return bool(auth_password())


def token_ttl_seconds() -> int:
    raw = os.environ.get("AUTH_TOKEN_HOURS", "").strip()
    try:
        hours = float(raw) if raw else DEFAULT_TOKEN_HOURS
    except ValueError:
        hours = DEFAULT_TOKEN_HOURS
    if hours <= 0:
        hours = DEFAULT_TOKEN_HOURS
    return int(hours * 3600)


def _secret() -> bytes:
    configured = os.environ.get("AUTH_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    material = f"chesslytics|{auth_username()}|{auth_password()}"
    return hashlib.sha256(material.encode("utf-8")).digest()


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(body: str) -> str:
    return _encode(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())


def create_token(username: str, now: Optional[float] = None) -> str:
    issued = time.time() if now is None else now
    payload = {"sub": username, "exp": int(issued) + token_ttl_seconds()}
    body = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_token(token: str, now: Optional[float] = None) -> Optional[str]:
    try:
        body, signature = token.split(".", 1)
        if not hmac.compare_digest(signature.encode("ascii"), _sign(body).encode("ascii")):
            return None
        payload = json.loads(_decode(body))
        subject = payload["sub"]
        expires = int(payload["exp"])
    except (ValueError, KeyError, TypeError, UnicodeError):
        return None
    current = time.time() if now is None else now
    if current >= expires:
        return None
    if not isinstance(subject, str) or subject != auth_username():
        return None
    return subject


def credentials_match(username: str, password: str) -> bool:
    user_ok = hmac.compare_digest(username.encode("utf-8"), auth_username().encode("utf-8"))
    password_ok = hmac.compare_digest(password.encode("utf-8"), auth_password().encode("utf-8"))
    return user_ok and password_ok


def retry_after(key: str, now: Optional[float] = None) -> int:
    current = time.time() if now is None else now
    with _lock:
        recent = [stamp for stamp in _failures.get(key, []) if current - stamp < FAILURE_WINDOW_SECONDS]
        if recent:
            _failures[key] = recent
        else:
            _failures.pop(key, None)
        if len(recent) < MAX_FAILURES:
            return 0
        remaining = LOCKOUT_SECONDS - (current - recent[-1])
        return max(1, int(remaining + 0.999)) if remaining > 0 else 0


def register_failure(key: str, now: Optional[float] = None) -> None:
    current = time.time() if now is None else now
    with _lock:
        recent = [stamp for stamp in _failures.get(key, []) if current - stamp < FAILURE_WINDOW_SECONDS]
        recent.append(current)
        _failures[key] = recent[-MAX_FAILURES:]


def register_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def reset_limits() -> None:
    with _lock:
        _failures.clear()


def require_auth(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if not auth_enabled():
        return None
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = verify_token(token.strip())
    if subject is None:
        raise HTTPException(
            status_code=401,
            detail="invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return subject
