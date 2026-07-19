from __future__ import annotations

import pytest

from upgradepilot.config import Settings
from upgradepilot.llm.client import (
    LLMBudgetExceeded,
    LLMError,
    LLMTask,
    OpenAIChatLLMClient,
    StaticLLMClient,
    StructuredLLMRequest,
)


@pytest.mark.asyncio
async def test_static_llm_client_returns_structured_response() -> None:
    client = StaticLLMClient(outputs={LLMTask.MIGRATION_PLANNING: {"plan": {"x": 1}}})

    response = await client.generate_structured(
        StructuredLLMRequest(
            task=LLMTask.MIGRATION_PLANNING,
            prompt="hello",
            prompt_id="migration_planning",
            prompt_version="1.0.0",
            schema_name="MigrationPlanningLLMOutput",
            token_budget=100,
            timeout_seconds=1,
        )
    )

    assert response.data == {"plan": {"x": 1}}
    assert response.provider == "fake"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_static_llm_client_enforces_prompt_budget() -> None:
    client = StaticLLMClient()

    with pytest.raises(LLMBudgetExceeded):
        await client.generate_structured(
            StructuredLLMRequest(
                task=LLMTask.COMPATIBILITY_INTERPRETATION,
                prompt="x" * 1000,
                prompt_id="compatibility_interpretation",
                prompt_version="1.0.0",
                schema_name="CompatibilityInterpretationLLMOutput",
                token_budget=2,
                timeout_seconds=1,
            )
        )


@pytest.mark.asyncio
async def test_openai_client_without_key_fails_as_degraded_llm() -> None:
    client = OpenAIChatLLMClient(settings=Settings(llm_provider="openai", llm_api_key=None))

    with pytest.raises(LLMError, match="LLM_API_KEY is not configured"):
        await client.generate_structured(
            StructuredLLMRequest(
                task=LLMTask.MIGRATION_PLANNING,
                prompt="{}",
                prompt_id="migration_planning",
                prompt_version="1.0.0",
                schema_name="MigrationPlanningLLMOutput",
                token_budget=100,
                timeout_seconds=1,
            )
        )
