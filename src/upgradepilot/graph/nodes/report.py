"""
Report assembly nodes:
  - assemble_validated_report
  - assemble_partial_report
  - assemble_terminal_report
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from upgradepilot.graph.nodes._helpers import _now, node_record
from upgradepilot.graph.state import AnalysisStatus, ReportStatus, UpgradePilotState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_report(state: UpgradePilotState) -> dict[str, Any]:
    req = state.get("request_data") or {}
    pack_version = ""
    pack_id = req.get("migration_pack", "") or state.get("pack_id", "")
    if pack_id:
        try:
            from upgradepilot.migration.loader import load_all_packs

            pack_version = load_all_packs().get(str(pack_id)).metadata.version
        except Exception:
            pack_version = ""
    return {
        "analysis_id": state.get("analysis_id", ""),
        "generated_at": datetime.now(UTC).isoformat(),
        "repository_url": req.get("repository_url", ""),
        "ref": req.get("ref", "main"),
        "migration_pack": pack_id,
        "migration_pack_version": pack_version,
        "commit_sha": (state.get("snapshot") or {}).get("resolved_commit_sha", ""),
        "observability": {
            "trace_id": state.get("trace_id"),
            "langsmith_root_run_id": state.get("langsmith_root_run_id"),
            "langsmith_submitted": False,
            "status": state.get("observability_status", "disabled"),
            "degraded_reason": state.get("observability_degraded_reason"),
            "trace_url": None,
        },
    }


# ---------------------------------------------------------------------------
# assemble_validated_report
# ---------------------------------------------------------------------------

_NODE_VALIDATED = "assemble_validated_report"


async def assemble_validated_report(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    report = {
        **_base_report(state),
        "status": "validated",
        "profile": state.get("profile"),
        "applicability_status": state.get("applicability_status", ""),
        "findings": state.get("findings") or [],
        "dependencies": state.get("dependencies") or [],
        "documentation_evidence": state.get("documentation_evidence") or [],
        "test_ci_summary": state.get("test_ci_summary"),
        "risk_assessment": state.get("risk_assessment"),
        "interpretation": state.get("interpretation"),
        "plan_draft": state.get("plan_draft"),
        "validation_outcome": state.get("validation_outcome", ""),
        "validation_issues": state.get("validation_issues") or [],
        "warnings": state.get("warnings") or [],
        "limitations": [],
        "node_executions": state.get("node_executions") or [],
    }
    return {
        "final_report": report,
        "report_status": ReportStatus.VALIDATED,
        "status": AnalysisStatus.COMPLETED,
        "node_executions": [node_record(_NODE_VALIDATED, started)],
    }


# ---------------------------------------------------------------------------
# assemble_partial_report
# ---------------------------------------------------------------------------

_NODE_PARTIAL = "assemble_partial_report"


async def assemble_partial_report(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    errors = state.get("errors") or []
    validation_issues = state.get("validation_issues") or []

    limitations = [e.get("message", "") for e in errors if e.get("message")]
    if validation_issues:
        limitations.append(
            f"Evidence validation failed with {len(validation_issues)} issue(s); "
            "plan may be incomplete."
        )

    report = {
        **_base_report(state),
        "status": "partial",
        "profile": state.get("profile"),
        "applicability_status": state.get("applicability_status", ""),
        "findings": state.get("findings") or [],
        "dependencies": state.get("dependencies") or [],
        "risk_assessment": state.get("risk_assessment"),
        "interpretation": state.get("interpretation"),
        "plan_draft": state.get("plan_draft"),
        "validation_outcome": state.get("validation_outcome", ""),
        "validation_issues": validation_issues,
        "warnings": state.get("warnings") or [],
        "limitations": limitations,
        "errors": errors,
        "node_executions": state.get("node_executions") or [],
    }
    return {
        "final_report": report,
        "report_status": ReportStatus.PARTIAL,
        "status": AnalysisStatus.PARTIAL,
        "node_executions": [node_record(_NODE_PARTIAL, started)],
    }


# ---------------------------------------------------------------------------
# assemble_terminal_report
# ---------------------------------------------------------------------------

_NODE_TERMINAL = "assemble_terminal_report"


async def assemble_terminal_report(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    errors = state.get("errors") or []
    reason = errors[0].get("message", "Unknown error") if errors else "Unknown error"

    report = {
        **_base_report(state),
        "status": "terminal",
        "profile": state.get("profile"),
        "applicability_status": state.get("applicability_status", ""),
        "reason": reason,
        "errors": errors,
        "warnings": state.get("warnings") or [],
        "node_executions": state.get("node_executions") or [],
    }
    return {
        "final_report": report,
        "report_status": ReportStatus.TERMINAL,
        "status": AnalysisStatus.TERMINAL,
        "node_executions": [node_record(_NODE_TERMINAL, started)],
    }
