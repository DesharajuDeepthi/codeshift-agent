"""Provider-neutral structured-output LLM client."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from upgradepilot.config import Settings, get_settings


class LLMTask(StrEnum):
    DOCUMENTATION_RESEARCH = "documentation_research"
    COMPATIBILITY_INTERPRETATION = "compatibility_interpretation"
    MIGRATION_PLANNING = "migration_planning"
    EVIDENCE_CRITIC = "evidence_critic"


class LLMError(RuntimeError):
    """Base error for structured LLM calls."""


class LLMBudgetExceeded(LLMError):
    """Raised before a call when prompt or output budgets are exceeded."""


class LLMTimeout(LLMError):
    """Raised when a provider call exceeds the configured timeout."""


class StructuredLLMRequest(BaseModel):
    """Provider-neutral structured generation request."""

    model_config = {"frozen": True}

    task: LLMTask
    prompt: str
    prompt_id: str
    prompt_version: str
    schema_name: str
    token_budget: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    max_output_chars: int = Field(gt=0, default=24_000)


class StructuredLLMResponse(BaseModel):
    """Provider-neutral structured generation response."""

    model_config = {"frozen": True}

    data: dict[str, Any]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0, default=0.0)
    retry_count: int = Field(ge=0, default=0)
    latency_ms: float = Field(ge=0.0, default=0.0)
    provider: str
    model: str


class LLMClient(Protocol):
    """Single structured-output interface used by all agents."""

    async def generate_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        """Generate schema-shaped JSON data for one bounded agent call."""


class StaticLLMClient:
    """Fake/test LLM client that returns precomputed structured data."""

    def __init__(
        self,
        *,
        outputs: Mapping[LLMTask, Mapping[str, Any]] | None = None,
        raise_for: Mapping[LLMTask, Exception] | None = None,
        provider: str = "fake",
        model: str = "fake-structured",
    ) -> None:
        self._outputs = dict(outputs or {})
        self._raise_for = dict(raise_for or {})
        self.provider = provider
        self.model = model
        self.calls: list[StructuredLLMRequest] = []

    async def generate_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        self.calls.append(request)
        if _estimate_tokens(request.prompt) > request.token_budget:
            raise LLMBudgetExceeded("prompt exceeds token budget")
        if len(request.prompt) > request.max_output_chars * 4:
            raise LLMBudgetExceeded("prompt exceeds output safety budget")
        exc = self._raise_for.get(request.task)
        if exc is not None:
            raise exc
        data = dict(self._outputs.get(request.task, {}))
        output_text = json.dumps(data, sort_keys=True, default=str)
        if len(output_text) > request.max_output_chars:
            raise LLMBudgetExceeded("structured output exceeds max_output_chars")
        return StructuredLLMResponse(
            data=data,
            input_tokens=_estimate_tokens(request.prompt),
            output_tokens=_estimate_tokens(output_text),
            provider=self.provider,
            model=self.model,
        )


class OpenAIChatLLMClient:
    """Minimal OpenAI-compatible structured JSON client using httpx."""

    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        if _estimate_tokens(request.prompt) > request.token_budget:
            raise LLMBudgetExceeded("prompt exceeds token budget")
        api_key = (
            self._settings.llm_api_key.get_secret_value()
            if self._settings.llm_api_key is not None
            else None
        )
        if not api_key:
            raise LLMError("LLM_API_KEY is not configured")
        started = time.perf_counter()
        payload = {
            "model": self._settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only a JSON object matching the requested schema. "
                        "Do not include markdown fences."
                    ),
                },
                {"role": "user", "content": request.prompt},
            ],
            "temperature": 0,
            "max_tokens": min(self._settings.llm_max_tokens, request.token_budget),
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(request.timeout_seconds)) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise LLMTimeout("LLM provider timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM provider error: {type(exc).__name__}") from exc

        raw = response.json()
        content = raw["choices"][0]["message"]["content"]
        if len(content) > request.max_output_chars:
            raise LLMBudgetExceeded("structured output exceeds max_output_chars")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM provider returned non-JSON content") from exc
        usage = raw.get("usage") or {}
        return StructuredLLMResponse(
            data=data,
            input_tokens=int(usage.get("prompt_tokens") or _estimate_tokens(request.prompt)),
            output_tokens=int(usage.get("completion_tokens") or _estimate_tokens(content)),
            estimated_cost_usd=0.0,
            retry_count=0,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            provider=self._settings.llm_provider,
            model=self._settings.llm_model,
        )


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Return the configured provider-neutral client."""
    cfg = settings or get_settings()
    if cfg.llm_provider.lower() == "openai":
        return OpenAIChatLLMClient(settings=cfg)
    return OpenAIChatLLMClient(settings=cfg)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
