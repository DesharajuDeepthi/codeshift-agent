"""Auth models for V2 GitHub OAuth flow."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class GitHubUser(BaseModel):
    github_id: int
    login: str
    email: str | None
    avatar_url: str | None


class User(BaseModel):
    user_id: uuid.UUID
    github_id: int
    login: str
    email: str | None
    avatar_url: str | None
    created_at: datetime
    is_active: bool = True


class TokenPayload(BaseModel):
    sub: str  # user_id as string
    exp: int
    iat: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
