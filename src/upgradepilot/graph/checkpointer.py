"""
Checkpointer factory.

In tests: MemorySaver (no external deps).
In production: AsyncPostgresSaver (requires DATABASE_URL).

Import gracefully; a missing libpq does not crash the module at import time.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any

from langgraph.checkpoint.memory import MemorySaver


def get_memory_checkpointer() -> MemorySaver:
    return MemorySaver()


def psycopg_connection_string(connection_string: str) -> str:
    """Normalize SQLAlchemy-style PostgreSQL URLs for psycopg."""
    if connection_string.startswith("postgresql+psycopg://"):
        return "postgresql://" + connection_string.removeprefix("postgresql+psycopg://")
    return connection_string


def get_postgres_checkpointer(connection_string: str) -> AbstractAsyncContextManager[Any]:
    """Return an AsyncPostgresSaver context manager; raises ImportError if unavailable."""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        return AsyncPostgresSaver.from_conn_string(psycopg_connection_string(connection_string))
    except ImportError as exc:
        raise ImportError(
            "langgraph-checkpoint-postgres and psycopg are required for production "
            "checkpointing. Install with: uv add langgraph-checkpoint-postgres psycopg"
        ) from exc


def get_checkpointer(*, postgres_url: str | None = None) -> object:
    """
    Return the appropriate checkpointer.

    Production callers should pass ``postgres_url`` and manage the returned async
    context manager. Tests and fixture-only runs can request the in-memory saver
    by omitting it.
    """
    if postgres_url:
        return get_postgres_checkpointer(postgres_url)
    return get_memory_checkpointer()
