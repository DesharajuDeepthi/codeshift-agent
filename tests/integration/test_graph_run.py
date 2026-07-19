"""
Integration tests: run the full compiled graph end-to-end in FIXTURE mode.

All 11 scenarios are covered.  No external network, no database, no LLM.
"""

from __future__ import annotations

import asyncio
import uuid

from upgradepilot.graph.build import build_graph
from upgradepilot.graph.checkpointer import get_memory_checkpointer
from upgradepilot.graph.state import (
    FIXTURE_ACQUISITION_FAILURE,
    FIXTURE_NOT_APPLICABLE,
    FIXTURE_REPAIR_FAIL,
    FIXTURE_REPAIR_SUCCESS,
    FIXTURE_SUPPORTED,
    FIXTURE_UNSUPPORTED,
    FIXTURE_VALIDATION_STRUCTURAL,
    AnalysisStatus,
    ApplicabilityStatus,
    ReportStatus,
    ValidationOutcome,
    make_initial_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE_REQUEST = {
    "repository_url": "https://github.com/test-owner/test-repo",
    "ref": "main",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "fixture",
    "request_id": "int-test-req",
    "github_owner": "test-owner",
    "github_repo": "test-repo",
}


def _run(scenario: str) -> dict:
    """Run the graph for a given FIXTURE scenario; return the final state."""
    checkpointer = get_memory_checkpointer()
    compiled = build_graph(checkpointer=checkpointer)
    state = make_initial_state(
        analysis_id=str(uuid.uuid4()),
        request_data=_FIXTURE_REQUEST,
        fixture_scenario=scenario,
    )
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    return asyncio.run(compiled.ainvoke(state, config=config))


# ---------------------------------------------------------------------------
# Scenario 1 — happy path (SUPPORTED, validation PASS)
# ---------------------------------------------------------------------------


def test_scenario_supported_happy_path():
    result = _run(FIXTURE_SUPPORTED)
    assert result["status"] == AnalysisStatus.COMPLETED
    assert result["report_status"] == ReportStatus.VALIDATED
    assert result["final_report"] is not None
    assert result["final_report"]["status"] == "validated"
    assert result["applicability_status"] == ApplicabilityStatus.SUPPORTED
    assert result["validation_outcome"] == ValidationOutcome.PASS
    # Findings and dependencies were produced
    assert len(result["findings"]) >= 1
    assert len(result["dependencies"]) >= 1
    # No structural errors
    assert not any(e.get("error_code") == "TERMINAL" for e in result.get("errors") or [])


# ---------------------------------------------------------------------------
# Scenario 2 — NOT_APPLICABLE
# ---------------------------------------------------------------------------


def test_scenario_not_applicable():
    result = _run(FIXTURE_NOT_APPLICABLE)
    assert result["status"] == AnalysisStatus.TERMINAL
    assert result["report_status"] == ReportStatus.TERMINAL
    assert result["applicability_status"] == ApplicabilityStatus.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Scenario 3 — UNSUPPORTED
# ---------------------------------------------------------------------------


def test_scenario_unsupported():
    result = _run(FIXTURE_UNSUPPORTED)
    assert result["status"] == AnalysisStatus.TERMINAL
    assert result["report_status"] == ReportStatus.TERMINAL
    assert result["applicability_status"] == ApplicabilityStatus.UNSUPPORTED


# ---------------------------------------------------------------------------
# Scenario 4 — acquisition failure
# ---------------------------------------------------------------------------


def test_scenario_acquisition_failure():
    result = _run(FIXTURE_ACQUISITION_FAILURE)
    assert result["status"] == AnalysisStatus.TERMINAL
    assert result["report_status"] == ReportStatus.TERMINAL
    errors = result.get("errors") or []
    assert any(e.get("error_code") == "REPOSITORY_INACCESSIBLE" for e in errors)


# ---------------------------------------------------------------------------
# Scenario 5 — repair success (validator REPAIRABLE → repair → PASS)
# ---------------------------------------------------------------------------


def test_scenario_repair_success():
    result = _run(FIXTURE_REPAIR_SUCCESS)
    assert result["status"] == AnalysisStatus.COMPLETED
    assert result["report_status"] == ReportStatus.VALIDATED
    assert result["validation_outcome"] == ValidationOutcome.PASS
    # One repair was executed
    assert result["repair_count"] == 1


# ---------------------------------------------------------------------------
# Scenario 6 — repair fail (REPAIRABLE → repair → STRUCTURAL_FAILURE → partial)
# ---------------------------------------------------------------------------


def test_scenario_repair_fail():
    result = _run(FIXTURE_REPAIR_FAIL)
    assert result["status"] == AnalysisStatus.PARTIAL
    assert result["report_status"] == ReportStatus.PARTIAL
    # repair_count incremented once
    assert result["repair_count"] == 1


# ---------------------------------------------------------------------------
# Scenario 7 — structural failure (no repair attempted)
# ---------------------------------------------------------------------------


def test_scenario_validation_structural():
    result = _run(FIXTURE_VALIDATION_STRUCTURAL)
    assert result["status"] == AnalysisStatus.PARTIAL
    assert result["report_status"] == ReportStatus.PARTIAL
    assert result["validation_outcome"] == ValidationOutcome.STRUCTURAL_FAILURE
    # repair_count must stay 0 (no repair attempted for structural failure)
    assert result["repair_count"] == 0


# ---------------------------------------------------------------------------
# Scenario 8 — node_executions contain all expected nodes (happy path)
# ---------------------------------------------------------------------------


def test_all_nodes_recorded():
    result = _run(FIXTURE_SUPPORTED)
    executed = {r["node_name"] for r in result.get("node_executions") or []}
    expected = {
        "validate_request",
        "acquire_repository",
        "profile_repository",
        "select_migration_pack",
        "parse_dependencies",
        "scan_compatibility",
        "analyze_tests_and_ci",
        "documentation_research",
        "aggregate_analysis",
        "calculate_risk",
        "compatibility_interpretation",
        "migration_planning",
        "deterministic_evidence_validator",
        "assemble_validated_report",
    }
    assert expected.issubset(executed), f"Missing nodes: {expected - executed}"


# ---------------------------------------------------------------------------
# Scenario 9 — repair path node coverage
# ---------------------------------------------------------------------------


def test_repair_path_nodes_recorded():
    result = _run(FIXTURE_REPAIR_SUCCESS)
    executed = {r["node_name"] for r in result.get("node_executions") or []}
    assert "evidence_critic" in executed
    assert "repair_plan" in executed
    # Validator ran twice (once before repair, once after)
    validator_runs = [
        r
        for r in (result.get("node_executions") or [])
        if r["node_name"] == "deterministic_evidence_validator"
    ]
    assert len(validator_runs) == 2


# ---------------------------------------------------------------------------
# Scenario 10 — parallel branches all contribute findings
# ---------------------------------------------------------------------------


def test_parallel_branches_contribute():
    result = _run(FIXTURE_SUPPORTED)
    # scan_compatibility adds 1 finding; parse_dependencies adds 1 dep;
    # documentation_research adds 1 doc evidence; analyze_tests_and_ci sets summary
    assert len(result["findings"]) >= 1
    assert len(result["dependencies"]) >= 1
    assert len(result["documentation_evidence"]) >= 1
    assert result["test_ci_summary"] is not None


# ---------------------------------------------------------------------------
# Scenario 11 — final report fields
# ---------------------------------------------------------------------------


def test_final_report_has_required_fields():
    result = _run(FIXTURE_SUPPORTED)
    report = result["final_report"]
    required = {
        "analysis_id",
        "generated_at",
        "repository_url",
        "ref",
        "migration_pack",
        "status",
    }
    missing = required - set(report.keys())
    assert not missing, f"Missing report fields: {missing}"
