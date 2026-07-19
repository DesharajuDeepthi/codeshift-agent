"""Versioned evaluation dataset registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = ROOT / "tests" / "fixtures"

DATASET_VERSION = "1.0.0"

LANGSMITH_DATASET_NAMES = {
    "applicability": "upgradepilot-v1-applicability",
    "detection": "upgradepilot-v1-detection",
    "planning": "upgradepilot-v1-planning",
    "chaos": "upgradepilot-v1-chaos",
    "public_migrations": "upgradepilot-v1-public-migrations",
}


@dataclass(frozen=True)
class DatasetExample:
    name: str
    group: str
    inputs: dict[str, Any]
    expected: dict[str, Any]
    split: str = "regression"
    tags: list[str] = field(default_factory=list)

    def to_langsmith(self) -> dict[str, Any]:
        return {
            "inputs": {
                **self.inputs,
                "dataset_version": DATASET_VERSION,
                "group": self.group,
            },
            "outputs": self.expected,
            "metadata": {
                "name": self.name,
                "tags": self.tags,
                "dataset_version": DATASET_VERSION,
            },
            "split": self.split,
        }


def applicability_examples() -> list[DatasetExample]:
    return [
        DatasetExample(
            name="requirements-pydantic-v1",
            group="applicability",
            inputs={"fixture_path": "tests/fixtures/req_txt"},
            expected={
                "pydantic_signal": "v1_detected",
                "applicability_status": "SUPPORTED",
                "pydantic_dependency_count": 1,
            },
            split="smoke",
            tags=["manifest:requirements", "pydantic:v1"],
        ),
        DatasetExample(
            name="pep621-pydantic-v2",
            group="applicability",
            inputs={"fixture_path": "tests/fixtures/pep621"},
            expected={
                "pydantic_signal": "v2_detected",
                "applicability_status": "UNSUPPORTED",
                "pydantic_dependency_count": 1,
            },
            tags=["manifest:pyproject", "pydantic:v2"],
        ),
        DatasetExample(
            name="no-pydantic-python",
            group="applicability",
            inputs={"fixture_path": "tests/fixtures/no_pydantic"},
            expected={
                "pydantic_signal": "not_found",
                "applicability_status": "NOT_APPLICABLE",
                "pydantic_dependency_count": 0,
            },
            tags=["pydantic:none"],
        ),
        DatasetExample(
            name="unpinned-pydantic",
            group="applicability",
            inputs={"fixture_path": "tests/fixtures/unpinned_pydantic"},
            expected={
                "pydantic_signal": "unpinned",
                "applicability_status": "NOT_APPLICABLE",
                "pydantic_dependency_count": 1,
            },
            tags=["manifest:requirements", "pydantic:unpinned"],
        ),
        DatasetExample(
            name="malformed-manifests",
            group="applicability",
            inputs={"fixture_path": "tests/fixtures/malformed"},
            expected={
                "pydantic_signal": "v1_detected",
                "applicability_status": "NOT_APPLICABLE",
                "graceful_failure": True,
            },
            tags=["malformed"],
        ),
    ]


def planning_examples() -> list[DatasetExample]:
    return [
        DatasetExample(
            name="grounded-plan-single-finding",
            group="planning",
            inputs={"fixture": "single-pyd009-finding"},
            expected={
                "schema_valid": True,
                "evidence_coverage": True,
                "prohibited_claim_count": 0,
                "unsupported_claim_count": 0,
                "call_budget_compliant": True,
            },
            split="smoke",
            tags=["planning", "evidence"],
        ),
        DatasetExample(
            name="repairable-wording",
            group="planning",
            inputs={"fixture": "repairable-grounding"},
            expected={
                "repair_count": 1,
                "second_validation_pass": True,
                "call_budget_compliant": True,
            },
            tags=["planning", "repair"],
        ),
    ]


def chaos_examples() -> list[DatasetExample]:
    return [
        DatasetExample(
            name="github-acquisition-failure",
            group="chaos",
            inputs={"fixture_scenario": "acquisition_failure"},
            expected={"report_status": "terminal", "graceful_failure": True, "repair_count": 0},
            tags=["chaos", "github"],
        ),
        DatasetExample(
            name="unsupported-terminates-early",
            group="chaos",
            inputs={"fixture_scenario": "unsupported"},
            expected={"report_status": "terminal", "early_termination": True, "repair_count": 0},
            tags=["trajectory", "unsupported"],
        ),
        DatasetExample(
            name="structural-validation-partial",
            group="chaos",
            inputs={"fixture_scenario": "validation_structural"},
            expected={"report_status": "partial", "repair_count": 0, "graceful_failure": True},
            tags=["validation", "structural"],
        ),
        DatasetExample(
            name="single-repair-success",
            group="chaos",
            inputs={"fixture_scenario": "repair_success"},
            expected={"report_status": "validated", "repair_count": 1, "trajectory": "repair_pass"},
            split="smoke",
            tags=["trajectory", "repair"],
        ),
        DatasetExample(
            name="second-validation-failure",
            group="chaos",
            inputs={"fixture_scenario": "repair_fail"},
            expected={
                "report_status": "partial",
                "repair_count": 1,
                "trajectory": "repair_partial",
            },
            tags=["trajectory", "repair"],
        ),
    ]


def public_migration_examples() -> list[DatasetExample]:
    return [
        DatasetExample(
            name="pydantic-v1.10.15-release",
            group="public_migrations",
            inputs={
                "repository": "https://github.com/pydantic/pydantic",
                "requested_ref": "v1.10.15",
                "pinned_commit_sha": "5476a758c8ac59887dbfa3aa1c3481d0a0e20837",
            },
            expected={"documented": True, "pinned": True, "pack_id": "pydantic-v1-to-v2"},
            tags=["public", "pinned", "pydantic:v1"],
        ),
        DatasetExample(
            name="fastapi-0.95.2-release",
            group="public_migrations",
            inputs={
                "repository": "https://github.com/fastapi/fastapi",
                "requested_ref": "0.95.2",
                "pinned_commit_sha": "8cc967a7605d3883bd04ceb5d25cc94ae079612f",
            },
            expected={"documented": True, "pinned": True, "pack_id": "pydantic-v1-to-v2"},
            tags=["public", "pinned", "fastapi", "pydantic:v1"],
        ),
    ]


def all_examples() -> dict[str, list[DatasetExample]]:
    return {
        "applicability": applicability_examples(),
        "planning": planning_examples(),
        "chaos": chaos_examples(),
        "public_migrations": public_migration_examples(),
    }
