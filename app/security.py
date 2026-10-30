from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from starlette.requests import Request

from app import settings

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LENGTH = 32
SCRYPT_SALT_BYTES = 16

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")

COMMON_PASSWORDS = {
    "password",
    "password1",
    "password12",
    "password123",
    "passw0rd123",
    "1234567890",
    "12345678901",
    "123456789012",
    "qwertyuiop",
    "qwerty12345",
    "qwerty123456",
    "1q2w3e4r5t",
    "iloveyou123",
    "letmein1234",
    "welcome1234",
    "admin12345",
    "administrator",
    "chesslytics",
    "chesslytics1",
    "chess123456",
    "changeme123",
    "abcdefghij",
    "0123456789",
    "9876543210",
}

TOKEN_VERSION = "v2"
COMMON_PASSWORD_FILE = Path(__file__).resolve().parent / "data" / "common_passwords.txt"
TRAILING_FILLER = "0123456789!@#$%^&*()-_=+.,?"
_common_cache: dict = {"words": None}


def common_password_list() -> frozenset:
    words = _common_cache["words"]
    if words is None:
        try:
            text = COMMON_PASSWORD_FILE.read_text(encoding="utf-8")
        except OSError:
            text = ""
        words = frozenset(line for line in text.splitlines() if line)
        _common_cache["words"] = words
    return words


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=128 * n * r * p * 2 + 1024 * 1024,
        dklen=SCRYPT_LENGTH,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n_text, r_text, p_text, salt_text, digest_text = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_text), int(r_text), int(p_text)
        if n < 2**10 or n > 2**20 or r < 1 or r > 32 or p < 1 or p > 8:
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        actual = _scrypt(password, salt, n, r, p)
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def password_needs_rehash(stored: str) -> bool:
    try:
        scheme, n_text, r_text, p_text, _salt, _digest = stored.split("$")
        return scheme != "scrypt" or (
            int(n_text) < SCRYPT_N or int(r_text) < SCRYPT_R or int(p_text) < SCRYPT_P
        )
    except ValueError:
        return True


DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    verify_password(password, DUMMY_HASH)


def normalize_username(username: str) -> str:
    return username.strip().lower()


def username_error(username: str, allow_reserved: bool = False) -> Optional[str]:
    if not USERNAME_PATTERN.match(username):
        return (
            "username must be 3 to 32 characters, start with a letter or digit, and use "
            "only letters, digits, dots, dashes and underscores"
        )
    if allow_reserved:
        return None
    key = normalize_username(username)
    reserved = set(settings.RESERVED_USERNAMES)
    configured = normalize_username(settings.admin_username())
    if configured:
        reserved.add(configured)
    if key in reserved:
        return "that username is reserved"
    return None


def password_error(password: str, username: Optional[str] = None) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"password must be at most {MAX_PASSWORD_LENGTH} characters"
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or "change_me" in lowered or "changeme" in lowered:
        return "that password is too common"
    common = common_password_list()
    stripped = lowered.strip(TRAILING_FILLER)
    if lowered in common or (len(stripped) >= 4 and stripped in common):
        return "that password is too common"
    if len(set(password)) < 4:
        return "password needs more variety"
    if username and len(username) >= 3 and normalize_username(username) in lowered:
        return "password must not contain the username"
    return None


def create_session_token(
    user_id: int, version: int, sid: str, now: Optional[float] = None
) -> str:
    issued = int(time.time() if now is None else now)
    ttl = int(settings.session_hours() * 3600)
    payload = {
        "uid": user_id,
        "ver": version,
        "sid": sid,
        "iat": issued,
        "exp": issued + ttl,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(f"{TOKEN_VERSION}.{body}")
    return f"{TOKEN_VERSION}.{body}.{signature}"


def _sign(message: str) -> str:
    digest = hmac.new(settings.secret_key(), message.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def read_session_token(token: str, now: Optional[float] = None) -> Optional[dict]:
    try:
        version, body, signature = token.split(".")
        if version != TOKEN_VERSION:
            return None
        expected = _sign(f"{version}.{body}")
        if not hmac.compare_digest(signature.encode("ascii"), expected.encode("ascii")):
            return None
        payload = json.loads(_b64decode(body))
        user_id = int(payload["uid"])
        token_version = int(payload["ver"])
        expires = int(payload["exp"])
        issued = int(payload["iat"])
        sid = str(payload["sid"])
    except (ValueError, KeyError, TypeError, UnicodeError):
        return None
    if not sid or len(sid) > 128:
        return None
    current = time.time() if now is None else now
    if current >= expires:
        return None
    return {"uid": user_id, "ver": token_version, "sid": sid, "exp": expires, "iat": issued}


def client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    hops = settings.trusted_proxy_hops()
    if hops <= 0:
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(parts) < hops:
        return direct
    candidate = parts[-hops]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return direct


def is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if settings.trusted_proxy_hops() > 0:
        return request.headers.get("x-forwarded-proto", "").split(",")[-1].strip() == "https"
    return False


class RateLimiter:
    def __init__(self, max_keys: int = 50000) -> None:
        self._events: dict[str, tuple[float, deque]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def _prune(self, now: float) -> None:
        if len(self._events) <= self._max_keys:
            return
        for key in list(self._events):
            window, events = self._events[key]
            while events and now - events[0] >= window:
                events.popleft()
            if not events:
                del self._events[key]
        if len(self._events) > self._max_keys:
            for key in list(self._events)[: len(self._events) - self._max_keys]:
                del self._events[key]

    def _live(self, key: str, window: float, now: float) -> deque:
        entry = self._events.get(key)
        if entry is None:
            events: deque = deque()
            self._events[key] = (window, events)
            return events
        stored_window, events = entry
        if stored_window != window:
            self._events[key] = (window, events)
        while events and now - events[0] >= window:
            events.popleft()
        return events

    def retry_after(
        self, key: str, limit: int, window: float, now: Optional[float] = None
    ) -> int:
        current = time.monotonic() if now is None else now
        with self._lock:
            events = self._live(key, window, current)
            if len(events) < limit:
                return 0
            oldest = events[-limit]
            return max(1, int(window - (current - oldest) + 0.999))

    def record(self, key: str, window: float, now: Optional[float] = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            self._prune(current)
            self._live(key, window, current).append(current)

    def consume(
        self, key: str, limit: int, window: float, now: Optional[float] = None
    ) -> int:
        current = time.monotonic() if now is None else now
        with self._lock:
            self._prune(current)
            events = self._live(key, window, current)
            if len(events) >= limit:
                oldest = events[-limit]
                return max(1, int(window - (current - oldest) + 0.999))
            events.append(current)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


limiter = RateLimiter()
