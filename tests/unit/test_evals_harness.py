from __future__ import annotations

import json
from pathlib import Path

from evals.compare import compare_results
from evals.suites.local import run_local_suite


def test_local_smoke_writes_required_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_local_suite("smoke")

    assert result.passed
    assert Path("eval_results/latest.json").exists()
    assert Path("eval_results/latest.md").exists()
    assert Path("eval_results/junit.xml").exists()
    latest = json.loads(Path("eval_results/latest.json").read_text(encoding="utf-8"))
    assert latest["suite"] == "smoke"
    assert latest["backend"] == "local"
    assert latest["aggregate_metrics"]["hard_metrics_passed"] is True
    groups = {case["group"] for case in latest["cases"]}
    assert {"applicability", "detection", "planning", "chaos"}.issubset(groups)


def test_local_all_includes_public_migration_group_as_pinned_examples(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_local_suite("all")

    assert result.passed
    assert result.aggregate_metrics["public_migrations_pass_rate"] == 1.0
    public_cases = [case for case in result.cases if case.group == "public_migrations"]
    assert len(public_cases) >= 2
    assert all(case.metrics["pinned_commit_sha"] for case in public_cases)


def test_compare_fails_on_hard_metric_regression(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cases = Path("eval_results/cases")
    cases.mkdir(parents=True)
    baseline = {
        "aggregate_metrics": {
            "hard_failure_count": 0,
            "valid_file_references": 1.0,
            "prohibited_claim_count": 0,
        }
    }
    candidate = {
        "aggregate_metrics": {
            "hard_failure_count": 1,
            "valid_file_references": 0.5,
            "prohibited_claim_count": 1,
        }
    }
    (cases / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    (cases / "candidate.json").write_text(json.dumps(candidate), encoding="utf-8")

    comparison = compare_results("baseline", "candidate")

    assert not comparison["passed"]
    assert {"hard_failure_count", "valid_file_references", "prohibited_claim_count"}.issubset(
        comparison["hard_metric_regressions"]
    )
