from __future__ import annotations

from typing import Any

import pytest

from upgradepilot.agents.compatibility_interpretation import CompatibilityInterpretationAgent
from upgradepilot.agents.migration_planning import MigrationPlanningAgent
from upgradepilot.graph.state import FIXTURE_SUPPORTED, make_initial_state
from upgradepilot.llm.client import LLMTask, LLMTimeout, StaticLLMClient
from upgradepilot.migration.loader import load_all_packs

_REQUEST = {
    "repository_url": "https://github.com/test-owner/test-repo",
    "ref": "main",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "fixture",
    "request_id": "agents-test",
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


def _pack():
    return load_all_packs().get("pydantic-v1-to-v2")


def _state() -> dict[str, Any]:
    state = make_initial_state("analysis-agents-test", _REQUEST, FIXTURE_SUPPORTED)
    state["findings"] = [_FINDING]
    state["documentation_evidence"] = [_DOC]
    state["risk_assessment"] = {
        "total_score": 2,
        "level": "low",
        "components": [],
        "scoring_model_version": "1.0.0",
    }
    return state


@pytest.mark.asyncio
async def test_compatibility_rejects_malformed_output() -> None:
    client = StaticLLMClient(outputs={LLMTask.COMPATIBILITY_INTERPRETATION: {"bad": []}})
    result = await CompatibilityInterpretationAgent(pack=_pack(), llm_client=client).run(
        state=_state()
    )

    assert result.status == "partial"
    assert result.llm_calls == 1
    assert result.interpretations == []


@pytest.mark.asyncio
async def test_compatibility_timeout_is_partial() -> None:
    client = StaticLLMClient(
        raise_for={LLMTask.COMPATIBILITY_INTERPRETATION: LLMTimeout("timeout")}
    )
    result = await CompatibilityInterpretationAgent(pack=_pack(), llm_client=client).run(
        state=_state()
    )

    assert result.status == "partial"
    assert "timeout" in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_planning_rejects_unknown_finding_reference() -> None:
    bad_plan = _valid_plan_output()
    bad_plan["plan"]["claims"][0]["finding_ids"] = ["new-finding"]
    client = StaticLLMClient(outputs={LLMTask.MIGRATION_PLANNING: bad_plan})

    result = await MigrationPlanningAgent(pack=_pack(), llm_client=client).run(state=_state())

    assert result.status == "partial"
    assert result.plan is not None
    assert result.plan.claims[0].finding_ids == ["finding-1"]


@pytest.mark.asyncio
async def test_planning_rejects_forbidden_claims() -> None:
    bad_plan = _valid_plan_output()
    bad_plan["plan"]["claims"][0]["text"] = "Tests passed after the migration."
    client = StaticLLMClient(outputs={LLMTask.MIGRATION_PLANNING: bad_plan})

    result = await MigrationPlanningAgent(pack=_pack(), llm_client=client).run(state=_state())

    assert result.status == "partial"
    assert any("malformed" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_planning_budget_exceeded_is_partial() -> None:
    client = StaticLLMClient()
    state = _state()
    state["findings"] = [{**_FINDING, "evidence": "x" * 100_000}]

    result = await MigrationPlanningAgent(pack=_pack(), llm_client=client).run(state=state)

    assert result.status == "partial"
    assert any("budget" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_planning_valid_output_keeps_known_evidence_links() -> None:
    client = StaticLLMClient(outputs={LLMTask.MIGRATION_PLANNING: _valid_plan_output()})

    result = await MigrationPlanningAgent(pack=_pack(), llm_client=client).run(state=_state())

    assert result.status == "completed"
    assert result.plan is not None
    assert result.plan.claims[0].finding_ids == ["finding-1"]
    assert result.plan.claims[0].documentation_evidence_ids == ["doc-1"]


def _valid_plan_output() -> dict[str, Any]:
    return {
        "plan": {
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
            "file_worklist": [
                {"path": "src/app/models.py", "findings_count": 1, "priority": "high"}
            ],
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
                    "text": "The cited finding should be reviewed against the migration evidence.",
                    "claim_type": "action",
                    "finding_ids": ["finding-1"],
                    "documentation_evidence_ids": ["doc-1"],
                    "repository_evidence_ids": ["finding-1"],
                    "confidence": 0.8,
                }
            ],
        },
        "warnings": [],
    }
