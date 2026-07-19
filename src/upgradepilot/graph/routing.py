"""
Routing functions for the UpgradePilot graph.

Routing functions are pure functions: they read state and return a node name
(or list of node names for fan-out).  They must never modify state.
"""

from __future__ import annotations

from upgradepilot.graph.state import (
    AnalysisStatus,
    ApplicabilityStatus,
    UpgradePilotState,
    ValidationOutcome,
)


def route_after_request(state: UpgradePilotState) -> str:
    """After validate_request: if TERMINAL, go to terminal report; else continue."""
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"
    return "acquire_repository"


def route_after_acquisition(state: UpgradePilotState) -> str:
    """After acquire_repository: terminal on failure, else profile."""
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"
    return "profile_repository"


def route_after_profile(state: UpgradePilotState) -> str:
    """After profile_repository: terminal on failure, else select pack."""
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"
    return "select_migration_pack"


def route_after_pack_selection(state: UpgradePilotState) -> str | list[str]:
    """
    After select_migration_pack:
    - NOT_APPLICABLE → terminal (not an error, but no migration possible)
    - UNSUPPORTED    → terminal
    - ERROR          → terminal
    - SUPPORTED / PROBABLE_NEEDS_REVIEW → parallel fan-out
    """
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"

    applicability = state.get("applicability_status", "")
    non_migratable = {
        ApplicabilityStatus.NOT_APPLICABLE,
        ApplicabilityStatus.UNSUPPORTED,
        ApplicabilityStatus.ERROR,
    }
    if applicability in non_migratable:
        return "assemble_terminal_report"

    # Fan-out to parallel branches
    return [
        "parse_dependencies",
        "scan_compatibility",
        "analyze_tests_and_ci",
    ]


def route_after_risk(state: UpgradePilotState) -> str:
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"
    return "compatibility_interpretation"


def route_after_interpretation(state: UpgradePilotState) -> str:
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"
    return "migration_planning"


def route_after_planning(state: UpgradePilotState) -> str:
    if state.get("status") == AnalysisStatus.TERMINAL:
        return "assemble_terminal_report"
    return "deterministic_evidence_validator"


def route_after_validation(state: UpgradePilotState) -> str:
    """
    After deterministic_evidence_validator:
    - PASS                → assemble_validated_report
    - REPAIRABLE + first try → evidence_critic → repair_plan → back to validator
    - REPAIRABLE + already repaired (repair_count > 0) → partial
    - STRUCTURAL_FAILURE  → partial
    """
    outcome = state.get("validation_outcome", "")
    repair_count = state.get("repair_count", 0)

    if outcome == ValidationOutcome.PASS:
        return "assemble_validated_report"

    if outcome == ValidationOutcome.REPAIRABLE and repair_count == 0:
        return "evidence_critic"

    # STRUCTURAL_FAILURE or second validation failure
    return "assemble_partial_report"


def route_after_critic(state: UpgradePilotState) -> str:
    return "repair_plan"


def route_after_repair(state: UpgradePilotState) -> str:
    return "deterministic_evidence_validator"
