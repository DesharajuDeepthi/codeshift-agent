"""Shared evaluation models and artifact writing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from upgradepilot import __version__

RESULTS_DIR = Path("eval_results")


@dataclass(frozen=True)
class CaseResult:
    name: str
    group: str
    passed: bool
    metrics: dict[str, float | int | bool | str] = field(default_factory=dict)
    hard_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "passed": self.passed,
            "metrics": self.metrics,
            "hard_failures": self.hard_failures,
            "warnings": self.warnings,
            "tags": self.tags,
            "details": self.details,
        }


@dataclass(frozen=True)
class EvalRunResult:
    suite: str
    backend: str
    status: str
    experiment_name: str
    dataset_versions: dict[str, str]
    cases: list[CaseResult]
    aggregate_metrics: dict[str, float | int | bool | str]
    semantic_metrics: dict[str, float | int | bool | str] = field(default_factory=dict)
    experiment_url: str | None = None
    warnings: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    application_version: str = __version__

    @property
    def passed(self) -> bool:
        if self.status == "skipped":
            return True
        hard_metrics_ok = bool(self.aggregate_metrics.get("hard_metrics_passed", False))
        return hard_metrics_ok and all(case.passed for case in self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "backend": self.backend,
            "status": self.status,
            "passed": self.passed,
            "experiment_name": self.experiment_name,
            "experiment_url": self.experiment_url,
            "dataset_versions": self.dataset_versions,
            "application_version": self.application_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "aggregate_metrics": self.aggregate_metrics,
            "semantic_metrics": self.semantic_metrics,
            "warnings": self.warnings,
            "cases": [case.to_dict() for case in self.cases],
        }

    def print_report(self) -> None:
        print(render_markdown(self))


def write_outputs(result: EvalRunResult) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    cases_dir = RESULTS_DIR / "cases"
    comparisons_dir = RESULTS_DIR / "comparisons"
    cases_dir.mkdir(exist_ok=True)
    comparisons_dir.mkdir(exist_ok=True)

    payload = result.to_dict()
    (RESULTS_DIR / "latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (RESULTS_DIR / "latest.md").write_text(render_markdown(result), encoding="utf-8")
    (RESULTS_DIR / "junit.xml").write_text(render_junit(result), encoding="utf-8")
    (cases_dir / f"{result.experiment_name}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def render_markdown(result: EvalRunResult) -> str:
    lines = [
        f"# UpgradePilot Evaluation: {result.suite}",
        "",
        f"- Backend: `{result.backend}`",
        f"- Status: `{result.status}`",
        f"- Passed: `{result.passed}`",
        f"- Experiment: `{result.experiment_name}`",
    ]
    if result.experiment_url:
        lines.append(f"- LangSmith experiment: {result.experiment_url}")
    if result.warnings:
        lines.append(f"- Warnings: {'; '.join(result.warnings)}")
    lines.extend(["", "## Metrics", ""])
    for key, value in sorted(result.aggregate_metrics.items()):
        lines.append(f"- `{key}`: {value}")
    if result.semantic_metrics:
        lines.extend(["", "## Semantic Metrics", ""])
        for key, value in sorted(result.semantic_metrics.items()):
            lines.append(f"- `{key}`: {value}")
    lines.extend(
        ["", "## Cases", "", "| Group | Case | Passed | Hard Failures |", "|---|---|---:|---|"]
    )
    for case in result.cases:
        failures = ", ".join(case.hard_failures)
        lines.append(f"| {case.group} | {case.name} | {case.passed} | {failures} |")
    lines.append("")
    return "\n".join(lines)


def render_junit(result: EvalRunResult) -> str:
    testsuite = Element(
        "testsuite",
        {
            "name": f"upgradepilot-evals-{result.suite}-{result.backend}",
            "tests": str(len(result.cases)),
            "failures": str(sum(1 for case in result.cases if not case.passed)),
            "skipped": "1" if result.status == "skipped" else "0",
        },
    )
    for case in result.cases:
        testcase = SubElement(
            testsuite,
            "testcase",
            {"classname": case.group, "name": case.name},
        )
        if not case.passed:
            failure = SubElement(testcase, "failure", {"message": "; ".join(case.hard_failures)})
            failure.text = json.dumps(case.to_dict(), sort_keys=True)
    if result.status == "skipped":
        testcase = SubElement(testsuite, "testcase", {"classname": "langsmith", "name": "cloud"})
        SubElement(testcase, "skipped", {"message": "; ".join(result.warnings)})
    return tostring(testsuite, encoding="unicode")


def experiment_name(suite: str, prompt_version: str = "1.0.0") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return f"upgradepilot-v1-{suite}-{__version__}-{prompt_version}-{stamp}"
