"""User models for V2 multi-tenant support."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class User(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    created_at: datetime
    is_active: bool = True


class TokenPayload(BaseModel):
    sub: str  # user_id
    exp: int
    iat: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
