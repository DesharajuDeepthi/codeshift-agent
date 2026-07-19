"""
deterministic_evidence_validator node.

Validates the plan_draft against evidence in state:
  - All file references exist in the profile.
  - All rule IDs exist in the loaded pack.
  - All finding_ids referenced in claims exist.
  - No prohibited claims (LLM cannot assert version certainty without evidence).

Returns validation_outcome and appends validation_issues.
"""

from __future__ import annotations

from typing import Any

from upgradepilot.graph.nodes._helpers import (
    _now,
    is_fixture,
    node_record,
)
from upgradepilot.graph.state import (
    FIXTURE_REPAIR_FAIL,
    FIXTURE_REPAIR_SUCCESS,
    FIXTURE_VALIDATION_STRUCTURAL,
    UpgradePilotState,
    ValidationOutcome,
)
from upgradepilot.validators.evidence import ValidationContext, validate_plan_evidence

_NODE = "deterministic_evidence_validator"

# ---------------------------------------------------------------------------
# Fixture validation issues
# ---------------------------------------------------------------------------

_REPAIRABLE_ISSUE: dict[str, Any] = {
    "validator_id": "V-FILE-REF",
    "severity": "warning",
    "message": "FIXTURE: One plan claim references a file not in the profile.",
    "claim_id": "claim-fixture-001",
    "evidence_id": None,
    "repairable": True,
}

_STRUCTURAL_ISSUE: dict[str, Any] = {
    "validator_id": "V-EVIDENCE",
    "severity": "error",
    "message": "FIXTURE: Plan claim cites a finding_id that does not exist.",
    "claim_id": "claim-fixture-002",
    "evidence_id": None,
    "repairable": False,
}


def _make_issue(
    validator_id: str,
    severity: str,
    message: str,
    repairable: bool,
    claim_id: str | None = None,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    return {
        "validator_id": validator_id,
        "severity": severity,
        "message": message,
        "claim_id": claim_id,
        "evidence_id": evidence_id,
        "repairable": repairable,
    }


async def deterministic_evidence_validator(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        scenario = state.get("fixture_scenario", "")
        if scenario == FIXTURE_VALIDATION_STRUCTURAL:
            return {
                "validation_outcome": ValidationOutcome.STRUCTURAL_FAILURE,
                "validation_issues": [_STRUCTURAL_ISSUE],
                "node_executions": [node_record(_NODE, started)],
            }
        if scenario == FIXTURE_REPAIR_SUCCESS:
            # First pass repairable; after repair the second pass should PASS.
            # We detect second pass by repair_count > 0.
            if state.get("repair_count", 0) > 0:
                return {
                    "validation_outcome": ValidationOutcome.PASS,
                    "validation_issues": [],
                    "node_executions": [node_record(_NODE, started)],
                }
            return {
                "validation_outcome": ValidationOutcome.REPAIRABLE,
                "validation_issues": [_REPAIRABLE_ISSUE],
                "node_executions": [node_record(_NODE, started)],
            }
        if scenario == FIXTURE_REPAIR_FAIL:
            # Always repairable on first pass, fails on second.
            if state.get("repair_count", 0) > 0:
                return {
                    "validation_outcome": ValidationOutcome.STRUCTURAL_FAILURE,
                    "validation_issues": [_STRUCTURAL_ISSUE],
                    "node_executions": [node_record(_NODE, started)],
                }
            return {
                "validation_outcome": ValidationOutcome.REPAIRABLE,
                "validation_issues": [_REPAIRABLE_ISSUE],
                "node_executions": [node_record(_NODE, started)],
            }
        # Default fixture: PASS
        return {
            "validation_outcome": ValidationOutcome.PASS,
            "validation_issues": [],
            "node_executions": [node_record(_NODE, started)],
        }

    context = ValidationContext(
        plan_draft=state.get("plan_draft") or {},
        profile=state.get("profile") or {},
        findings=state.get("findings") or [],
        documentation_evidence=state.get("documentation_evidence") or [],
        dependencies=state.get("dependencies") or [],
        risk_assessment=state.get("risk_assessment") or {},
        pack_id=str(state.get("pack_id") or state.get("request_data", {}).get("migration_pack")),
    )
    issues = validate_plan_evidence(context)

    # Determine outcome
    has_structural = any(not i["repairable"] for i in issues)
    has_repairable = any(i["repairable"] for i in issues)

    if has_structural:
        outcome = ValidationOutcome.STRUCTURAL_FAILURE
    elif has_repairable:
        outcome = ValidationOutcome.REPAIRABLE
    else:
        outcome = ValidationOutcome.PASS

    return {
        "validation_outcome": outcome,
        "validation_issues": issues,
        "node_executions": [node_record(_NODE, started)],
    }
