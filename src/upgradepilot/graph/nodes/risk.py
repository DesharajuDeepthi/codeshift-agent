"""calculate_risk node — deterministic risk scoring."""

from __future__ import annotations

from typing import Any

from upgradepilot.graph.nodes._helpers import (
    _now,
    graph_error,
    is_fixture,
    node_error_record,
    node_record,
)
from upgradepilot.graph.state import UpgradePilotState

_NODE = "calculate_risk"

_FIXTURE_RISK: dict[str, Any] = {
    "total_score": 42,
    "level": "medium",
    "components": [
        {
            "component_id": "rc-removed-api",
            "description": "Removed/changed API usage found",
            "points": 30,
            "supporting_finding_ids": ["00000000-0000-0000-0000-000000000001"],
        },
        {
            "component_id": "rc-no-test-coverage",
            "description": "No Pydantic-specific test coverage detected",
            "points": 12,
            "supporting_finding_ids": [],
        },
    ],
    "scoring_model_version": "1.0.0",
}


async def calculate_risk(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        return {
            "risk_assessment": _FIXTURE_RISK,
            "node_executions": [node_record(_NODE, started)],
        }

    try:
        from upgradepilot.migration.risk import score_risk
        from upgradepilot.models.finding import MigrationFinding

        findings = [MigrationFinding.model_validate(f) for f in (state.get("findings") or [])]
        test_ci = state.get("test_ci_summary") or {}
        pack_id = state.get("pack_id", "pydantic-v1-to-v2")

        assessment = score_risk(findings, test_ci, pack_id)
        return {
            "risk_assessment": assessment.model_dump(),
            "node_executions": [node_record(_NODE, started)],
        }
    except Exception as exc:
        return {
            "risk_assessment": None,
            "node_executions": [node_error_record(_NODE, started, "RISK_SCORE_ERROR")],
            "errors": [graph_error(_NODE, "RISK_SCORE_ERROR", str(exc))],
        }
