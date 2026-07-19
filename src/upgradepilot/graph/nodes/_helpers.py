"""
Shared helpers for graph nodes.

Nodes are thin: they record execution, call a service (or FIXTURE stub),
and return a partial state update.  Never put domain logic here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from upgradepilot.graph.state import (
    GraphError,
    NodeExecutionRecord,
    NodeStatus,
    UpgradePilotState,
)


def _now() -> datetime:
    return datetime.now(UTC)


def is_fixture(state: UpgradePilotState) -> bool:
    req = state.get("request_data") or {}
    return str(req.get("analysis_mode", "")).lower() == "fixture"


def node_record(node_name: str, started_at: datetime) -> dict[str, Any]:
    """Return a NodeExecutionRecord dict for a successfully completed node."""
    completed = _now()
    ms = (completed - started_at).total_seconds() * 1000
    return NodeExecutionRecord(
        node_name=node_name,
        status=NodeStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed,
        latency_ms=ms,
    ).model_dump()


def node_error_record(node_name: str, started_at: datetime, error_code: str) -> dict[str, Any]:
    """Return a failed NodeExecutionRecord dict."""
    completed = _now()
    ms = (completed - started_at).total_seconds() * 1000
    return NodeExecutionRecord(
        node_name=node_name,
        status=NodeStatus.FAILED,
        started_at=started_at,
        completed_at=completed,
        latency_ms=ms,
        error_code=error_code,
    ).model_dump()


def graph_error(node_name: str, code: str, message: str) -> dict[str, Any]:
    return GraphError(node_name=node_name, error_code=code, message=message).model_dump()
