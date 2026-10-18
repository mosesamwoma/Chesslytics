from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if parts:
        return parts[-1]
    return request.client.host if request.client else "unknown"


@router.get("/status")
def status() -> dict:
    return {"enabled": auth.auth_enabled()}


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    if not auth.auth_enabled():
        raise HTTPException(status_code=400, detail="authentication is not enabled")
    key = _client_key(request)
    wait = auth.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"too many failed attempts; try again in {wait} seconds",
            headers={"Retry-After": str(wait)},
        )
    if not auth.credentials_match(payload.username, payload.password):
        auth.register_failure(key)
        raise HTTPException(status_code=401, detail="incorrect username or password")
    auth.register_success(key)
    return {
        "token": auth.create_token(auth.auth_username()),
        "token_type": "bearer",
        "expires_in": auth.token_ttl_seconds(),
        "username": auth.auth_username(),
    }


@router.get("/me")
def me(subject: str | None = Depends(auth.require_auth)) -> dict:
    return {"username": subject, "enabled": auth.auth_enabled()}
