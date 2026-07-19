"""FastAPI dependency helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import redis.asyncio as aioredis

from upgradepilot.config import get_settings


async def get_readiness_checks() -> dict[str, Any]:
    """Run lightweight readiness probes; returns dict of {name: {ok, required, detail}}."""
    settings = get_settings()
    results: dict[str, Any] = {}

    # Migration pack loaded.
    results["migration_pack"] = {"ok": True, "required": True}

    # PostgreSQL is required for production-like checkpointing/readiness.
    try:
        await _postgres_reachable(settings.database_url.get_secret_value())
        results["postgres"] = {"ok": True, "required": True}
    except Exception as exc:
        results["postgres"] = {
            "ok": False,
            "required": True,
            "detail": f"PostgreSQL unavailable: {type(exc).__name__}",
        }

    # Redis probe (non-required: degraded-but-ready is allowed)
    try:
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        results["redis"] = {"ok": True, "required": False}
    except Exception as exc:
        results["redis"] = {
            "ok": False,
            "required": False,
            "detail": f"Redis unavailable: {type(exc).__name__}",
        }

    # LangSmith (non-required)
    results["langsmith"] = {
        "ok": settings.tracing_enabled,
        "required": False,
        "detail": None if settings.tracing_enabled else "LangSmith tracing disabled or no API key",
    }

    return results


async def _postgres_reachable(url: str) -> None:
    """Check that the configured PostgreSQL TCP endpoint is reachable."""
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2)
    writer.close()
    await writer.wait_closed()
    del reader
