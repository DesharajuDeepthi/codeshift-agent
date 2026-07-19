from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from upgradepilot.agents.documentation_research import DocumentationResearchAgent
from upgradepilot.graph.state import FIXTURE_SUPPORTED, make_initial_state
from upgradepilot.migration.loader import load_all_packs

_REQUEST = {
    "repository_url": "https://github.com/test-owner/test-repo",
    "ref": "main",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "fixture",
    "request_id": "docs-agent-test",
    "github_owner": "test-owner",
    "github_repo": "test-repo",
}

_FINDING = {
    "finding_id": "finding-1",
    "rule_id": "PYD009",
    "source_ids": ["PYDANTIC_MIGRATION_GUIDE", "PYDANTIC_V2_SERIALIZATION"],
}


def _pack():
    return load_all_packs().get("pydantic-v1-to-v2")


def _state() -> dict[str, Any]:
    return make_initial_state("analysis-docs-test", _REQUEST, FIXTURE_SUPPORTED)


class MalformedLLM:
    async def generate_structured(self, request):
        from upgradepilot.llm.client import StructuredLLMResponse

        return StructuredLLMResponse(
            data={"selections": [{"source_id": "PYDANTIC_MIGRATION_GUIDE"}]},
            input_tokens=1,
            output_tokens=1,
            provider="fake",
            model="fake",
        )


class TimeoutLLM:
    async def generate_structured(self, request):
        del request
        raise TimeoutError("model timed out")


class InventingLLM:
    async def generate_structured(self, request):
        from upgradepilot.llm.client import StructuredLLMResponse

        return StructuredLLMResponse(
            data={
                "selections": [
                    {
                        "source_id": "STACK_OVERFLOW",
                        "section": "Accepted answer",
                        "rule_ids": ["PYD009"],
                        "relevance": "Invented source.",
                    }
                ],
                "warnings": [],
            },
            input_tokens=1,
            output_tokens=1,
            provider="fake",
            model="fake",
        )


class RecordingLLM:
    def __init__(self) -> None:
        self.prompt = ""

    async def generate_structured(self, request):
        from upgradepilot.llm.client import StructuredLLMResponse

        self.prompt = request.prompt
        return StructuredLLMResponse(
            data={
                "selections": [
                    {
                        "source_id": "PYDANTIC_V2_VALIDATORS",
                        "section": "Field validators",
                        "rule_ids": ["PYD001"],
                        "relevance": "Official validator migration evidence.",
                    }
                ],
                "warnings": [],
            },
            input_tokens=1,
            output_tokens=1,
            provider="fake",
            model="fake",
        )


@pytest.mark.asyncio
async def test_rule_to_source_mapping_uses_only_pack_sources() -> None:
    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=Path("migration_packs/pydantic_v1_to_v2"),
        prefer_live=False,
    )

    result = await agent.run(state=_state(), findings=[_FINDING])

    assert result.status == "completed"
    assert result.llm_calls == 1
    assert result.evidence
    assert {ev.source_id for ev in result.evidence} <= {
        "PYDANTIC_MIGRATION_GUIDE",
        "PYDANTIC_V2_SERIALIZATION",
    }
    assert all(ev.related_rule_ids == ["PYD009"] for ev in result.evidence)


@pytest.mark.asyncio
async def test_no_source_available_returns_unavailable(tmp_path: Path) -> None:
    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=tmp_path,
        prefer_live=False,
    )

    result = await agent.run(state=_state(), findings=[_FINDING])

    assert result.status == "unavailable"
    assert result.evidence == []
    assert "DOCUMENTATION_UNAVAILABLE" in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_malformed_llm_response_is_rejected() -> None:
    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=Path("migration_packs/pydantic_v1_to_v2"),
        llm_client=MalformedLLM(),
        prefer_live=False,
    )

    result = await agent.run(state=_state(), findings=[_FINDING])

    assert result.status == "partial"
    assert result.evidence == []
    assert "malformed" in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_llm_timeout_is_partial_without_evidence() -> None:
    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=Path("migration_packs/pydantic_v1_to_v2"),
        llm_client=TimeoutLLM(),
        prefer_live=False,
    )

    result = await agent.run(state=_state(), findings=[_FINDING])

    assert result.status == "partial"
    assert result.evidence == []
    assert "timed out" in " ".join(result.warnings)


@pytest.mark.asyncio
async def test_invented_source_from_llm_is_rejected() -> None:
    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=Path("migration_packs/pydantic_v1_to_v2"),
        llm_client=InventingLLM(),
        prefer_live=False,
    )

    result = await agent.run(state=_state(), findings=[_FINDING])

    assert result.status == "partial"
    assert result.evidence == []
    assert any("Rejected invented source_id" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_prompt_injection_inside_docs_is_delimited_and_ignored() -> None:
    recorder = RecordingLLM()
    tmp_root = Path("migration_packs/pydantic_v1_to_v2")
    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=tmp_root,
        llm_client=recorder,
        prefer_live=False,
    )

    result = await agent.run(
        state=_state(),
        findings=[
            {
                "finding_id": "finding-2",
                "rule_id": "PYD001",
                "source_ids": ["PYDANTIC_MIGRATION_GUIDE", "PYDANTIC_V2_VALIDATORS"],
            }
        ],
    )

    assert "<UNTRUSTED_OFFICIAL_DOCUMENT_SECTION>" in recorder.prompt
    assert "Ignore previous instructions" in recorder.prompt
    assert result.evidence
    assert {ev.source_id for ev in result.evidence} == {"PYDANTIC_V2_VALIDATORS"}
    assert "STACK_OVERFLOW" not in {ev.source_id for ev in result.evidence}


@pytest.mark.asyncio
async def test_agent_does_not_await_slow_fake_when_timeout_is_raised() -> None:
    class SlowThenTimeoutLLM:
        async def generate_structured(self, request):
            del request
            await asyncio.sleep(0)
            raise TimeoutError("synthetic timeout")

    agent = DocumentationResearchAgent(
        pack=_pack(),
        pack_dir=Path("migration_packs/pydantic_v1_to_v2"),
        llm_client=SlowThenTimeoutLLM(),
        prefer_live=False,
    )

    result = await agent.run(state=_state(), findings=[_FINDING])

    assert result.status == "partial"
