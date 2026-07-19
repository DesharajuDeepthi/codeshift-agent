"""Typed outputs for compatibility interpretation and planning agents."""

from __future__ import annotations

import re
import uuid
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

_FORBIDDEN_CLAIM_PATTERNS = (
    re.compile(r"\btests?\s+(passed|ran|succeeded|were run)\b", re.IGNORECASE),
    re.compile(r"\bcode\s+(was\s+)?(changed|modified|updated|fixed)\b", re.IGNORECASE),
    re.compile(r"\bwill\s+definitely\s+succeed\b", re.IGNORECASE),
    re.compile(r"\b\d+(\.\d+)?\s*(hours?|hrs?)\b", re.IGNORECASE),
)


class AgentOutputStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ClaimType(StrEnum):
    IMPACT = "impact"
    ACTION = "action"
    RISK = "risk"
    TESTING = "testing"
    ROLLOUT = "rollout"
    ROLLBACK = "rollback"
    GAP = "gap"


class CompatibilityInterpretationEntry(BaseModel):
    model_config = {"frozen": True}

    finding_id: str
    impact_summary: str = Field(max_length=800)
    migration_steps: list[str] = Field(default_factory=list, max_length=8)
    caveats: list[str] = Field(default_factory=list, max_length=8)
    documentation_ids: list[str] = Field(default_factory=list)
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    assumptions: list[str] = Field(default_factory=list, max_length=8)


class CompatibilityInterpretationResult(BaseModel):
    model_config = {"frozen": True}

    status: AgentOutputStatus
    interpretations: list[CompatibilityInterpretationEntry] = Field(default_factory=list)
    summary: str = Field(default="", max_length=2000)
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    prompt_id: str = "compatibility_interpretation"
    prompt_version: str
    llm_calls: Annotated[int, Field(ge=0, le=1)] = 0
    token_budget: Annotated[int, Field(gt=0)]
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    estimated_cost_usd: Annotated[float, Field(ge=0.0)] = 0.0


class MigrationPhase(BaseModel):
    model_config = {"frozen": True}

    name: str = Field(max_length=120)
    description: str = Field(max_length=1000)
    file_paths: list[str] = Field(default_factory=list, max_length=100)
    finding_ids: list[str] = Field(default_factory=list, max_length=200)


class FileWorkItem(BaseModel):
    model_config = {"frozen": True}

    path: str
    findings_count: Annotated[int, Field(ge=0)]
    priority: str


class PlanClaim(BaseModel):
    model_config = {"frozen": True}

    claim_id: str = Field(default_factory=lambda: f"claim-{uuid.uuid4()}")
    text: str = Field(max_length=1000)
    claim_type: ClaimType
    finding_ids: list[str] = Field(default_factory=list)
    documentation_evidence_ids: list[str] = Field(default_factory=list)
    repository_evidence_ids: list[str] = Field(default_factory=list)
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]

    @field_validator("text")
    @classmethod
    def no_forbidden_claims(cls, value: str) -> str:
        for pattern in _FORBIDDEN_CLAIM_PATTERNS:
            if pattern.search(value):
                raise ValueError("plan claim contains a forbidden assertion")
        return value


class MigrationPlanDraft(BaseModel):
    model_config = {"frozen": True}

    executive_summary: str = Field(max_length=1600)
    impact_summary: list[str] = Field(default_factory=list, max_length=20)
    phases: list[MigrationPhase] = Field(default_factory=list, max_length=12)
    file_worklist: list[FileWorkItem] = Field(default_factory=list, max_length=500)
    dependency_actions: list[str] = Field(default_factory=list, max_length=20)
    testing_checklist: list[str] = Field(default_factory=list, max_length=30)
    rollout_checklist: list[str] = Field(default_factory=list, max_length=30)
    rollback_checklist: list[str] = Field(default_factory=list, max_length=30)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    gaps: list[str] = Field(default_factory=list, max_length=30)
    human_review_points: list[str] = Field(default_factory=list, max_length=30)
    claims: list[PlanClaim] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def no_forbidden_plan_text(self) -> MigrationPlanDraft:
        text_fields = [
            self.executive_summary,
            *self.impact_summary,
            *self.dependency_actions,
            *self.testing_checklist,
            *self.rollout_checklist,
            *self.rollback_checklist,
            *self.assumptions,
            *self.gaps,
            *self.human_review_points,
        ]
        for value in text_fields:
            for pattern in _FORBIDDEN_CLAIM_PATTERNS:
                if pattern.search(value):
                    raise ValueError("migration plan contains a forbidden assertion")
        return self


class MigrationPlanningResult(BaseModel):
    model_config = {"frozen": True}

    status: AgentOutputStatus
    plan: MigrationPlanDraft | None = None
    warnings: list[str] = Field(default_factory=list)
    prompt_id: str = "migration_planning"
    prompt_version: str
    llm_calls: Annotated[int, Field(ge=0, le=1)] = 0
    token_budget: Annotated[int, Field(gt=0)]
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    estimated_cost_usd: Annotated[float, Field(ge=0.0)] = 0.0


class EvidenceRepairInstruction(BaseModel):
    model_config = {"frozen": True}

    claim_id: str
    replacement_text: str = Field(max_length=1000)
    keep_finding_ids: list[str] = Field(default_factory=list)
    keep_documentation_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(max_length=800)

    @field_validator("replacement_text")
    @classmethod
    def replacement_avoids_forbidden_claims(cls, value: str) -> str:
        for pattern in _FORBIDDEN_CLAIM_PATTERNS:
            if pattern.search(value):
                raise ValueError("repair replacement contains a forbidden assertion")
        return value


class EvidenceCriticResult(BaseModel):
    model_config = {"frozen": True}

    status: AgentOutputStatus
    repairs: list[EvidenceRepairInstruction] = Field(default_factory=list, max_length=50)
    approved_claim_ids: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=1000)
    warnings: list[str] = Field(default_factory=list)
    prompt_id: str = "evidence_critic"
    prompt_version: str
    llm_calls: Annotated[int, Field(ge=0, le=1)] = 0
    token_budget: Annotated[int, Field(gt=0)]
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    estimated_cost_usd: Annotated[float, Field(ge=0.0)] = 0.0
