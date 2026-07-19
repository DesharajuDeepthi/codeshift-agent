"""JWT creation and verification."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import jwt

_ALGORITHM = "HS256"
_EXPIRES_SECONDS = 60 * 60 * 8  # 8 hours


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY env var must be set")
    return secret


def create_access_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + _EXPIRES_SECONDS,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
