"""
GitHub OAuth router.

GET /auth/login    → redirect to GitHub with state param
GET /auth/callback → exchange code, upsert user, return JWT

The GitHub access token is used once to fetch the user profile and then
discarded — it is never stored.
"""

from __future__ import annotations

import os
import secrets
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from upgradepilot.auth.jwt import _EXPIRES_SECONDS, create_access_token
from upgradepilot.auth.models import GitHubUser, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105
_GITHUB_USER_URL = "https://api.github.com/user"

# In-process state store — short-lived CSRF tokens (one per login attempt).
# Replaced by Redis in Phase 4; sufficient for a single-process deployment.
_pending_states: set[str] = set()


def _client_id() -> str:
    val = os.environ.get("GITHUB_CLIENT_ID", "")
    if not val:
        raise RuntimeError("GITHUB_CLIENT_ID env var must be set")
    return val


def _client_secret() -> str:
    val = os.environ.get("GITHUB_CLIENT_SECRET", "")
    if not val:
        raise RuntimeError("GITHUB_CLIENT_SECRET env var must be set")
    return val


@router.get("/login")
def login() -> RedirectResponse:
    """Redirect the browser to GitHub's OAuth authorization page."""
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    params = {
        "client_id": _client_id(),
        "scope": "read:user user:email",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{_GITHUB_AUTHORIZE_URL}?{query}")


@router.get("/callback", response_model=TokenResponse)
def callback(
    code: str = Query(...),
    state: str = Query(...),
) -> TokenResponse:
    """
    Exchange GitHub OAuth code for an access token, fetch the user
    profile, upsert the user record, and return a signed JWT.
    """
    if state not in _pending_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter.",
        )
    _pending_states.discard(state)

    github_token = _exchange_code(code)
    gh_user = _fetch_github_user(github_token)
    # GitHub token intentionally not stored beyond this function scope.

    user_id = _upsert_user(gh_user)
    access_token = create_access_token(user_id)
    return TokenResponse(access_token=access_token, expires_in=_EXPIRES_SECONDS)


def _exchange_code(code: str) -> str:
    with httpx.Client(timeout=10) as client:
        resp = client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
    resp.raise_for_status()
    token: str = resp.json().get("access_token", "")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub did not return an access token.",
        )
    return token


def _fetch_github_user(token: str) -> GitHubUser:
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            _GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return GitHubUser(
        github_id=data["id"],
        login=data["login"],
        email=data.get("email"),
        avatar_url=data.get("avatar_url"),
    )


def _upsert_user(gh_user: GitHubUser) -> uuid.UUID:
    """
    Insert or update the user row and return the internal user_id.

    Uses an in-memory stub until Phase 4 wires the real DB connection.
    The stub is replaced by a single INSERT … ON CONFLICT DO UPDATE.
    """
    # TODO(phase-4): replace with real DB upsert via SQLAlchemy connection
    return uuid.uuid5(uuid.NAMESPACE_URL, f"github:{gh_user.github_id}")
