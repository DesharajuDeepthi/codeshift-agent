"""
Previous-run findings retrieval for delta detection.

Queries the analyses table for the most recent completed run on a
given thread_id, returning its findings list for use in compute_delta.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

_QUERY = sa.text(
    """
    SELECT report
    FROM   analyses
    WHERE  thread_id = :thread_id
      AND  status    = 'completed'
      AND  report    IS NOT NULL
    ORDER  BY created_at DESC
    LIMIT  1
    """
)


def get_previous_findings(
    thread_id: str,
    conn: Connection,
) -> list[dict[str, Any]]:
    """
    Return the findings list from the most recent completed run for
    this thread_id, or an empty list if no prior run exists.

    `report` is stored as JSONB with shape {"findings": [...], ...}.
    """
    row = conn.execute(_QUERY, {"thread_id": thread_id}).fetchone()
    if row is None:
        return []
    report: dict[str, Any] = row[0] if isinstance(row[0], dict) else {}
    return report.get("findings") or []
