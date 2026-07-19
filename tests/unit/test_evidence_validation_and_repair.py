from __future__ import annotations

from typing import Any

import pytest

from upgradepilot.agents.evidence_critic import EvidenceCriticAgent
from upgradepilot.graph.nodes.agents import repair_plan
from upgradepilot.graph.nodes.evidence import deterministic_evidence_validator
from upgradepilot.graph.state import FIXTURE_SUPPORTED, ValidationOutcome, make_initial_state
from upgradepilot.llm.client import LLMTask, LLMTimeout, StaticLLMClient
from upgradepilot.migration.loader import load_all_packs
from upgradepilot.validators.evidence import ValidationContext, validate_plan_evidence

_REQUEST = {
    "repository_url": "https://github.com/test-owner/test-repo",
    "ref": "main",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "standard",
    "request_id": "validation-test",
    "github_owner": "test-owner",
    "github_repo": "test-repo",
}

_FINDING = {
    "finding_id": "finding-1",
    "rule_id": "PYD009",
    "pack_id": "pydantic-v1-to-v2",
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
                "text": (
                    "Finding PYD009 for .dict() should be reviewed against "
                    "documentation evidence doc-1."
                ),
                "claim_type": "action",
                "finding_ids": ["finding-1"],
                "documentation_evidence_ids": ["doc-1"],
                "repository_evidence_ids": ["finding-1"],
                "confidence": 0.8,
            }
        ],
    }


def _context(
    *,
    plan: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
    docs: list[dict[str, Any]] | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    risk: dict[str, Any] | None = None,
    pack_id: str = "pydantic-v1-to-v2",
) -> ValidationContext:
    return ValidationContext(
        plan_draft=plan or _valid_plan(),
        profile=profile or {"python_files": ["src/app/models.py"]},
        findings=findings or [_FINDING],
        documentation_evidence=docs or [_DOC],
        dependencies=dependencies
        or [
            {
                "package": "pydantic",
                "normalized_name": "pydantic",
                "constraint": {"raw": ">=1.9,<2"},
            }
        ],
        risk_assessment=risk
        or {
            "total_score": 2,
            "level": "LOW",
            "components": [],
            "scoring_model_version": "1.0.0",
        },
        pack_id=pack_id,
    )


def _issue_ids(issues: list[dict[str, Any]]) -> set[str]:
    return {str(issue["validator_id"]) for issue in issues}


def test_validation_complete_pass() -> None:
    assert validate_plan_evidence(_context()) == []


def test_validation_invalid_file_is_structural() -> None:
    plan = _valid_plan()
    plan["file_worklist"][0]["path"] = "src/app/missing.py"

    issues = validate_plan_evidence(_context(plan=plan))

    assert "V-FILE-REF" in _issue_ids(issues)
    assert not next(issue for issue in issues if issue["validator_id"] == "V-FILE-REF")[
        "repairable"
    ]


def test_validation_invalid_line_range_is_structural() -> None:
    finding = {**_FINDING, "line_end": 9}

    issues = validate_plan_evidence(_context(findings=[finding]))

    assert "V-LINE-RANGE" in _issue_ids(issues)
    assert not next(issue for issue in issues if issue["validator_id"] == "V-LINE-RANGE")[
        "repairable"
    ]


def test_validation_invalid_source_is_structural() -> None:
    doc = {**_DOC, "source_id": "STACK_OVERFLOW", "canonical_url": "https://stackoverflow.com/q/1"}

    issues = validate_plan_evidence(_context(docs=[doc]))

    assert "V-SOURCE" in _issue_ids(issues)
    assert not next(issue for issue in issues if issue["validator_id"] == "V-SOURCE")["repairable"]


def test_validation_unsupported_package_version_is_structural() -> None:
    plan = _valid_plan()
    plan["claims"][0]["text"] = "Finding PYD009 for .dict() should use Pydantic 2.7.0."

    issues = validate_plan_evidence(_context(plan=plan))

    assert "V-VERSION" in _issue_ids(issues)
    assert not next(issue for issue in issues if issue["validator_id"] == "V-VERSION")["repairable"]


def test_validation_uncited_recommendation_is_terminal_evidence_failure() -> None:
    plan = _valid_plan()
    plan["claims"][0]["finding_ids"] = []
    plan["claims"][0]["documentation_evidence_ids"] = []

    issues = validate_plan_evidence(_context(plan=plan))

    assert {"V-FINDING-REF", "V-EVIDENCE"}.issubset(_issue_ids(issues))
    assert any(not issue["repairable"] for issue in issues)


def test_validation_claim_that_tests_passed_is_structural() -> None:
    plan = _valid_plan()
    plan["claims"][0]["text"] = "Tests passed after replacing .dict()."

    issues = validate_plan_evidence(_context(plan=plan))

    assert "V-PROHIBITED-CLAIM" in _issue_ids(issues)
    assert not next(issue for issue in issues if issue["validator_id"] == "V-PROHIBITED-CLAIM")[
        "repairable"
    ]


def test_validation_overconfident_wording_is_repairable() -> None:
    plan = _valid_plan()
    plan["claims"][0]["text"] = "Finding PYD009 for .dict() will definitely be safe to deploy."

    issues = validate_plan_evidence(_context(plan=plan))

    assert "V-PROHIBITED-CLAIM" in _issue_ids(issues)
    assert next(issue for issue in issues if issue["validator_id"] == "V-PROHIBITED-CLAIM")[
        "repairable"
    ]


@pytest.mark.asyncio
async def test_evidence_critic_rejects_added_evidence_ids() -> None:
    state = make_initial_state("analysis-validation-test", _REQUEST, FIXTURE_SUPPORTED)
    state["plan_draft"] = _valid_plan()
    state["findings"] = [_FINDING]
    state["documentation_evidence"] = [_DOC]
    state["validation_issues"] = [
        {
            "validator_id": "V-GROUNDING",
            "severity": "warning",
            "message": "Claim needs grounding.",
            "claim_id": "claim-1",
            "evidence_id": None,
            "repairable": True,
        }
    ]
    client = StaticLLMClient(
        outputs={
            LLMTask.EVIDENCE_CRITIC: {
                "repairs": [
                    {
                        "claim_id": "claim-1",
                        "replacement_text": "Finding PYD009 for .dict() needs review.",
                        "keep_finding_ids": ["finding-1", "new-finding"],
                        "keep_documentation_evidence_ids": ["doc-1"],
                        "rationale": "Bad repair adds evidence.",
                    }
                ],
                "approved_claim_ids": [],
                "summary": "Bad repair.",
                "warnings": [],
            }
        }
    )

    result = await EvidenceCriticAgent(
        pack=load_all_packs().get("pydantic-v1-to-v2"), llm_client=client
    ).run(state=state)

    assert result.status == "partial"
    assert result.llm_calls == 1


@pytest.mark.asyncio
async def test_evidence_critic_timeout_is_partial() -> None:
    state = make_initial_state("analysis-validation-timeout", _REQUEST, FIXTURE_SUPPORTED)
    state["plan_draft"] = _valid_plan()
    state["findings"] = [_FINDING]
    state["documentation_evidence"] = [_DOC]
    state["validation_issues"] = [
        {
            "validator_id": "V-GROUNDING",
            "severity": "warning",
            "message": "Claim needs grounding.",
            "claim_id": "claim-1",
            "evidence_id": None,
            "repairable": True,
        }
    ]
    client = StaticLLMClient(raise_for={LLMTask.EVIDENCE_CRITIC: LLMTimeout("timeout")})

    result = await EvidenceCriticAgent(
        pack=load_all_packs().get("pydantic-v1-to-v2"), llm_client=client
    ).run(state=state)

    assert result.status == "partial"
    assert result.llm_calls == 1
    assert "timeout" in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_successful_repair_and_second_validation_pass() -> None:
    plan = _valid_plan()
    plan["claims"][0]["text"] = "This should be reviewed before migration."
    state = make_initial_state("analysis-repair-test", _REQUEST, FIXTURE_SUPPORTED)
    state["profile"] = {"python_files": ["src/app/models.py"]}
    state["plan_draft"] = plan
    state["findings"] = [_FINDING]
    state["documentation_evidence"] = [_DOC]
    state["dependencies"] = [
        {
            "package": "pydantic",
            "normalized_name": "pydantic",
            "constraint": {"raw": ">=1.9,<2"},
        }
    ]
    state["risk_assessment"] = {
        "total_score": 2,
        "level": "LOW",
        "components": [],
        "scoring_model_version": "1.0.0",
    }
    state["pack_id"] = "pydantic-v1-to-v2"

    first = await deterministic_evidence_validator(state)
    state.update(first)
    assert state["validation_outcome"] == ValidationOutcome.REPAIRABLE

    critic = await EvidenceCriticAgent(pack=load_all_packs().get("pydantic-v1-to-v2")).run(
        state=state
    )
    state["repair_instructions"] = [repair.model_dump(mode="json") for repair in critic.repairs]
    repaired = await repair_plan(state)
    state.update(repaired)
    second = await deterministic_evidence_validator(state)

    assert critic.llm_calls == 1
    assert repaired["repair_count"] == 1
    assert second["validation_outcome"] == ValidationOutcome.PASS
    assert second["validation_issues"] == []


@pytest.mark.asyncio
async def test_second_failure_remains_partial_trajectory() -> None:
    plan = _valid_plan()
    plan["claims"][0]["text"] = "This should be reviewed before migration."
    state = make_initial_state("analysis-second-failure-test", _REQUEST, FIXTURE_SUPPORTED)
    state["profile"] = {"python_files": ["src/app/models.py"]}
    state["plan_draft"] = plan
    state["findings"] = [_FINDING]
    state["documentation_evidence"] = [_DOC]
    state["risk_assessment"] = {
        "total_score": 2,
        "level": "LOW",
        "components": [],
        "scoring_model_version": "1.0.0",
    }
    state["pack_id"] = "pydantic-v1-to-v2"
    state.update(await deterministic_evidence_validator(state))
    state["repair_instructions"] = []

    repaired = await repair_plan(state)
    state.update(repaired)
    second = await deterministic_evidence_validator(state)

    assert repaired["repair_count"] == 1
    assert second["validation_outcome"] == ValidationOutcome.REPAIRABLE
    assert second["validation_issues"][0]["repairable"]
