"""
Parallel analysis branch nodes:
  - parse_dependencies
  - scan_compatibility
  - analyze_tests_and_ci
  - documentation_research
  - aggregate_analysis
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from upgradepilot.graph.nodes._helpers import (
    _now,
    graph_error,
    is_fixture,
    node_error_record,
    node_record,
)
from upgradepilot.graph.state import UpgradePilotState

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_FIXTURE_DEP: dict[str, Any] = {
    "package": "pydantic",
    "normalized_name": "pydantic",
    "constraint": {"raw": ">=1.9,<2", "kind": "range", "lower": "1.9", "upper": "2"},
    "manifest_path": "pyproject.toml",
    "line": 12,
    "parser": "pyproject_toml",
    "parser_version": "1.0.0",
    "confidence": 1.0,
}

_FIXTURE_FINDING: dict[str, Any] = {
    "finding_id": "00000000-0000-0000-0000-000000000001",
    "rule_id": "PYD001",
    "pack_id": "pydantic-v1-to-v2",
    "pack_version": "1.0.0",
    "category": "serialization",
    "severity": "high",
    "file": "src/app/models.py",
    "line_start": 10,
    "line_end": 10,
    "evidence": "model.dict()",
    "symbol": ".dict()",
    "migration_concept": "Use .model_dump() instead of .dict()",
    "source_ids": ["PYDANTIC_MIGRATION_GUIDE"],
    "detector": "ast_scanner",
    "detector_version": "1.0.0",
    "confidence": 0.95,
    "match_kind": "ast",
}

_FIXTURE_TEST_CI: dict[str, Any] = {
    "test_files_count": 5,
    "frameworks": ["pytest"],
    "ci_systems": ["github_actions"],
    "has_pydantic_specific_tests": True,
    "coverage_signals": [],
}

_FIXTURE_DOC_EVIDENCE: dict[str, Any] = {
    "evidence_id": "doc-fixture-001",
    "source_id": "pydantic-v2-migration-guide",
    "title": "Pydantic v2 Migration Guide",
    "canonical_url": "https://docs.pydantic.dev/latest/migration/",
    "retrieved_at": "2024-01-01T00:00:00Z",
    "content_hash": "abc123",
    "section": "Model methods",
    "bounded_excerpt": ".dict() is replaced by .model_dump()",
    "related_rule_ids": ["PYD001"],
}

# ---------------------------------------------------------------------------
# parse_dependencies
# ---------------------------------------------------------------------------

_NODE_DEPS = "parse_dependencies"


async def parse_dependencies(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        return {
            "dependencies": [_FIXTURE_DEP],
            "node_executions": [node_record(_NODE_DEPS, started)],
        }

    snapshot_dict = state.get("snapshot")
    profile_dict = state.get("profile")
    if not snapshot_dict or not profile_dict:
        return {
            "dependencies": [],
            "node_executions": [node_record(_NODE_DEPS, started)],
            "warnings": ["No snapshot/profile available for dependency parsing."],
        }

    try:
        from upgradepilot.models.profile import RepositoryProfile
        from upgradepilot.models.snapshot import RepositorySnapshot

        from pathlib import Path

        from upgradepilot.analyzers.manifest_parser import parse_pyproject_toml, parse_requirements_txt

        snapshot = RepositorySnapshot.model_validate(snapshot_dict)
        profile = RepositoryProfile.model_validate(profile_dict)
        workspace = Path(snapshot.workspace_path)
        all_deps: list[Any] = []
        for manifest in profile.manifest_files:
            if manifest.parse_error:
                continue
            path = workspace / manifest.path
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            if manifest.kind in ("pyproject_toml", "pyproject.toml"):
                deps, _ = parse_pyproject_toml(content, manifest.path)
            elif manifest.kind.startswith("requirements") and manifest.kind.endswith(".txt"):
                deps, _ = parse_requirements_txt(content, manifest.path)
            elif manifest.kind in ("requirements_txt", "requirements"):
                deps, _ = parse_requirements_txt(content, manifest.path)
            else:
                continue
            all_deps.extend(deps)
        return {
            "dependencies": [d.model_dump() for d in all_deps],
            "node_executions": [node_record(_NODE_DEPS, started)],
        }
    except Exception as exc:
        return {
            "dependencies": [],
            "node_executions": [node_error_record(_NODE_DEPS, started, "DEP_PARSE_ERROR")],
            "errors": [graph_error(_NODE_DEPS, "DEP_PARSE_ERROR", str(exc))],
        }


# ---------------------------------------------------------------------------
# scan_compatibility
# ---------------------------------------------------------------------------

_NODE_SCAN = "scan_compatibility"


async def scan_compatibility(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        return {
            "findings": [_FIXTURE_FINDING],
            "node_executions": [node_record(_NODE_SCAN, started)],
        }

    snapshot_dict = state.get("snapshot")
    pack_id = state.get("pack_id", "")
    if not snapshot_dict or not pack_id:
        return {
            "findings": [],
            "node_executions": [node_record(_NODE_SCAN, started)],
            "warnings": ["Skipping compatibility scan: no snapshot or pack."],
        }

    try:
        from pathlib import Path

        from upgradepilot.analyzers.ast_scanner import scan_workspace
        from upgradepilot.migration.loader import load_all_packs
        from upgradepilot.models.snapshot import RepositorySnapshot

        snapshot = RepositorySnapshot.model_validate(snapshot_dict)
        registry = load_all_packs()
        pack = registry.get(pack_id)
        result = scan_workspace(Path(snapshot.workspace_path), pack)
        return {
            "findings": [f.model_dump() for f in result.findings],
            "node_executions": [node_record(_NODE_SCAN, started)],
        }
    except Exception as exc:
        return {
            "findings": [],
            "node_executions": [node_error_record(_NODE_SCAN, started, "SCAN_ERROR")],
            "errors": [graph_error(_NODE_SCAN, "SCAN_ERROR", str(exc))],
        }


# ---------------------------------------------------------------------------
# analyze_tests_and_ci
# ---------------------------------------------------------------------------

_NODE_TESTCI = "analyze_tests_and_ci"


async def analyze_tests_and_ci(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        return {
            "test_ci_summary": _FIXTURE_TEST_CI,
            "node_executions": [node_record(_NODE_TESTCI, started)],
        }

    profile_dict = state.get("profile")
    if not profile_dict:
        return {
            "test_ci_summary": None,
            "node_executions": [node_record(_NODE_TESTCI, started)],
            "warnings": ["No profile for test/CI analysis."],
        }

    try:
        from upgradepilot.models.profile import RepositoryProfile

        profile = RepositoryProfile.model_validate(profile_dict)
        tp = profile.test_profile
        summary: dict[str, Any] = {
            "test_files_count": len(tp.test_files),
            "frameworks": [f.value for f in tp.frameworks],
            "ci_systems": [c.value for c in tp.ci_systems],
            "has_pydantic_specific_tests": any("pydantic" in f.lower() for f in tp.test_files),
            "coverage_signals": [],
        }
        return {
            "test_ci_summary": summary,
            "node_executions": [node_record(_NODE_TESTCI, started)],
        }
    except Exception as exc:
        return {
            "test_ci_summary": None,
            "node_executions": [node_error_record(_NODE_TESTCI, started, "TESTCI_ERROR")],
            "errors": [graph_error(_NODE_TESTCI, "TESTCI_ERROR", str(exc))],
        }


# ---------------------------------------------------------------------------
# documentation_research
# ---------------------------------------------------------------------------

_NODE_DOCS = "documentation_research"


async def documentation_research(state: UpgradePilotState) -> dict[str, Any]:
    """Run the trusted Documentation Research Agent."""
    started = _now()
    findings = state.get("findings") or []
    pack_id = str(state.get("pack_id") or state.get("request_data", {}).get("migration_pack") or "")
    if not findings:
        return {
            "documentation_evidence": [],
            "node_executions": [node_record(_NODE_DOCS, started)],
            "warnings": ["Documentation research skipped: no compatibility findings."],
        }
    if not pack_id:
        return {
            "documentation_evidence": [],
            "node_executions": [
                node_error_record(_NODE_DOCS, started, "DOCUMENTATION_UNAVAILABLE")
            ],
            "errors": [
                graph_error(
                    _NODE_DOCS,
                    "DOCUMENTATION_UNAVAILABLE",
                    "Documentation research requires a selected migration pack.",
                )
            ],
        }

    try:
        from upgradepilot.agents.documentation_research import default_documentation_agent

        agent = default_documentation_agent(pack_id=pack_id)
        result = await agent.run(state=state, findings=findings)
        response: dict[str, Any] = {
            "documentation_evidence": [
                evidence.model_dump(mode="json") for evidence in result.evidence
            ],
            "node_executions": [node_record(_NODE_DOCS, started)],
            "warnings": result.warnings,
        }
        if result.status == "unavailable":
            response["errors"] = [
                graph_error(
                    _NODE_DOCS,
                    "DOCUMENTATION_UNAVAILABLE",
                    "Trusted documentation evidence is unavailable for the detected rules.",
                )
            ]
        return response
    except Exception as exc:
        return {
            "documentation_evidence": [],
            "node_executions": [node_error_record(_NODE_DOCS, started, "DOCUMENTATION_ERROR")],
            "errors": [graph_error(_NODE_DOCS, "DOCUMENTATION_ERROR", str(exc))],
        }


# ---------------------------------------------------------------------------
# aggregate_analysis  (fan-in after parallel branches)
# ---------------------------------------------------------------------------

_NODE_AGG = "aggregate_analysis"


async def aggregate_analysis(state: UpgradePilotState) -> dict[str, Any]:
    """
    Convergence node after the parallel fan-out.
    At this point all parallel branches have merged via Annotated[list, operator.add]
    reducers, so we just record execution.  No state mutation needed.
    """
    started = _now()
    n_findings = len(state.get("findings") or [])
    n_deps = len(state.get("dependencies") or [])
    n_docs = len(state.get("documentation_evidence") or [])
    return {
        "node_executions": [node_record(_NODE_AGG, started)],
        "warnings": []
        if (n_findings or n_deps or n_docs)
        else ["Aggregate: no findings, dependencies, or documentation evidence collected."],
    }
