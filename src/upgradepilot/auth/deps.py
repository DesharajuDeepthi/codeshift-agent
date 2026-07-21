"""FastAPI dependencies for JWT authentication."""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException, status

from upgradepilot.auth.jwt import decode_access_token


def optional_user_id(authorization: str | None = Header(default=None)) -> uuid.UUID | None:
    """Extract user_id from Bearer token; returns None if absent or invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
        return uuid.UUID(payload["sub"])
    except Exception:
        return None


def require_user_id(authorization: str | None = Header(default=None)) -> uuid.UUID:
    """Extract user_id from Bearer token; raises 401 if absent or invalid."""
    user_id = optional_user_id(authorization)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
