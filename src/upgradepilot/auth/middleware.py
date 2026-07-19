"""FastAPI dependency for JWT auth — injects current user into route handlers."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from upgradepilot.auth.jwt import decode_access_token
from upgradepilot.auth.models import TokenPayload

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),  # noqa: B008
) -> uuid.UUID:
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        return uuid.UUID(TokenPayload(**payload).sub)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
