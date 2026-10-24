from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app import settings
from app.database.models import User, utcnow

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GROUPS = 4
GROUP_LENGTH = 4
CODE_LENGTH = GROUPS * GROUP_LENGTH


def generate() -> str:
    groups = [
        "".join(secrets.choice(ALPHABET) for _ in range(GROUP_LENGTH)) for _ in range(GROUPS)
    ]
    return "-".join(groups)


def normalize(raw: str) -> Optional[str]:
    cleaned = "".join(ch for ch in (raw or "").upper() if ch not in " -_\t\r\n")
    if len(cleaned) != CODE_LENGTH or any(ch not in ALPHABET for ch in cleaned):
        return None
    return cleaned


def digest(normalized: str) -> str:
    key = settings.secret_key()
    return hmac.new(key, b"recovery:" + normalized.encode("ascii"), hashlib.sha256).hexdigest()


def issue(session: Session, user: User) -> str:
    code = generate()
    normalized = normalize(code)
    assert normalized is not None
    user.recovery_hash = digest(normalized)
    user.recovery_created_at = utcnow()
    session.flush()
    return code


def matches(user: Optional[User], raw: str) -> bool:
    normalized = normalize(raw)
    expected = user.recovery_hash if user is not None and user.recovery_hash else None
    candidate = digest(normalized) if normalized is not None else digest("-")
    reference = expected or digest("*")
    same = hmac.compare_digest(candidate, reference)
    return bool(same and expected and normalized is not None)
