"""Unit tests for health endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from upgradepilot.api.main import create_app


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


def test_liveness_returns_200(client: TestClient) -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_readiness_returns_200_when_degraded(client: TestClient) -> None:
    degraded_checks: dict[str, Any] = {
        "migration_pack": {"ok": True, "required": True},
        "postgres": {"ok": True, "required": True},
        "redis": {"ok": False, "required": False, "detail": "Redis unavailable"},
        "langsmith": {"ok": False, "required": False, "detail": "LangSmith disabled"},
    }
    with patch(
        "upgradepilot.api.health.get_readiness_checks",
        new=AsyncMock(return_value=degraded_checks),
    ):
        resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert "components" in body
    assert body["components"]["redis"]["status"] == "degraded"
    assert body["components"]["langsmith"]["status"] == "degraded"


def test_readiness_returns_503_when_required_component_down(client: TestClient) -> None:
    """When a required dependency is reported DOWN the endpoint must return 503."""
    down_checks: dict[str, Any] = {
        "migration_pack": {"ok": False, "required": True, "detail": "pack not loaded"},
        "postgres": {"ok": True, "required": True},
        "redis": {"ok": False, "required": False, "detail": "Redis unavailable"},
        "langsmith": {"ok": False, "required": False},
    }
    with patch(
        "upgradepilot.api.health.get_readiness_checks",
        new=AsyncMock(return_value=down_checks),
    ):
        resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "down"
    assert body["components"]["migration_pack"]["status"] == "down"


def test_readiness_returns_503_when_postgres_down(client: TestClient) -> None:
    down_checks: dict[str, Any] = {
        "migration_pack": {"ok": True, "required": True},
        "postgres": {"ok": False, "required": True, "detail": "PostgreSQL unavailable"},
        "redis": {"ok": True, "required": False},
        "langsmith": {"ok": True, "required": False},
    }
    with patch(
        "upgradepilot.api.health.get_readiness_checks",
        new=AsyncMock(return_value=down_checks),
    ):
        resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "down"
    assert body["components"]["postgres"]["status"] == "down"


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "upgradepilot_http_requests_total" in resp.text
