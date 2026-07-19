"""
Build and compile the UpgradePilot StateGraph.

Call `build_graph()` to get a compiled graph ready to invoke.
The module-level `graph` is the default compiled instance (no checkpointer),
used by the LangGraph server (langgraph.json).
"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, StateGraph

from upgradepilot.graph.nodes.acquisition import acquire_repository
from upgradepilot.graph.nodes.agents import (
    compatibility_interpretation,
    evidence_critic,
    migration_planning,
    repair_plan,
)
from upgradepilot.graph.nodes.analysis import (
    aggregate_analysis,
    analyze_tests_and_ci,
    documentation_research,
    parse_dependencies,
    scan_compatibility,
)
from upgradepilot.graph.nodes.evidence import deterministic_evidence_validator
from upgradepilot.graph.nodes.profiling import profile_repository, select_migration_pack
from upgradepilot.graph.nodes.report import (
    assemble_partial_report,
    assemble_terminal_report,
    assemble_validated_report,
)
from upgradepilot.graph.nodes.risk import calculate_risk
from upgradepilot.graph.nodes.validation import validate_request
from upgradepilot.graph.routing import (
    route_after_acquisition,
    route_after_critic,
    route_after_interpretation,
    route_after_pack_selection,
    route_after_planning,
    route_after_profile,
    route_after_repair,
    route_after_request,
    route_after_risk,
    route_after_validation,
)
from upgradepilot.graph.state import AnalysisStatus, UpgradePilotState
from upgradepilot.observability.tracing import instrument_graph_node


def _add_observed_node(
    graph_builder: StateGraph[UpgradePilotState],
    name: str,
    action: object,
) -> None:
    """Register a node wrapped with observability instrumentation."""
    graph_builder.add_node(name, cast(Any, instrument_graph_node(name, cast(Any, action))))


def build_graph(checkpointer: object = None) -> object:  # noqa: ANN201
    """
    Assemble and compile the UpgradePilot StateGraph.

    Parameters
    ----------
    checkpointer:
        Optional LangGraph checkpointer (MemorySaver, AsyncPostgresSaver …).
        Pass None for stateless execution (no persistence).

    Returns
    -------
    CompiledStateGraph
    """
    g: StateGraph[UpgradePilotState] = StateGraph(UpgradePilotState)

    # ── Nodes ──────────────────────────────────────────────────────────────
    _add_observed_node(g, "validate_request", validate_request)
    _add_observed_node(g, "acquire_repository", acquire_repository)
    _add_observed_node(g, "profile_repository", profile_repository)
    _add_observed_node(g, "select_migration_pack", select_migration_pack)

    # Parallel analysis branches
    _add_observed_node(g, "parse_dependencies", parse_dependencies)
    _add_observed_node(g, "scan_compatibility", scan_compatibility)
    _add_observed_node(g, "analyze_tests_and_ci", analyze_tests_and_ci)
    _add_observed_node(g, "documentation_research", documentation_research)

    _add_observed_node(g, "aggregate_analysis", aggregate_analysis)
    _add_observed_node(g, "calculate_risk", calculate_risk)

    # Agent placeholders
    _add_observed_node(g, "compatibility_interpretation", compatibility_interpretation)
    _add_observed_node(g, "migration_planning", migration_planning)
    _add_observed_node(g, "deterministic_evidence_validator", deterministic_evidence_validator)
    _add_observed_node(g, "evidence_critic", evidence_critic)
    _add_observed_node(g, "repair_plan", repair_plan)

    # Report nodes
    _add_observed_node(g, "assemble_validated_report", assemble_validated_report)
    _add_observed_node(g, "assemble_partial_report", assemble_partial_report)
    _add_observed_node(g, "assemble_terminal_report", assemble_terminal_report)

    # ── Entry point ────────────────────────────────────────────────────────
    g.set_entry_point("validate_request")

    # ── Conditional edges ──────────────────────────────────────────────────
    g.add_conditional_edges("validate_request", route_after_request)
    g.add_conditional_edges("acquire_repository", route_after_acquisition)
    g.add_conditional_edges("profile_repository", route_after_profile)

    # Fan-out: select_migration_pack → parallel deterministic branches.
    # documentation_research depends on merged scanner findings, so it runs once
    # after the fan-in aggregate step.
    g.add_conditional_edges(
        "select_migration_pack",
        route_after_pack_selection,
        {
            "parse_dependencies": "parse_dependencies",
            "scan_compatibility": "scan_compatibility",
            "analyze_tests_and_ci": "analyze_tests_and_ci",
            "assemble_terminal_report": "assemble_terminal_report",
        },
    )

    # Parallel branches converge to aggregate_analysis
    g.add_edge("parse_dependencies", "aggregate_analysis")
    g.add_edge("scan_compatibility", "aggregate_analysis")
    g.add_edge("analyze_tests_and_ci", "aggregate_analysis")

    g.add_conditional_edges(
        "aggregate_analysis",
        lambda s: (
            "assemble_terminal_report"
            if s.get("status") == AnalysisStatus.TERMINAL
            else "documentation_research"
        ),
    )
    g.add_edge("documentation_research", "calculate_risk")
    g.add_conditional_edges("calculate_risk", route_after_risk)
    g.add_conditional_edges("compatibility_interpretation", route_after_interpretation)
    g.add_conditional_edges("migration_planning", route_after_planning)
    g.add_conditional_edges(
        "deterministic_evidence_validator",
        route_after_validation,
        {
            "assemble_validated_report": "assemble_validated_report",
            "assemble_partial_report": "assemble_partial_report",
            "evidence_critic": "evidence_critic",
        },
    )
    g.add_conditional_edges("evidence_critic", route_after_critic)
    g.add_conditional_edges("repair_plan", route_after_repair)

    # Report nodes → END
    g.add_edge("assemble_validated_report", END)
    g.add_edge("assemble_partial_report", END)
    g.add_edge("assemble_terminal_report", END)

    # ── Compile ────────────────────────────────────────────────────────────
    if checkpointer is not None:
        return g.compile(checkpointer=checkpointer)  # type: ignore[arg-type]
    return g.compile()


# Default compiled graph for langgraph.json / server use
graph = build_graph()
