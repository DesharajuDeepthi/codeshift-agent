"""LLM-backed agent graph nodes."""

from __future__ import annotations

from typing import Any

from upgradepilot.graph.nodes._helpers import _now, graph_error, node_error_record, node_record
from upgradepilot.graph.state import UpgradePilotState
from upgradepilot.migration.loader import load_all_packs
from upgradepilot.models.agent_outputs import EvidenceRepairInstruction

# ---------------------------------------------------------------------------
# compatibility_interpretation  (placeholder)
# ---------------------------------------------------------------------------

_NODE_INTERP = "compatibility_interpretation"


async def compatibility_interpretation(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    pack_id = str(state.get("pack_id") or state.get("request_data", {}).get("migration_pack") or "")
    try:
        from upgradepilot.agents.compatibility_interpretation import (
            CompatibilityInterpretationAgent,
        )

        pack = load_all_packs().get(pack_id)
        result = await CompatibilityInterpretationAgent(pack=pack).run(state=state)
        return {
            "interpretation": result.model_dump(mode="json"),
            "node_executions": [node_record(_NODE_INTERP, started)],
            "warnings": result.warnings,
        }
    except Exception as exc:
        return {
            "interpretation": None,
            "node_executions": [node_error_record(_NODE_INTERP, started, "LLM_UNAVAILABLE")],
            "errors": [graph_error(_NODE_INTERP, "LLM_UNAVAILABLE", str(exc))],
        }


# ---------------------------------------------------------------------------
# migration_planning  (placeholder)
# ---------------------------------------------------------------------------

_NODE_PLAN = "migration_planning"


async def migration_planning(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    pack_id = str(state.get("pack_id") or state.get("request_data", {}).get("migration_pack") or "")
    try:
        from upgradepilot.agents.migration_planning import MigrationPlanningAgent

        pack = load_all_packs().get(pack_id)
        result = await MigrationPlanningAgent(pack=pack).run(state=state)
        plan = result.plan.model_dump(mode="json") if result.plan is not None else None
        return {
            "plan_draft": plan,
            "node_executions": [node_record(_NODE_PLAN, started)],
            "warnings": result.warnings,
        }
    except Exception as exc:
        return {
            "plan_draft": None,
            "node_executions": [node_error_record(_NODE_PLAN, started, "LLM_UNAVAILABLE")],
            "errors": [graph_error(_NODE_PLAN, "LLM_UNAVAILABLE", str(exc))],
        }


# ---------------------------------------------------------------------------
# evidence_critic  (placeholder)
# ---------------------------------------------------------------------------

_NODE_CRITIC = "evidence_critic"


async def evidence_critic(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    pack_id = str(state.get("pack_id") or state.get("request_data", {}).get("migration_pack") or "")
    try:
        from upgradepilot.agents.evidence_critic import EvidenceCriticAgent

        pack = load_all_packs().get(pack_id)
        result = await EvidenceCriticAgent(pack=pack).run(state=state)
        repair_instructions = [repair.model_dump(mode="json") for repair in result.repairs]
        return {
            "evidence_critic_result": result.model_dump(mode="json"),
            "repair_instructions": repair_instructions,
            "node_executions": [node_record(_NODE_CRITIC, started)],
            "warnings": result.warnings,
        }
    except Exception as exc:
        return {
            "evidence_critic_result": None,
            "repair_instructions": [],
            "node_executions": [node_error_record(_NODE_CRITIC, started, "LLM_UNAVAILABLE")],
            "errors": [graph_error(_NODE_CRITIC, "LLM_UNAVAILABLE", str(exc))],
        }


# ---------------------------------------------------------------------------
# repair_plan  (placeholder)
# ---------------------------------------------------------------------------

_NODE_REPAIR = "repair_plan"


async def repair_plan(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()
    current = state.get("repair_count", 0)
    repaired_plan, warnings = _apply_repair_instructions(
        state.get("plan_draft") or {},
        state.get("repair_instructions") or [],
    )
    return {
        "repair_count": current + 1,
        "plan_draft": repaired_plan,
        "node_executions": [node_record(_NODE_REPAIR, started)],
        "warnings": warnings,
    }


def _apply_repair_instructions(
    plan_draft: dict[str, Any],
    raw_instructions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Apply critic repairs without adding or rewriting evidence."""
    plan = dict(plan_draft)
    claims = [dict(claim) for claim in plan.get("claims") or []]
    claim_by_id = {str(claim.get("claim_id")): claim for claim in claims}
    warnings: list[str] = []

    for raw in raw_instructions:
        try:
            instruction = EvidenceRepairInstruction.model_validate(raw)
        except Exception:
            warnings.append("REPAIR_SKIPPED: malformed repair instruction.")
            continue

        claim = claim_by_id.get(instruction.claim_id)
        if claim is None:
            warnings.append(f"REPAIR_SKIPPED: unknown claim_id {instruction.claim_id!r}.")
            continue

        original_finding_ids = [str(value) for value in claim.get("finding_ids") or []]
        original_doc_ids = [str(value) for value in claim.get("documentation_evidence_ids") or []]
        keep_finding_ids = instruction.keep_finding_ids or original_finding_ids
        keep_doc_ids = instruction.keep_documentation_evidence_ids or original_doc_ids
        claim["text"] = instruction.replacement_text
        claim["finding_ids"] = [
            finding_id for finding_id in original_finding_ids if finding_id in keep_finding_ids
        ]
        claim["documentation_evidence_ids"] = [
            evidence_id for evidence_id in original_doc_ids if evidence_id in keep_doc_ids
        ]

    plan["claims"] = claims
    return plan, warnings
