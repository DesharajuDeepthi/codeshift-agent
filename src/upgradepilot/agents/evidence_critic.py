"""Evidence Critic Agent for single repair pass."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from upgradepilot.config import get_settings
from upgradepilot.llm.client import (
    LLMBudgetExceeded,
    LLMClient,
    LLMTask,
    LLMTimeout,
    StaticLLMClient,
    StructuredLLMRequest,
)
from upgradepilot.migration.models import LoadedMigrationPack, PromptTemplate
from upgradepilot.models.agent_outputs import (
    AgentOutputStatus,
    EvidenceCriticResult,
    EvidenceRepairInstruction,
)
from upgradepilot.observability.tracing import (
    LLMUsage,
    begin_child_run,
    end_child_run,
    record_llm_trace,
)

_AGENT_NAME = "evidence_critic"
_PROMPT_ID = "evidence_critic"
_MAX_LLM_CALLS = 1


class EvidenceCriticLLMOutput(BaseModel):
    model_config = {"frozen": True}

    repairs: list[EvidenceRepairInstruction] = Field(default_factory=list)
    approved_claim_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class EvidenceCriticAgent:
    """Repair generated-language grounding failures without changing evidence."""

    def __init__(self, *, pack: LoadedMigrationPack, llm_client: LLMClient | None = None) -> None:
        self._pack = pack
        self._llm_client = llm_client

    async def run(self, *, state: Mapping[str, Any]) -> EvidenceCriticResult:
        prompt = self._pack.get_prompt(_PROMPT_ID)
        if prompt is None:
            raise ValueError("evidence_critic prompt is missing from migration pack")
        token_budget = min(prompt.max_tokens, get_settings().llm_max_tokens)
        failed_claims = _failed_repairable_claims(state)
        if not failed_claims:
            return EvidenceCriticResult(
                status=AgentOutputStatus.UNAVAILABLE,
                warnings=["No repairable failed claims were available for critique."],
                prompt_version=prompt.version,
                token_budget=token_budget,
            )

        default_output = _default_output(failed_claims, state)
        llm = self._llm_client or StaticLLMClient(
            outputs={LLMTask.EVIDENCE_CRITIC: default_output.model_dump()}
        )
        evidence = _evidence_lookup(state, failed_claims)
        prompt_text = _render_prompt(prompt, failed_claims=failed_claims, evidence=evidence)
        input_tokens = _estimate_tokens(prompt_text)
        try:
            raw = await llm.generate_structured(
                StructuredLLMRequest(
                    task=LLMTask.EVIDENCE_CRITIC,
                    prompt=prompt_text,
                    prompt_id=prompt.prompt_id,
                    prompt_version=prompt.version,
                    schema_name="EvidenceCriticLLMOutput",
                    token_budget=token_budget,
                    timeout_seconds=get_settings().llm_timeout_seconds,
                )
            )
            output = EvidenceCriticLLMOutput.model_validate(raw.data)
            _validate_repairs(output.repairs, failed_claims)
            record_llm_trace(
                state,
                agent=_AGENT_NAME,
                status="completed",
                usage=LLMUsage(
                    input_tokens=raw.input_tokens,
                    output_tokens=raw.output_tokens,
                    estimated_cost_usd=raw.estimated_cost_usd,
                    retry_count=raw.retry_count,
                ),
                metadata={
                    "prompt_id": prompt.prompt_id,
                    "prompt_version": prompt.version,
                    "max_llm_calls": _MAX_LLM_CALLS,
                    "repairable_claim_count": len(failed_claims),
                    "provider": raw.provider,
                    "model": raw.model,
                },
            )
            return EvidenceCriticResult(
                status=AgentOutputStatus.COMPLETED,
                repairs=output.repairs,
                approved_claim_ids=output.approved_claim_ids,
                summary=output.summary,
                warnings=output.warnings,
                prompt_version=prompt.version,
                llm_calls=1,
                token_budget=token_budget,
                input_tokens=raw.input_tokens,
                output_tokens=raw.output_tokens,
                estimated_cost_usd=raw.estimated_cost_usd,
            )
        except (ValidationError, ValueError, LLMBudgetExceeded, LLMTimeout, TimeoutError) as exc:
            status = "timeout" if isinstance(exc, (LLMTimeout, TimeoutError)) else "malformed"
            if isinstance(exc, LLMBudgetExceeded):
                status = "budget_exceeded"
            record_llm_trace(
                state,
                agent=_AGENT_NAME,
                status=status,
                usage=LLMUsage(input_tokens=input_tokens),
                metadata={"prompt_id": prompt.prompt_id, "prompt_version": prompt.version},
            )
            return EvidenceCriticResult(
                status=AgentOutputStatus.PARTIAL,
                warnings=[f"LLM_UNAVAILABLE: evidence critic {status}."],
                prompt_version=prompt.version,
                llm_calls=1,
                token_budget=token_budget,
                input_tokens=input_tokens,
            )


def _failed_repairable_claims(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    repairable_claim_ids = {
        issue.get("claim_id")
        for issue in state.get("validation_issues") or []
        if issue.get("repairable") and issue.get("claim_id")
    }
    claims = list((state.get("plan_draft") or {}).get("claims") or [])
    return [claim for claim in claims if claim.get("claim_id") in repairable_claim_ids]


def _evidence_lookup(
    state: Mapping[str, Any], failed_claims: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    finding_ids = {
        finding_id for claim in failed_claims for finding_id in (claim.get("finding_ids") or [])
    }
    doc_ids = {
        doc_id
        for claim in failed_claims
        for doc_id in (claim.get("documentation_evidence_ids") or [])
    }
    findings = [
        finding
        for finding in state.get("findings") or []
        if finding.get("finding_id") in finding_ids
    ]
    docs = [
        doc
        for doc in state.get("documentation_evidence") or []
        if doc.get("evidence_id") in doc_ids
    ]
    handle = begin_child_run(
        state,
        name="tool.evidence_lookup",
        category="tool",
        run_type="tool",
        inputs={"agent": _AGENT_NAME, "claim_count": len(failed_claims)},
        metadata={"allowed_tool": "evidence lookup"},
    )
    output = {"findings": findings, "documentation_evidence": docs}
    end_child_run(state, handle, outputs=output)
    return output


def _render_prompt(
    prompt: PromptTemplate,
    *,
    failed_claims: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
) -> str:
    inputs = {
        "failed_claims": failed_claims,
        "existing_evidence_only": evidence,
        "constraints": {
            "cannot_add_findings_or_evidence": True,
            "cannot_override_deterministic_failures": True,
            "repair_claim_text_only": True,
            "max_llm_calls": _MAX_LLM_CALLS,
        },
    }
    return prompt.body.replace("{inputs_json}", json.dumps(inputs, sort_keys=True, default=str))


def _default_output(
    failed_claims: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
) -> EvidenceCriticLLMOutput:
    findings = {finding.get("finding_id"): finding for finding in state.get("findings") or []}
    docs = {doc.get("evidence_id"): doc for doc in state.get("documentation_evidence") or []}
    repairs: list[EvidenceRepairInstruction] = []
    for claim in failed_claims:
        finding_ids = [str(value) for value in claim.get("finding_ids") or []]
        doc_ids = [str(value) for value in claim.get("documentation_evidence_ids") or []]
        first_finding = findings.get(finding_ids[0]) if finding_ids else None
        first_doc = docs.get(doc_ids[0]) if doc_ids else None
        if first_finding is None or first_doc is None:
            continue
        repairs.append(
            EvidenceRepairInstruction(
                claim_id=str(claim.get("claim_id")),
                replacement_text=(
                    f"Finding {first_finding.get('rule_id')} at {first_finding.get('file')} "
                    "requires human review against documentation evidence "
                    f"{first_doc.get('evidence_id')}."
                ),
                keep_finding_ids=finding_ids,
                keep_documentation_evidence_ids=doc_ids,
                rationale="Ground the claim in the cited rule and documentation evidence.",
            )
        )
    return EvidenceCriticLLMOutput(
        repairs=repairs,
        approved_claim_ids=[],
        summary=f"Prepared {len(repairs)} repair instruction(s).",
    )


def _validate_repairs(
    repairs: list[EvidenceRepairInstruction],
    failed_claims: Sequence[Mapping[str, Any]],
) -> None:
    failed_by_id = {claim.get("claim_id"): claim for claim in failed_claims}
    for repair in repairs:
        claim = failed_by_id.get(repair.claim_id)
        if claim is None:
            raise ValueError(f"repair references unknown claim_id: {repair.claim_id}")
        if set(repair.keep_finding_ids) - set(claim.get("finding_ids") or []):
            raise ValueError("repair attempted to add finding IDs")
        if set(repair.keep_documentation_evidence_ids) - set(
            claim.get("documentation_evidence_ids") or []
        ):
            raise ValueError("repair attempted to add documentation evidence IDs")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
