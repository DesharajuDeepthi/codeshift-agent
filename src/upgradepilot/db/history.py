"""
User analysis history — thin psycopg layer (no ORM).

Table is created on first use via ensure_table(); no migration tooling required
for this single-table append-only store.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS user_analyses (
    id            SERIAL PRIMARY KEY,
    user_id       UUID        NOT NULL,
    analysis_id   TEXT        NOT NULL UNIQUE,
    repository_url TEXT       NOT NULL,
    ref           TEXT        NOT NULL DEFAULT 'main',
    status        TEXT        NOT NULL DEFAULT 'running',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_analyses_user_id ON user_analyses (user_id, created_at DESC);
"""


def _conn_string() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def ensure_table() -> None:
    """Create the user_analyses table if it doesn't exist. Called at API startup."""
    import psycopg

    cs = _conn_string()
    if not cs:
        return
    with psycopg.connect(cs) as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()


def record_analysis(
    *,
    user_id: uuid.UUID,
    analysis_id: str,
    repository_url: str,
    ref: str,
) -> None:
    """Insert a new analysis row for this user."""
    import psycopg

    cs = _conn_string()
    if not cs:
        return
    with psycopg.connect(cs) as conn:
        conn.execute(
            """
            INSERT INTO user_analyses (user_id, analysis_id, repository_url, ref)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (analysis_id) DO NOTHING
            """,
            (user_id, analysis_id, repository_url, ref),
        )
        conn.commit()


def finish_analysis(*, analysis_id: str, status: str) -> None:
    """Update status and finished_at when analysis completes."""
    import psycopg

    cs = _conn_string()
    if not cs:
        return
    with psycopg.connect(cs) as conn:
        conn.execute(
            """
            UPDATE user_analyses
            SET status = %s, finished_at = %s
            WHERE analysis_id = %s
            """,
            (status, datetime.now(UTC), analysis_id),
        )
        conn.commit()


def list_analyses(*, user_id: uuid.UUID, limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent analyses for a user, newest first."""
    import psycopg

    cs = _conn_string()
    if not cs:
        return []
    with psycopg.connect(cs) as conn:
        rows = conn.execute(
            """
            SELECT analysis_id, repository_url, ref, status, created_at, finished_at
            FROM user_analyses
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
    return [
        {
            "analysis_id": r[0],
            "repository_url": r[1],
            "ref": r[2],
            "status": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "finished_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]
