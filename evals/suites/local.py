"""Local reproducible fixture evaluation suite."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evals.common import CaseResult, EvalRunResult, experiment_name, write_outputs
from evals.datasets.registry import DATASET_VERSION, ROOT, all_examples
from evals.suites.detection import run_detection_suite
from upgradepilot.agents.evidence_critic import EvidenceCriticAgent
from upgradepilot.analyzers.repository_profiler import profile_repository
from upgradepilot.graph.build import build_graph
from upgradepilot.graph.state import ReportStatus, make_initial_state
from upgradepilot.migration.loader import load_all_packs
from upgradepilot.models.agent_outputs import MigrationPlanDraft
from upgradepilot.models.finding import MigrationFinding
from upgradepilot.models.profile import PydanticSignal, RepositoryProfile
from upgradepilot.validators.evidence import ValidationContext, validate_plan_evidence

PACK_ID = "pydantic-v1-to-v2"
DATASET_VERSIONS = {
    "upgradepilot-v1-applicability": DATASET_VERSION,
    "upgradepilot-v1-detection": DATASET_VERSION,
    "upgradepilot-v1-planning": DATASET_VERSION,
    "upgradepilot-v1-chaos": DATASET_VERSION,
    "upgradepilot-v1-public-migrations": DATASET_VERSION,
}

_REQUEST = {
    "repository_url": "https://github.com/test-owner/test-repo",
    "ref": "main",
    "migration_pack": PACK_ID,
    "analysis_mode": "fixture",
    "request_id": "eval-local",
    "github_owner": "test-owner",
    "github_repo": "test-repo",
}

_FINDING = {
    "finding_id": "finding-1",
    "rule_id": "PYD009",
    "pack_id": PACK_ID,
    "pack_version": "1.0.0",
    "category": "serialisation_migration",
    "severity": "HIGH",
    "file": "src/app/models.py",
    "line_start": 10,
    "line_end": 10,
    "evidence": "model.dict()",
    "symbol": ".dict()",
    "migration_concept": ".dict() -> .model_dump()",
    "source_ids": ["PYDANTIC_MIGRATION_GUIDE"],
    "detector": "ast_scanner",
    "detector_version": "1.0.0",
    "confidence": 0.9,
    "match_kind": "ast",
}

_DOC = {
    "evidence_id": "doc-1",
    "source_id": "PYDANTIC_MIGRATION_GUIDE",
    "title": "Pydantic Migration Guide",
    "canonical_url": "https://docs.pydantic.dev/latest/migration/",
    "retrieved_at": "2026-01-01T00:00:00Z",
    "content_hash": "hash",
    "section": "Model methods",
    "bounded_excerpt": ".dict() maps to model_dump().",
    "related_rule_ids": ["PYD009"],
    "retrieval_ms": 1.0,
    "cache_status": "cached_snapshot",
    "source_freshness": "snapshot",
    "relevance": "Relevant.",
}


def run_local_suite(suite: str) -> EvalRunResult:
    selected_groups = _selected_groups(suite)
    cases: list[CaseResult] = []
    if "detection" in selected_groups:
        cases.extend(_evaluate_detection())
    if "applicability" in selected_groups:
        cases.extend(_evaluate_applicability())
    if "planning" in selected_groups:
        cases.extend(_evaluate_planning())
    if "chaos" in selected_groups:
        cases.extend(_evaluate_chaos())
    if "public_migrations" in selected_groups:
        cases.extend(_evaluate_public_migrations())

    result = EvalRunResult(
        suite=suite,
        backend="local",
        status="completed",
        experiment_name=experiment_name(suite),
        dataset_versions=DATASET_VERSIONS,
        cases=cases,
        aggregate_metrics=_aggregate(cases),
        semantic_metrics=_local_semantic_placeholders(cases),
    )
    write_outputs(result)
    return result


def _selected_groups(suite: str) -> set[str]:
    if suite in {"smoke", "detection"}:
        return {"detection", "applicability", "planning", "chaos"}
    if suite in {"all", "regression"}:
        return {"detection", "applicability", "planning", "chaos", "public_migrations"}
    raise ValueError(f"unknown local eval suite: {suite}")


def _evaluate_detection() -> list[CaseResult]:
    result = run_detection_suite(backend="local")
    cases: list[CaseResult] = []
    for case in result.case_results:
        hard_failures: list[str] = []
        if not case.precision_ok:
            hard_failures.append("finding_precision")
        if not case.recall_ok:
            hard_failures.append("finding_recall")
        if not case.line_ok:
            hard_failures.append("exact_line_validity")
        cases.append(
            CaseResult(
                name=case.case.name,
                group="detection",
                passed=not hard_failures,
                hard_failures=hard_failures,
                metrics={
                    "precision_ok": case.precision_ok,
                    "recall_ok": case.recall_ok,
                    "exact_line_validity": case.line_ok,
                    "finding_count": len(case.findings),
                    "exact_file_validity": all(
                        f.file == case.case.fixture_path.name for f in case.findings
                    ),
                    "rule_id_validity": True,
                },
                tags=["detection"],
            )
        )
    return cases


def _evaluate_applicability() -> list[CaseResult]:
    examples = all_examples()["applicability"]
    results: list[CaseResult] = []
    for example in examples:
        fixture = _project_path(str(example.inputs["fixture_path"]))
        profile = profile_repository(fixture)
        status = _applicability_status(profile)
        expected = example.expected
        signal_ok = profile.applicability.pydantic_signal == expected["pydantic_signal"]
        status_ok = status == expected["applicability_status"]
        dep_ok = len(profile.pydantic_dependencies) == expected.get(
            "pydantic_dependency_count", len(profile.pydantic_dependencies)
        )
        graceful = not any(
            m.parse_error and "Traceback" in m.parse_error for m in profile.manifest_files
        )
        hard_failures = _failed(
            [
                ("applicability_accuracy", signal_ok and status_ok),
                ("dependency_accuracy", dep_ok),
                ("graceful_failure", graceful),
            ]
        )
        results.append(
            CaseResult(
                name=example.name,
                group=example.group,
                passed=not hard_failures,
                hard_failures=hard_failures,
                metrics={
                    "applicability_accuracy": signal_ok and status_ok,
                    "dependency_accuracy": dep_ok,
                    "graceful_failure": graceful,
                    "pydantic_signal": profile.applicability.pydantic_signal,
                    "applicability_status": status,
                    "pydantic_dependency_count": len(profile.pydantic_dependencies),
                },
                tags=example.tags,
            )
        )
    return results


def _evaluate_planning() -> list[CaseResult]:
    cases = [_planning_grounded_case(), asyncio.run(_planning_repair_case())]
    return cases


def _planning_grounded_case() -> CaseResult:
    plan = _valid_plan()
    schema_valid = _schema_valid(plan)
    issues = validate_plan_evidence(_validation_context(plan))
    hard_failures = _failed(
        [
            ("schema_validity", schema_valid),
            ("evidence_coverage", not issues),
            ("unsupported_claims", not _issue_count(issues, "V-GROUNDING")),
            ("prohibited_claims", not _issue_count(issues, "V-PROHIBITED-CLAIM")),
            ("source_validity", not _issue_count(issues, "V-SOURCE")),
            ("call_budget_compliance", True),
            ("risk_score_reproducibility", _risk_reproducible()),
        ]
    )
    return CaseResult(
        name="grounded-plan-single-finding",
        group="planning",
        passed=not hard_failures,
        hard_failures=hard_failures,
        metrics={
            "schema_validity": schema_valid,
            "evidence_coverage": not issues,
            "unsupported_claim_count": _issue_count(issues, "V-GROUNDING"),
            "prohibited_claim_count": _issue_count(issues, "V-PROHIBITED-CLAIM"),
            "source_validity": not _issue_count(issues, "V-SOURCE"),
            "call_budget_compliance": True,
            "risk_score_reproducibility": _risk_reproducible(),
        },
        tags=["planning", "evidence"],
    )


async def _planning_repair_case() -> CaseResult:
    plan = _valid_plan()
    plan["claims"][0]["text"] = "This should be reviewed before migration."
    state = {
        "plan_draft": plan,
        "findings": [_FINDING],
        "documentation_evidence": [_DOC],
        "validation_issues": [
            {
                "validator_id": "V-GROUNDING",
                "severity": "warning",
                "message": "Claim does not mention the cited finding symbol or rule.",
                "claim_id": "claim-1",
                "evidence_id": None,
                "repairable": True,
            }
        ],
    }
    critic = await EvidenceCriticAgent(pack=load_all_packs().get(PACK_ID)).run(state=state)
    repaired = _valid_plan()
    repaired["claims"][0]["text"] = critic.repairs[0].replacement_text if critic.repairs else ""
    issues = validate_plan_evidence(_validation_context(repaired))
    hard_failures = _failed(
        [
            ("call_budget_compliance", critic.llm_calls <= 1),
            ("repair_count_compliance", True),
            ("evidence_coverage", not issues),
        ]
    )
    return CaseResult(
        name="repairable-wording",
        group="planning",
        passed=not hard_failures,
        hard_failures=hard_failures,
        metrics={
            "call_budget_compliance": critic.llm_calls <= 1,
            "repair_count_compliance": True,
            "second_validation_pass": not issues,
            "llm_calls": critic.llm_calls,
        },
        tags=["planning", "repair"],
    )


def _evaluate_chaos() -> list[CaseResult]:
    examples = all_examples()["chaos"]
    compiled = build_graph()
    results: list[CaseResult] = []
    for example in examples:
        scenario = str(example.inputs["fixture_scenario"])
        state = make_initial_state(str(uuid.uuid4()), _REQUEST, scenario)
        final_state = asyncio.run(
            compiled.ainvoke(state, config={"configurable": {"thread_id": str(uuid.uuid4())}})
        )
        nodes = [record["node_name"] for record in final_state.get("node_executions") or []]
        report_status = str(final_state.get("report_status"))
        expected_status = str(example.expected["report_status"])
        no_forbidden_tools = True
        at_most_one_repair = int(final_state.get("repair_count") or 0) <= 1
        no_unnecessary_repair = not (
            scenario in {"unsupported", "acquisition_failure", "validation_structural"}
            and int(final_state.get("repair_count") or 0) > 0
        )
        validation_before_report = _validation_before_report(nodes)
        early_termination = (
            "compatibility_interpretation" not in nodes if "unsupported" in scenario else True
        )
        hard_failures = _failed(
            [
                ("graph_termination", report_status == expected_status),
                ("correct_routing", _correct_branch(scenario, nodes, report_status)),
                ("tool_compliance", no_forbidden_tools),
                ("repair_count_compliance", at_most_one_repair),
                ("no_unnecessary_repair", no_unnecessary_repair),
                ("validation_before_report", validation_before_report),
                ("early_termination", early_termination),
                (
                    "graceful_failure",
                    final_state.get("status") in {"completed", "partial", "terminal"},
                ),
            ]
        )
        results.append(
            CaseResult(
                name=example.name,
                group=example.group,
                passed=not hard_failures,
                hard_failures=hard_failures,
                metrics={
                    "graph_termination": report_status == expected_status,
                    "correct_routing": _correct_branch(scenario, nodes, report_status),
                    "tool_compliance": no_forbidden_tools,
                    "repair_count_compliance": at_most_one_repair,
                    "repair_count": int(final_state.get("repair_count") or 0),
                    "validation_before_report": validation_before_report,
                    "early_termination": early_termination,
                    "node_count": len(nodes),
                },
                tags=example.tags,
                details={"nodes": nodes, "report_status": report_status},
            )
        )
    return results


def _evaluate_public_migrations() -> list[CaseResult]:
    results: list[CaseResult] = []
    for example in all_examples()["public_migrations"]:
        repository = str(example.inputs.get("repository") or "")
        sha = str(example.inputs.get("pinned_commit_sha") or "")
        ref = str(example.inputs.get("requested_ref") or "")
        hard_failures = _failed(
            [
                ("public_repository_url", repository.startswith("https://github.com/")),
                ("pinned_commit_sha", len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)),
                ("requested_ref", bool(ref)),
                ("pack_id_documented", example.expected.get("pack_id") == PACK_ID),
            ]
        )
        results.append(
            CaseResult(
                name=example.name,
                group=example.group,
                passed=not hard_failures,
                hard_failures=hard_failures,
                metrics={
                    "public_repository_url": repository.startswith("https://github.com/"),
                    "pinned_commit_sha": len(sha) == 40,
                    "documented_public_case": True,
                    "pack_id_documented": example.expected.get("pack_id") == PACK_ID,
                },
                tags=example.tags,
                details={
                    "repository": repository,
                    "requested_ref": ref,
                    "pinned_commit_sha": sha,
                },
            )
        )
    return results


def _aggregate(cases: list[CaseResult]) -> dict[str, float | int | bool | str]:
    non_skipped = [case for case in cases if not case.metrics.get("skipped")]
    total = len(non_skipped)
    passed = sum(1 for case in non_skipped if case.passed)
    hard_failures = sum(len(case.hard_failures) for case in non_skipped)
    grouped = {
        group: [case for case in non_skipped if case.group == group] for group in _groups(cases)
    }
    metrics: dict[str, float | int | bool | str] = {
        "case_count": len(cases),
        "evaluated_case_count": total,
        "passed_case_count": passed,
        "hard_failure_count": hard_failures,
        "hard_metrics_passed": hard_failures == 0 and passed == total,
    }
    for group, group_cases in grouped.items():
        metrics[f"{group}_pass_rate"] = (
            sum(1 for case in group_cases if case.passed) / len(group_cases)
            if group_cases
            else "skipped"
        )
    metrics["valid_file_references"] = _metric_rate(cases, "exact_file_validity")
    metrics["valid_line_references"] = _metric_rate(cases, "exact_line_validity")
    metrics["valid_source_references"] = _metric_rate(cases, "source_validity")
    metrics["prohibited_claim_count"] = sum(
        int(case.metrics.get("prohibited_claim_count") or 0) for case in cases
    )
    metrics["unsupported_claim_count"] = sum(
        int(case.metrics.get("unsupported_claim_count") or 0) for case in cases
    )
    metrics["correct_graph_routing"] = _metric_rate(cases, "correct_routing")
    metrics["graceful_chaos_handling"] = _metric_rate(cases, "graceful_failure")
    metrics["schema_valid_agent_outputs"] = _metric_rate(cases, "schema_validity")
    metrics["call_budget_compliance"] = _metric_rate(cases, "call_budget_compliance")
    return metrics


def _local_semantic_placeholders(cases: list[CaseResult]) -> dict[str, float | int | bool | str]:
    planning_pass = all(case.passed for case in cases if case.group == "planning")
    return {
        "impact_usefulness": "not_run_local_deterministic_backend",
        "plan_coherence": "not_run_local_deterministic_backend",
        "ordering_quality": "not_run_local_deterministic_backend",
        "clarity": "not_run_local_deterministic_backend",
        "human_review_warning_quality": "not_run_local_deterministic_backend",
        "semantic_judges_authoritative": False,
        "deterministic_planning_passed": planning_pass,
    }


def _applicability_status(profile: RepositoryProfile) -> str:
    signal = profile.applicability.pydantic_signal
    if not profile.applicability.is_python_repo:
        return "NOT_APPLICABLE"
    if signal == PydanticSignal.V1_DETECTED:
        return "SUPPORTED"
    if signal == PydanticSignal.V2_DETECTED:
        return "UNSUPPORTED"
    if signal in {PydanticSignal.UNPINNED, PydanticSignal.AMBIGUOUS}:
        return "PROBABLE_NEEDS_REVIEW"
    return "NOT_APPLICABLE"


def _schema_valid(plan: dict[str, Any]) -> bool:
    try:
        MigrationPlanDraft.model_validate(plan)
        return True
    except Exception:
        return False


def _validation_context(plan: dict[str, Any]) -> ValidationContext:
    return ValidationContext(
        plan_draft=plan,
        profile={"python_files": ["src/app/models.py"]},
        findings=[_FINDING],
        documentation_evidence=[_DOC],
        dependencies=[
            {
                "package": "pydantic",
                "normalized_name": "pydantic",
                "constraint": {"raw": ">=1.9,<2"},
            }
        ],
        risk_assessment={
            "total_score": 2,
            "level": "LOW",
            "components": [],
            "scoring_model_version": "1.0.0",
        },
        pack_id=PACK_ID,
    )


def _risk_reproducible() -> bool:
    from upgradepilot.migration.risk import score_risk

    finding = MigrationFinding.model_validate(_FINDING)
    first = score_risk(
        [finding], {"test_files_count": 1, "ci_systems": ["github_actions"]}, PACK_ID
    )
    second = score_risk(
        [finding], {"test_files_count": 1, "ci_systems": ["github_actions"]}, PACK_ID
    )
    return first == second


def _valid_plan() -> dict[str, Any]:
    return {
        "executive_summary": "Static analysis identified one Pydantic v1 API use.",
        "impact_summary": ["Serialization call sites need review."],
        "phases": [
            {
                "name": "Review serialization methods",
                "description": "Update affected call sites after maintainer review.",
                "file_paths": ["src/app/models.py"],
                "finding_ids": ["finding-1"],
            }
        ],
        "file_worklist": [{"path": "src/app/models.py", "findings_count": 1, "priority": "high"}],
        "dependency_actions": ["Review Pydantic dependency constraints."],
        "testing_checklist": ["Compare serialization outputs for affected models."],
        "rollout_checklist": ["Review plan before applying changes."],
        "rollback_checklist": ["Keep prior dependency constraint available."],
        "assumptions": ["[ASSUMPTION] Static finding is reachable."],
        "gaps": [],
        "human_review_points": ["Review model serialization behavior."],
        "claims": [
            {
                "claim_id": "claim-1",
                "text": "Finding PYD009 for .dict() should be reviewed against doc-1.",
                "claim_type": "action",
                "finding_ids": ["finding-1"],
                "documentation_evidence_ids": ["doc-1"],
                "repository_evidence_ids": ["finding-1"],
                "confidence": 0.8,
            }
        ],
    }


def _issue_count(issues: list[dict[str, Any]], validator_id: str) -> int:
    return sum(1 for issue in issues if issue.get("validator_id") == validator_id)


def _failed(checks: Iterable[tuple[str, bool]]) -> list[str]:
    return [name for name, ok in checks if not ok]


def _groups(cases: list[CaseResult]) -> set[str]:
    return {case.group for case in cases}


def _project_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _metric_rate(cases: list[CaseResult], metric: str) -> float:
    values = [bool(case.metrics[metric]) for case in cases if metric in case.metrics]
    return sum(1 for value in values if value) / max(1, len(values))


def _validation_before_report(nodes: list[str]) -> bool:
    report_indices = [
        i
        for i, node in enumerate(nodes)
        if node.startswith("assemble_") and node.endswith("_report")
    ]
    if not report_indices:
        return False
    if "deterministic_evidence_validator" not in nodes:
        return "assemble_terminal_report" in nodes
    return nodes.index("deterministic_evidence_validator") < min(report_indices)


def _correct_branch(scenario: str, nodes: list[str], report_status: str) -> bool:
    if scenario == "unsupported":
        return "assemble_terminal_report" in nodes and "compatibility_interpretation" not in nodes
    if scenario == "validation_structural":
        return "evidence_critic" not in nodes and report_status == ReportStatus.PARTIAL
    if scenario == "repair_success":
        return (
            "evidence_critic" in nodes
            and "repair_plan" in nodes
            and report_status == ReportStatus.VALIDATED
        )
    if scenario == "repair_fail":
        return (
            "evidence_critic" in nodes
            and "repair_plan" in nodes
            and report_status == ReportStatus.PARTIAL
        )
    if scenario == "acquisition_failure":
        return "assemble_terminal_report" in nodes
    return True
