"""Unit tests for GitHub OAuth router."""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set required env vars before importing the router
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-32b")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")

from fastapi import FastAPI

from upgradepilot.auth.jwt import create_access_token, decode_access_token
from upgradepilot.auth.router import _pending_states, router

app = FastAPI()
app.include_router(router)
client = TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


def test_login_redirects_to_github():
    resp = client.get("/auth/login")
    assert resp.status_code == 307
    assert "github.com/login/oauth/authorize" in resp.headers["location"]


def test_login_includes_state_param():
    resp = client.get("/auth/login")
    location = resp.headers["location"]
    assert "state=" in location


def test_login_requests_correct_scopes():
    resp = client.get("/auth/login")
    location = resp.headers["location"]
    assert "read%3Auser" in location or "read:user" in location


# ---------------------------------------------------------------------------
# /auth/callback
# ---------------------------------------------------------------------------


def _mock_httpx(github_token: str = "gh-token-abc", github_id: int = 42) -> MagicMock:
    """Return a mock httpx.Client context manager for both OAuth calls."""
    token_resp = MagicMock()
    token_resp.json.return_value = {"access_token": github_token}
    token_resp.raise_for_status = MagicMock()

    user_resp = MagicMock()
    user_resp.json.return_value = {
        "id": github_id,
        "login": "testuser",
        "email": "testuser@example.com",
        "avatar_url": "https://avatars.githubusercontent.com/u/42",
    }
    user_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = token_resp
    mock_client.get.return_value = user_resp
    return mock_client


def _add_state(state: str) -> None:
    _pending_states.add(state)


def test_callback_returns_jwt():
    state = "valid-state-xyz"
    _add_state(state)
    with patch("upgradepilot.auth.router.httpx.Client", return_value=_mock_httpx()):
        resp = client.get(f"/auth/callback?code=abc&state={state}")
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_callback_jwt_is_valid():
    state = "valid-state-jwt"
    _add_state(state)
    with patch("upgradepilot.auth.router.httpx.Client", return_value=_mock_httpx()):
        resp = client.get(f"/auth/callback?code=abc&state={state}")
    token = resp.json()["access_token"]
    payload = decode_access_token(token)
    assert "sub" in payload
    assert uuid.UUID(payload["sub"])  # must be a valid UUID


def test_callback_invalid_state_rejected():
    resp = client.get("/auth/callback?code=abc&state=not-a-real-state")
    assert resp.status_code == 400


def test_callback_state_consumed_after_use():
    """State token is one-time use — replay must be rejected."""
    state = "one-time-state"
    _add_state(state)
    with patch("upgradepilot.auth.router.httpx.Client", return_value=_mock_httpx()):
        resp1 = client.get(f"/auth/callback?code=abc&state={state}")
    assert resp1.status_code == 200
    resp2 = client.get(f"/auth/callback?code=abc&state={state}")
    assert resp2.status_code == 400


def test_callback_github_token_not_in_response():
    """GitHub token must not leak into our JWT response."""
    state = "leak-check-state"
    _add_state(state)
    mock = _mock_httpx(github_token="secret-gh-token")
    with patch("upgradepilot.auth.router.httpx.Client", return_value=mock):
        resp = client.get(f"/auth/callback?code=abc&state={state}")
    assert "secret-gh-token" not in resp.text


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def test_jwt_missing_secret_raises():
    with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}):
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            create_access_token(uuid.uuid4())
