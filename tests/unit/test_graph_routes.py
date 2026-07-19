"""
Unit tests for graph routing functions.

These tests are purely functional: they build minimal state dicts and assert
that the routing functions return the correct node name(s).
No LangGraph compilation or I/O required.
"""

from __future__ import annotations

from upgradepilot.graph.routing import (
    route_after_acquisition,
    route_after_pack_selection,
    route_after_profile,
    route_after_request,
    route_after_validation,
)
from upgradepilot.graph.state import (
    FIXTURE_SUPPORTED,
    AnalysisStatus,
    ApplicabilityStatus,
    ValidationOutcome,
    make_initial_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUEST = {
    "repository_url": "https://github.com/owner/repo",
    "ref": "main",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "fixture",
    "request_id": "test-req-001",
    "github_owner": "owner",
    "github_repo": "repo",
}


def _state(**overrides):
    s = make_initial_state("test-analysis-001", _REQUEST, FIXTURE_SUPPORTED)
    s.update(overrides)
    return s


# ---------------------------------------------------------------------------
# route_after_request
# ---------------------------------------------------------------------------


def test_route_after_request_running():
    s = _state(status=AnalysisStatus.RUNNING)
    assert route_after_request(s) == "acquire_repository"


def test_route_after_request_terminal():
    s = _state(status=AnalysisStatus.TERMINAL)
    assert route_after_request(s) == "assemble_terminal_report"


# ---------------------------------------------------------------------------
# route_after_acquisition
# ---------------------------------------------------------------------------


def test_route_after_acquisition_ok():
    s = _state(status=AnalysisStatus.RUNNING)
    assert route_after_acquisition(s) == "profile_repository"


def test_route_after_acquisition_terminal():
    s = _state(status=AnalysisStatus.TERMINAL)
    assert route_after_acquisition(s) == "assemble_terminal_report"


# ---------------------------------------------------------------------------
# route_after_profile
# ---------------------------------------------------------------------------


def test_route_after_profile_ok():
    s = _state(status=AnalysisStatus.RUNNING)
    assert route_after_profile(s) == "select_migration_pack"


def test_route_after_profile_terminal():
    s = _state(status=AnalysisStatus.TERMINAL)
    assert route_after_profile(s) == "assemble_terminal_report"


# ---------------------------------------------------------------------------
# route_after_pack_selection
# ---------------------------------------------------------------------------

_PARALLEL_BRANCHES = {
    "parse_dependencies",
    "scan_compatibility",
    "analyze_tests_and_ci",
}


def test_route_after_pack_supported():
    s = _state(
        status=AnalysisStatus.RUNNING,
        applicability_status=ApplicabilityStatus.SUPPORTED,
    )
    result = route_after_pack_selection(s)
    assert isinstance(result, list)
    assert set(result) == _PARALLEL_BRANCHES


def test_route_after_pack_probable():
    s = _state(
        status=AnalysisStatus.RUNNING,
        applicability_status=ApplicabilityStatus.PROBABLE_NEEDS_REVIEW,
    )
    result = route_after_pack_selection(s)
    assert isinstance(result, list)
    assert set(result) == _PARALLEL_BRANCHES


def test_route_after_pack_not_applicable():
    s = _state(
        status=AnalysisStatus.RUNNING,
        applicability_status=ApplicabilityStatus.NOT_APPLICABLE,
    )
    assert route_after_pack_selection(s) == "assemble_terminal_report"


def test_route_after_pack_unsupported():
    s = _state(
        status=AnalysisStatus.RUNNING,
        applicability_status=ApplicabilityStatus.UNSUPPORTED,
    )
    assert route_after_pack_selection(s) == "assemble_terminal_report"


def test_route_after_pack_error():
    s = _state(
        status=AnalysisStatus.RUNNING,
        applicability_status=ApplicabilityStatus.ERROR,
    )
    assert route_after_pack_selection(s) == "assemble_terminal_report"


def test_route_after_pack_terminal_status():
    s = _state(status=AnalysisStatus.TERMINAL, applicability_status=ApplicabilityStatus.SUPPORTED)
    assert route_after_pack_selection(s) == "assemble_terminal_report"


# ---------------------------------------------------------------------------
# route_after_validation
# ---------------------------------------------------------------------------


def test_route_validation_pass():
    s = _state(validation_outcome=ValidationOutcome.PASS, repair_count=0)
    assert route_after_validation(s) == "assemble_validated_report"


def test_route_validation_repairable_first_try():
    s = _state(validation_outcome=ValidationOutcome.REPAIRABLE, repair_count=0)
    assert route_after_validation(s) == "evidence_critic"


def test_route_validation_repairable_second_try():
    s = _state(validation_outcome=ValidationOutcome.REPAIRABLE, repair_count=1)
    assert route_after_validation(s) == "assemble_partial_report"


def test_route_validation_structural():
    s = _state(validation_outcome=ValidationOutcome.STRUCTURAL_FAILURE, repair_count=0)
    assert route_after_validation(s) == "assemble_partial_report"
