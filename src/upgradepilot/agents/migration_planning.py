"""Migration Planning Agent."""

from __future__ import annotations

import json
from collections.abc import Mapping
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
    ClaimType,
    FileWorkItem,
    MigrationPhase,
    MigrationPlanDraft,
    MigrationPlanningResult,
    PlanClaim,
)
from upgradepilot.observability.tracing import (
    LLMUsage,
    begin_child_run,
    end_child_run,
    record_llm_trace,
)

_AGENT_NAME = "migration_planning"
_PROMPT_ID = "migration_planning"
_MAX_LLM_CALLS = 1


class MigrationPlanningLLMOutput(BaseModel):
    model_config = {"frozen": True}

    plan: MigrationPlanDraft
    warnings: list[str] = Field(default_factory=list)


class MigrationPlanningAgent:
    """Generate an evidence-linked read-only migration plan."""

    def __init__(self, *, pack: LoadedMigrationPack, llm_client: LLMClient | None = None) -> None:
        self._pack = pack
        self._llm_client = llm_client

    async def run(self, *, state: Mapping[str, Any]) -> MigrationPlanningResult:
        prompt = self._pack.get_prompt(_PROMPT_ID)
        if prompt is None:
            raise ValueError("migration_planning prompt is missing from migration pack")
        token_budget = min(prompt.max_tokens, get_settings().llm_max_tokens)
        findings = list(state.get("findings") or [])
        docs = list(state.get("documentation_evidence") or [])
        risk = dict(state.get("risk_assessment") or {})
        interpretation = state.get("interpretation") or {}
        known_finding_ids = {str(f["finding_id"]) for f in findings if f.get("finding_id")}
        known_doc_ids = {str(ev["evidence_id"]) for ev in docs if ev.get("evidence_id")}
        default_output = _default_output(findings, docs, risk)
        llm = self._llm_client or StaticLLMClient(
            outputs={LLMTask.MIGRATION_PLANNING: default_output.model_dump()}
        )
        tool_outputs = _run_allowed_tools(state, findings, docs, risk)
        prompt_text = _render_prompt(
            prompt,
            findings=findings,
            docs=docs,
            risk=risk,
            interpretation=interpretation,
            tool_outputs=tool_outputs,
        )
        input_tokens = _estimate_tokens(prompt_text)
        try:
            raw = await llm.generate_structured(
                StructuredLLMRequest(
                    task=LLMTask.MIGRATION_PLANNING,
                    prompt=prompt_text,
                    prompt_id=prompt.prompt_id,
                    prompt_version=prompt.version,
                    schema_name="MigrationPlanningLLMOutput",
                    token_budget=token_budget,
                    timeout_seconds=get_settings().llm_timeout_seconds,
                )
            )
            output = MigrationPlanningLLMOutput.model_validate(raw.data)
            _validate_plan_refs(output.plan, known_finding_ids, known_doc_ids)
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
                    "provider": raw.provider,
                    "model": raw.model,
                },
            )
            return MigrationPlanningResult(
                status=AgentOutputStatus.COMPLETED,
                plan=output.plan,
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
            return MigrationPlanningResult(
                status=AgentOutputStatus.PARTIAL,
                plan=_fallback_plan(findings, docs),
                warnings=[f"LLM_UNAVAILABLE: migration planning {status}."],
                prompt_version=prompt.version,
                llm_calls=1,
                token_budget=token_budget,
                input_tokens=input_tokens,
            )


def _run_allowed_tools(
    state: Mapping[str, Any],
    findings: list[Mapping[str, Any]],
    docs: list[Mapping[str, Any]],
    risk: Mapping[str, Any],
) -> dict[str, Any]:
    tools = {
        "tool.verified_finding_lookup": {"finding_ids": [f.get("finding_id") for f in findings]},
        "tool.evidence_lookup": {"evidence_ids": [ev.get("evidence_id") for ev in docs]},
        "tool.risk_score_lookup": risk,
        "tool.plan_template": {
            "sections": [
                "executive_summary",
                "impact_summary",
                "phases",
                "file_worklist",
                "dependency_actions",
                "testing_checklist",
                "rollout_checklist",
                "rollback_checklist",
                "claims",
            ]
        },
    }
    for name, output in tools.items():
        handle = begin_child_run(
            state,
            name=name,
            category="tool",
            run_type="tool",
            inputs={"agent": _AGENT_NAME},
            metadata={"allowed_tool": name.removeprefix("tool.")},
        )
        end_child_run(state, handle, outputs=dict(output))
    return tools


def _render_prompt(
    prompt: PromptTemplate,
    *,
    findings: list[Mapping[str, Any]],
    docs: list[Mapping[str, Any]],
    risk: Mapping[str, Any],
    interpretation: object,
    tool_outputs: Mapping[str, Any],
) -> str:
    inputs = {
        "verified_findings": findings,
        "documentation_evidence": docs,
        "compatibility_interpretation": interpretation,
        "deterministic_risk_assessment": risk,
        "allowed_tools_used": tool_outputs,
        "forbidden_claims": [
            "tests passed",
            "code was changed",
            "migration will definitely succeed",
            "exact work-hour estimates",
            "uncited package versions",
        ],
        "constraints": {
            "max_llm_calls": _MAX_LLM_CALLS,
            "read_only_recommendations": True,
            "cite_known_findings_and_evidence_only": True,
        },
    }
    return (
        prompt.body.replace("{risk_score}", str(risk.get("total_score", 0)))
        .replace("{risk_level}", str(risk.get("level", "unknown")))
        .replace("{inputs_json}", json.dumps(inputs, sort_keys=True, default=str))
    )


def _default_output(
    findings: list[Mapping[str, Any]],
    docs: list[Mapping[str, Any]],
    risk: Mapping[str, Any],
) -> MigrationPlanningLLMOutput:
    plan = _fallback_plan(findings, docs)
    return MigrationPlanningLLMOutput(
        plan=plan.model_copy(
            update={
                "executive_summary": (
                    f"Static analysis found {len(findings)} Pydantic migration finding(s). "
                    f"Deterministic risk is {risk.get('total_score', 0)} "
                    f"({risk.get('level', 'unknown')})."
                )
            }
        ),
        warnings=[],
    )


def _fallback_plan(
    findings: list[Mapping[str, Any]],
    docs: list[Mapping[str, Any]],
) -> MigrationPlanDraft:
    doc_id = str(docs[0]["evidence_id"]) if docs else ""
    claims: list[PlanClaim] = []
    files: dict[str, list[str]] = {}
    for finding in findings:
        finding_id = str(finding.get("finding_id"))
        files.setdefault(str(finding.get("file")), []).append(finding_id)
        if doc_id:
            claims.append(
                PlanClaim(
                    text=(
                        f"Finding {finding.get('rule_id')} at {finding.get('file')} should be "
                        "reviewed against the cited Pydantic v2 migration evidence."
                    ),
                    claim_type=ClaimType.ACTION,
                    finding_ids=[finding_id],
                    documentation_evidence_ids=[doc_id],
                    repository_evidence_ids=[finding_id],
                    confidence=float(finding.get("confidence") or 0.7),
                )
            )
    return MigrationPlanDraft(
        executive_summary="Static analysis produced a read-only migration plan draft.",
        impact_summary=["Pydantic v1 API usage requires review against v2 migration evidence."],
        phases=[
            MigrationPhase(
                name="Review and migrate detected Pydantic API usage",
                description="Address findings in small groups while preserving current behavior.",
                file_paths=sorted(files),
                finding_ids=[str(f.get("finding_id")) for f in findings if f.get("finding_id")],
            )
        ],
        file_worklist=[
            FileWorkItem(path=path, findings_count=len(ids), priority="high")
            for path, ids in sorted(files.items())
        ],
        dependency_actions=["Review Pydantic dependency constraints before upgrading to v2."],
        testing_checklist=[
            (
                "Add or update targeted tests for affected model validation "
                "and serialization behavior."
            ),
            "Compare key model dump, validation, and schema outputs before and after migration.",
        ],
        rollout_checklist=[
            "Review generated recommendations with a maintainer before applying changes."
        ],
        rollback_checklist=[
            "Keep the prior dependency constraint available for rollback planning."
        ],
        assumptions=["[ASSUMPTION] Findings correspond to reachable code paths."],
        gaps=[] if docs else ["[GAP] No documentation evidence was available."],
        human_review_points=["Review dynamic validation or serialization behavior manually."],
        claims=claims,
    )


def _validate_plan_refs(
    plan: MigrationPlanDraft,
    known_finding_ids: set[str],
    known_doc_ids: set[str],
) -> None:
    for phase in plan.phases:
        unknown = set(phase.finding_ids) - known_finding_ids
        if unknown:
            raise ValueError(f"phase references unknown finding_ids: {sorted(unknown)}")
    for claim in plan.claims:
        unknown_findings = set(claim.finding_ids) - known_finding_ids
        unknown_docs = set(claim.documentation_evidence_ids) - known_doc_ids
        if unknown_findings:
            raise ValueError(f"claim references unknown finding_ids: {sorted(unknown_findings)}")
        if unknown_docs:
            raise ValueError(f"claim references unknown evidence_ids: {sorted(unknown_docs)}")
        if not claim.finding_ids or not claim.documentation_evidence_ids:
            raise ValueError("plan claim must cite at least one finding and documentation evidence")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
