"""Typed documentation evidence produced by the research agent."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class DocumentationResearchStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class SourceRetrievalStatus(StrEnum):
    LIVE = "live"
    CACHED_SNAPSHOT = "cached_snapshot"
    UNAVAILABLE = "unavailable"


class NormalizedDocumentSection(BaseModel):
    """One normalized, bounded section from an official documentation source."""

    model_config = {"frozen": True}

    source_id: str
    title: str
    canonical_url: str
    section: str
    text: str
    content_hash: str
    retrieved_at: datetime
    retrieval_ms: Annotated[float, Field(ge=0.0)]
    retrieval_status: SourceRetrievalStatus
    cache_hit: bool
    snapshot_version: str
    freshness_disclosure: str

    @field_validator("text")
    @classmethod
    def text_is_bounded(cls, value: str) -> str:
        lines = value.splitlines()
        if len(lines) > 20:
            raise ValueError("normalized section text must be bounded to <= 20 lines")
        if len(value) > 4000:
            raise ValueError("normalized section text must be bounded to <= 4000 chars")
        return value


class DocumentationEvidence(BaseModel):
    """Report-safe official documentation evidence."""

    model_config = {"frozen": True}

    evidence_id: str
    source_id: str
    title: str
    canonical_url: str
    retrieved_at: datetime
    content_hash: str
    section: str
    bounded_excerpt: str
    related_rule_ids: list[str]
    retrieval_ms: Annotated[float, Field(ge=0.0)]
    cache_status: SourceRetrievalStatus
    source_freshness: str
    relevance: str

    @field_validator("bounded_excerpt")
    @classmethod
    def excerpt_is_bounded(cls, value: str) -> str:
        lines = value.splitlines()
        if len(lines) > 20:
            raise ValueError("bounded_excerpt must contain <= 20 lines")
        if len(value) > 3000:
            raise ValueError("bounded_excerpt must contain <= 3000 chars")
        return value


class DocumentationResearchResult(BaseModel):
    """Typed output boundary for the Documentation Research Agent."""

    model_config = {"frozen": True}

    status: DocumentationResearchStatus
    evidence: list[DocumentationEvidence] = Field(default_factory=list)
    unavailable_source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    related_rule_ids: list[str] = Field(default_factory=list)
    prompt_id: str = "documentation_research"
    prompt_version: str
    llm_calls: Annotated[int, Field(ge=0, le=1)] = 0
    token_budget: Annotated[int, Field(gt=0)]
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    estimated_cost_usd: Annotated[float, Field(ge=0.0)] = 0.0
    retrieval_ms: Annotated[float, Field(ge=0.0)] = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
