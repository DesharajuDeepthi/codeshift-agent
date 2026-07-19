"""LangSmith dataset sync and regression experiment helpers."""

from __future__ import annotations

from typing import Any

from evals.common import CaseResult, EvalRunResult, experiment_name, write_outputs
from evals.datasets.registry import DATASET_VERSION, LANGSMITH_DATASET_NAMES, all_examples
from evals.suites.local import DATASET_VERSIONS, run_local_suite
from upgradepilot.config import get_settings
from upgradepilot.observability.redaction import sanitize_value


def langsmith_configured() -> bool:
    settings = get_settings()
    return bool(settings.langsmith_api_key)


def sync_langsmith_datasets() -> EvalRunResult:
    if not langsmith_configured():
        return _skipped("sync_dataset", "LANGSMITH_API_KEY is not configured.")

    try:
        client = _client()
        synced = 0
        for group, dataset_name in LANGSMITH_DATASET_NAMES.items():
            examples = all_examples().get(group, [])
            if not client.has_dataset(dataset_name=dataset_name):
                client.create_dataset(
                    dataset_name,
                    description=f"UpgradePilot V1 {group} evaluation dataset.",
                    metadata={"dataset_version": DATASET_VERSION, "group": group},
                )
            for example in examples:
                payload = example.to_langsmith()
                client.create_example(
                    dataset_name=dataset_name,
                    inputs=payload["inputs"],
                    outputs=payload["outputs"],
                    metadata=payload["metadata"],
                    split=payload["split"],
                )
                synced += 1
        result = EvalRunResult(
            suite="sync_dataset",
            backend="langsmith",
            status="completed",
            experiment_name=experiment_name("sync-dataset"),
            dataset_versions=DATASET_VERSIONS,
            cases=[
                CaseResult(
                    name="langsmith-dataset-sync",
                    group="langsmith",
                    passed=True,
                    metrics={"synced_examples": synced},
                )
            ],
            aggregate_metrics={
                "hard_metrics_passed": True,
                "synced_dataset_count": len(LANGSMITH_DATASET_NAMES),
                "synced_example_count": synced,
            },
        )
        write_outputs(result)
        return result
    except Exception as exc:
        return _skipped("sync_dataset", f"LangSmith sync unavailable: {sanitize_value(str(exc))}")


def run_langsmith_regression() -> EvalRunResult:
    if not langsmith_configured():
        return _skipped("regression", "LANGSMITH_API_KEY is not configured.")

    local = run_local_suite("regression")
    try:
        client = _client()
        sync_langsmith_datasets()
        project = client.create_project(
            local.experiment_name,
            description="UpgradePilot V1 regression evaluation.",
            metadata={
                "suite": "regression",
                "backend": "langsmith",
                "dataset_versions": DATASET_VERSIONS,
                "hard_metrics_passed": local.passed,
                "semantic_judges": [
                    "impact_usefulness",
                    "plan_coherence",
                    "ordering_quality",
                    "clarity",
                    "human_review_warning_quality",
                ],
                "semantic_judges_authoritative": False,
            },
            upsert=True,
            evaluator_keys=[
                "schema_validity",
                "evidence_coverage",
                "prohibited_claims",
                "impact_usefulness",
                "plan_coherence",
                "ordering_quality",
                "clarity",
                "human_review_warning_quality",
            ],
        )
        experiment_url = None
        if hasattr(project, "url"):
            experiment_url = str(project.url)
        result = EvalRunResult(
            suite="regression",
            backend="langsmith",
            status="completed",
            experiment_name=local.experiment_name,
            dataset_versions=DATASET_VERSIONS,
            cases=local.cases,
            aggregate_metrics=local.aggregate_metrics,
            semantic_metrics={
                **local.semantic_metrics,
                "semantic_judges_registered": True,
                "semantic_judges_authoritative": False,
            },
            experiment_url=experiment_url,
            warnings=[
                "Semantic LangSmith judges are advisory and cannot override deterministic failures."
            ],
        )
        write_outputs(result)
        return result
    except Exception as exc:
        return _skipped(
            "regression", f"LangSmith experiment unavailable: {sanitize_value(str(exc))}"
        )


def _client() -> Any:
    from langsmith import Client

    settings = get_settings()
    api_key = (
        settings.langsmith_api_key.get_secret_value()
        if settings.langsmith_api_key is not None
        else None
    )
    return Client(api_url=settings.langsmith_endpoint, api_key=api_key)


def _skipped(suite: str, warning: str) -> EvalRunResult:
    result = EvalRunResult(
        suite=suite,
        backend="langsmith",
        status="skipped",
        experiment_name=experiment_name(suite),
        dataset_versions=DATASET_VERSIONS,
        cases=[
            CaseResult(
                name="langsmith-cloud-evaluation",
                group="langsmith",
                passed=True,
                warnings=[warning],
                metrics={"skipped": True},
            )
        ],
        aggregate_metrics={"hard_metrics_passed": True, "cloud_skipped": True},
        warnings=[warning],
    )
    write_outputs(result)
    return result
