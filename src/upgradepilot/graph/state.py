"""
UpgradePilotState — the typed graph state and all supporting types.

Design rules:
- State uses TypedDict so LangGraph can serialize to/from checkpoints.
- Pydantic models are stored as dicts (model_dump()) for msgpack compatibility.
- Lists that are written by parallel branches use Annotated[list, operator.add].
- Single-writer fields use last-write-wins (no special reducer).
- Full file content is never stored here.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    TERMINAL = "terminal"
    FAILED = "failed"


class ApplicabilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PROBABLE_NEEDS_REVIEW = "PROBABLE_NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationOutcome(StrEnum):
    PASS = "pass"  # noqa: S105
    REPAIRABLE = "repairable"
    STRUCTURAL_FAILURE = "structural_failure"
    NOT_RUN = "not_run"


class ReportStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    PARTIAL = "partial"
    TERMINAL = "terminal"
    NONE = "none"


# ---------------------------------------------------------------------------
# Node execution record  (stored as dict in state)
# ---------------------------------------------------------------------------


class NodeExecutionRecord(BaseModel):
    """Written by every node to record its execution."""

    model_config = {"frozen": True}

    node_name: str
    status: NodeStatus
    started_at: datetime
    completed_at: datetime | None = None
    attempt: int = 1
    latency_ms: float | None = None
    error_code: str | None = None
    warning_codes: list[str] = Field(default_factory=list)
    langsmith_run_id: str | None = None


class GraphError(BaseModel):
    """Typed error recorded by any node."""

    model_config = {"frozen": True}

    node_name: str
    error_code: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# UpgradePilotState
# ---------------------------------------------------------------------------

# Fixture scenarios used in FIXTURE analysis_mode
FIXTURE_SUPPORTED = "supported"
FIXTURE_NOT_APPLICABLE = "not_applicable"
FIXTURE_UNSUPPORTED = "unsupported"
FIXTURE_ACQUISITION_FAILURE = "acquisition_failure"
FIXTURE_PROFILE_FAILURE = "profile_failure"
FIXTURE_REPAIR_SUCCESS = "repair_success"
FIXTURE_REPAIR_FAIL = "repair_fail"
FIXTURE_VALIDATION_STRUCTURAL = "validation_structural"
FIXTURE_AUTO_DETECT = "auto_detect"


class UpgradePilotState(TypedDict):
    # ── Identity ──────────────────────────────────────────────────────────
    analysis_id: str

    # ── Input request (dict form for checkpoint safety) ───────────────────
    request_data: dict[str, Any]  # AnalysisRequest.model_dump()

    # ── Test support ──────────────────────────────────────────────────────
    # fixture_scenario is read by nodes in FIXTURE mode to choose their output
    fixture_scenario: str

    # ── Execution status ──────────────────────────────────────────────────
    status: str  # AnalysisStatus value

    # ── Observability correlation ─────────────────────────────────────────
    trace_id: str | None
    langsmith_root_run_id: str | None
    observability_status: str
    observability_degraded_reason: str | None

    # ── Parallel-safe accumulators (all use append reducer) ───────────────
    node_executions: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]

    # ── Sequential stage outputs (last-write-wins) ────────────────────────
    snapshot: dict[str, Any] | None  # RepositorySnapshot.model_dump()
    profile: dict[str, Any] | None  # RepositoryProfile.model_dump()
    applicability_status: str  # ApplicabilityStatus value
    pack_id: str
    pack_candidates: list[dict[str, Any]]  # auto-detection results, ranked by confidence

    # ── Parallel analysis outputs ─────────────────────────────────────────
    dependencies: Annotated[list[dict[str, Any]], operator.add]
    findings: Annotated[list[dict[str, Any]], operator.add]
    test_ci_summary: dict[str, Any] | None
    documentation_evidence: Annotated[list[dict[str, Any]], operator.add]

    # ── Risk and agents ───────────────────────────────────────────────────
    risk_assessment: dict[str, Any] | None
    interpretation: dict[str, Any] | str | None
    plan_draft: dict[str, Any] | None

    # ── Validation ────────────────────────────────────────────────────────
    validation_outcome: str  # ValidationOutcome value
    validation_issues: list[dict[str, Any]]
    repair_count: int
    evidence_critic_result: dict[str, Any] | None
    repair_instructions: list[dict[str, Any]]

    # ── Final output ──────────────────────────────────────────────────────
    final_report: dict[str, Any] | None
    report_status: str  # ReportStatus value


def make_initial_state(
    analysis_id: str,
    request_data: dict[str, Any],
    fixture_scenario: str = FIXTURE_SUPPORTED,
) -> UpgradePilotState:
    """Create the zeroed initial state for a new analysis run."""
    return UpgradePilotState(
        analysis_id=analysis_id,
        request_data=request_data,
        fixture_scenario=fixture_scenario,
        status=AnalysisStatus.PENDING,
        trace_id=None,
        langsmith_root_run_id=None,
        observability_status="disabled",
        observability_degraded_reason=None,
        node_executions=[],
        errors=[],
        warnings=[],
        snapshot=None,
        profile=None,
        applicability_status=ApplicabilityStatus.SUPPORTED,
        pack_id="",
        pack_candidates=[],
        dependencies=[],
        findings=[],
        test_ci_summary=None,
        documentation_evidence=[],
        risk_assessment=None,
        interpretation=None,
        plan_draft=None,
        validation_outcome=ValidationOutcome.NOT_RUN,
        validation_issues=[],
        repair_count=0,
        evidence_critic_result=None,
        repair_instructions=[],
        final_report=None,
        report_status=ReportStatus.PENDING,
    )
