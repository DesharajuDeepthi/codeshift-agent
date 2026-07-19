"""
validate_request node.

Validates the incoming AnalysisRequest and transitions status to RUNNING.
Routes to terminal_report on validation error.
"""

from __future__ import annotations

from typing import Any

from upgradepilot.graph.nodes._helpers import (
    _now,
    graph_error,
    is_fixture,
    node_error_record,
    node_record,
)
from upgradepilot.graph.state import AnalysisStatus, UpgradePilotState
from upgradepilot.models.request import AnalysisRequest

_NODE = "validate_request"


def validate_request(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        return {
            "status": AnalysisStatus.RUNNING,
            "node_executions": [node_record(_NODE, started)],
        }

    try:
        # Reconstruct the Pydantic model to re-validate
        req = AnalysisRequest.model_validate(state["request_data"])
    except Exception as exc:
        return {
            "status": AnalysisStatus.TERMINAL,
            "node_executions": [node_error_record(_NODE, started, "REQUEST_INVALID")],
            "errors": [graph_error(_NODE, "REQUEST_INVALID", str(exc))],
        }

    return {
        "status": AnalysisStatus.RUNNING,
        "request_data": req.model_dump(),
        "node_executions": [node_record(_NODE, started)],
    }
