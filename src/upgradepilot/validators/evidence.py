"""Deterministic evidence validation for migration plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from upgradepilot.migration.loader import load_all_packs
from upgradepilot.migration.models import RiskRulesConfig
from upgradepilot.models.agent_outputs import MigrationPlanDraft

_VERSION_CLAIM_RE = re.compile(r"\bpydantic\s*(?:==|>=|<=|~=|>|<|=)?\s*(\d+(?:\.\d+){0,2})", re.I)
_PACKAGE_VERSION_RE = re.compile(r"\b(?:upgrade|pin|set|use)\s+pydantic[^\n]*\d", re.I)
_UNCITED_RECOMMENDATION_RE = re.compile(r"\b(should|replace|migrate|use|update|review)\b", re.I)
_EXECUTION_RE = re.compile(
    r"\b(tests?\s+(passed|ran|succeeded|were run)|code\s+(was\s+)?(changed|modified|updated))\b",
    re.I,
)
_DEFINITIVE_RE = re.compile(r"\b(will\s+definitely|guaranteed|safe\s+to\s+deploy)\b", re.I)
_EXACT_HOURS_RE = re.compile(r"\b\d+(\.\d+)?\s*(hours?|hrs?)\b", re.I)


@dataclass(frozen=True)
class ValidationContext:
    plan_draft: dict[str, Any]
    profile: dict[str, Any]
    findings: list[dict[str, Any]]
    documentation_evidence: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    risk_assessment: dict[str, Any]
    pack_id: str


class ValidationIssue(BaseModel):
    """JSON-safe issue emitted by deterministic evidence validators."""

    model_config = {"frozen": True}

    validator_id: str
    severity: Literal["error", "warning"]
    message: str = Field(max_length=1000)
    claim_id: str | None = None
    evidence_id: str | None = None
    repairable: bool


def make_issue(
    validator_id: str,
    severity: Literal["error", "warning"],
    message: str,
    repairable: bool,
    *,
    claim_id: str | None = None,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    return ValidationIssue(
        validator_id=validator_id,
        severity=severity,
        message=message,
        claim_id=claim_id,
        evidence_id=evidence_id,
        repairable=repairable,
    ).model_dump(mode="json")


def validate_plan_evidence(context: ValidationContext) -> list[dict[str, Any]]:
    """Validate plan claims against immutable deterministic evidence."""
    issues: list[dict[str, Any]] = []
    plan = context.plan_draft
    try:
        MigrationPlanDraft.model_validate(plan)
    except ValidationError as exc:
        issues.append(
            make_issue(
                "V-SCHEMA",
                "error",
                f"Plan schema or maximum length validation failed: {exc.errors()[0]['msg']}",
                repairable=True,
            )
        )

    try:
        pack = load_all_packs().get(context.pack_id)
    except Exception as exc:
        issues.append(
            make_issue(
                "V-PACK",
                "error",
                f"Migration pack is unavailable or unsupported: {type(exc).__name__}",
                repairable=False,
            )
        )
        return issues

    known_rule_ids = pack.known_rule_ids()
    known_sources = {source.source_id: source for source in pack.trusted_sources.sources}
    allowed_domains = set(pack.trusted_sources.allowed_domains)
    finding_by_id = {
        str(finding.get("finding_id")): finding
        for finding in context.findings
        if finding.get("finding_id")
    }
    doc_by_id = {
        str(doc.get("evidence_id")): doc
        for doc in context.documentation_evidence
        if doc.get("evidence_id")
    }
    python_files = set(context.profile.get("python_files") or [])
    known_files = python_files | {str(finding.get("file")) for finding in context.findings}
    dependency_versions = _known_dependency_versions(context.dependencies)

    issues.extend(_validate_plan_file_worklist(plan, known_files))
    for finding_id, finding in finding_by_id.items():
        issues.extend(
            _validate_finding(
                finding_id,
                finding,
                pack.metadata.pack_id,
                pack.metadata.version,
                known_rule_ids,
            )
        )
    for evidence_id, doc in doc_by_id.items():
        issues.extend(
            _validate_documentation(
                evidence_id,
                doc,
                known_sources,
                allowed_domains,
            )
        )
    issues.extend(_validate_risk(context.risk_assessment, finding_by_id, pack.risk_rules))

    for claim in plan.get("claims") or []:
        claim_id = str(claim.get("claim_id") or "")
        text = str(claim.get("text") or "")
        finding_ids = [str(value) for value in claim.get("finding_ids") or []]
        doc_ids = [str(value) for value in claim.get("documentation_evidence_ids") or []]
        repo_ids = [str(value) for value in claim.get("repository_evidence_ids") or []]

        issues.extend(
            _validate_claim_refs(
                claim_id,
                finding_ids,
                doc_ids,
                repo_ids,
                finding_by_id,
                doc_by_id,
            )
        )
        issues.extend(
            _validate_claim_language(
                claim_id,
                text,
                bool(finding_ids and doc_ids),
                dependency_versions,
            )
        )
        issues.extend(
            _validate_claim_evidence_coverage(
                claim_id,
                text,
                finding_ids,
                doc_ids,
                finding_by_id,
                doc_by_id,
            )
        )

    return issues


def _validate_plan_file_worklist(
    plan: dict[str, Any], known_files: set[str]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for entry in plan.get("file_worklist") or []:
        path = entry.get("path") if isinstance(entry, dict) else entry
        if path and known_files and path not in known_files:
            issues.append(
                make_issue(
                    "V-FILE-REF",
                    "error",
                    f"File worklist entry not found in repository evidence: {path!r}",
                    repairable=False,
                )
            )
    return issues


def _validate_finding(
    finding_id: str,
    finding: dict[str, Any],
    pack_id: str,
    pack_version: str,
    known_rule_ids: frozenset[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if finding.get("pack_id") != pack_id or finding.get("pack_version") != pack_version:
        issues.append(
            make_issue(
                "V-PACK",
                "error",
                f"Finding {finding_id} has unexpected migration-pack ID/version.",
                repairable=False,
            )
        )
    if finding.get("rule_id") not in known_rule_ids:
        issues.append(
            make_issue(
                "V-RULE",
                "error",
                f"Finding {finding_id} references unknown rule_id.",
                repairable=False,
            )
        )
    start = finding.get("line_start")
    end = finding.get("line_end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        issues.append(
            make_issue(
                "V-LINE-RANGE",
                "error",
                f"Finding {finding_id} has an invalid line range.",
                repairable=False,
            )
        )
    evidence = str(finding.get("evidence") or "")
    if not evidence.strip() or len(evidence.splitlines()) > 8:
        issues.append(
            make_issue(
                "V-SNIPPET",
                "error",
                f"Finding {finding_id} has missing or unbounded evidence snippet.",
                repairable=False,
            )
        )
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        expected_lines = end - start + 1
        actual_lines = len(evidence.splitlines()) if evidence.strip() else 0
        if actual_lines != expected_lines:
            issues.append(
                make_issue(
                    "V-LINE-RANGE",
                    "error",
                    f"Finding {finding_id} evidence snippet does not match line range.",
                    repairable=False,
                )
            )
    symbol = str(finding.get("symbol") or "")
    if symbol and symbol not in evidence:
        issues.append(
            make_issue(
                "V-SNIPPET",
                "error",
                f"Finding {finding_id} evidence snippet does not contain detected symbol.",
                repairable=False,
            )
        )
    return issues


def _validate_documentation(
    evidence_id: str,
    doc: dict[str, Any],
    known_sources: dict[str, Any],
    allowed_domains: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    source_id = str(doc.get("source_id") or "")
    source = known_sources.get(source_id)
    if source is None:
        issues.append(
            make_issue(
                "V-SOURCE",
                "error",
                f"Documentation evidence {evidence_id} references non-allowlisted source.",
                repairable=False,
                evidence_id=evidence_id,
            )
        )
    else:
        canonical_url = str(doc.get("canonical_url") or "")
        parsed_domain = urlparse(canonical_url).netloc.lower()
        if canonical_url != source.canonical_url or parsed_domain not in allowed_domains:
            issues.append(
                make_issue(
                    "V-SOURCE",
                    "error",
                    f"Documentation evidence {evidence_id} has non-canonical source URL.",
                    repairable=False,
                    evidence_id=evidence_id,
                )
            )
    excerpt = str(doc.get("bounded_excerpt") or "")
    if not excerpt.strip() or len(excerpt.splitlines()) > 20:
        issues.append(
            make_issue(
                "V-SNIPPET",
                "error",
                f"Documentation evidence {evidence_id} has missing or unbounded excerpt.",
                repairable=False,
                evidence_id=evidence_id,
            )
        )
    return issues


def _validate_risk(
    risk: dict[str, Any],
    finding_by_id: dict[str, dict[str, Any]],
    risk_rules: RiskRulesConfig,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    total = risk.get("total_score")
    component_sum = sum(
        int(component.get("points") or 0) for component in risk.get("components") or []
    )
    if isinstance(total, int) and component_sum > total:
        issues.append(
            make_issue(
                "V-RISK",
                "error",
                "Risk component points exceed deterministic total score.",
                repairable=False,
            )
        )
    if isinstance(total, int) and total > risk_rules.max_points:
        issues.append(
            make_issue(
                "V-RISK",
                "error",
                "Risk total exceeds migration-pack scoring maximum.",
                repairable=False,
            )
        )
    if risk.get("scoring_model_version") != risk_rules.scoring_version:
        issues.append(
            make_issue(
                "V-RISK",
                "error",
                "Risk score uses an unexpected scoring model version.",
                repairable=False,
            )
        )
    for component in risk.get("components") or []:
        for finding_id in component.get("supporting_finding_ids") or []:
            if finding_id and finding_id not in finding_by_id:
                issues.append(
                    make_issue(
                        "V-RISK",
                        "error",
                        f"Risk component references unknown finding_id: {finding_id!r}",
                        repairable=False,
                    )
                )
    return issues


def _validate_claim_refs(
    claim_id: str,
    finding_ids: list[str],
    doc_ids: list[str],
    repo_ids: list[str],
    finding_by_id: dict[str, dict[str, Any]],
    doc_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not finding_ids:
        issues.append(
            make_issue(
                "V-FINDING-REF",
                "error",
                "Claim must cite at least one finding ID.",
                False,
                claim_id=claim_id,
            )
        )
    if not doc_ids:
        issues.append(
            make_issue(
                "V-EVIDENCE",
                "error",
                "Claim must cite at least one documentation evidence ID.",
                False,
                claim_id=claim_id,
            )
        )
    for finding_id in finding_ids:
        if finding_id not in finding_by_id:
            issues.append(
                make_issue(
                    "V-FINDING-REF",
                    "error",
                    f"Claim references unknown finding_id: {finding_id!r}",
                    False,
                    claim_id=claim_id,
                )
            )
    for evidence_id in doc_ids:
        if evidence_id not in doc_by_id:
            issues.append(
                make_issue(
                    "V-EVIDENCE",
                    "error",
                    f"Claim references unknown documentation evidence_id: {evidence_id!r}",
                    False,
                    claim_id=claim_id,
                    evidence_id=evidence_id,
                )
            )
    for repo_id in repo_ids:
        if repo_id not in finding_by_id:
            issues.append(
                make_issue(
                    "V-REPOSITORY-EVIDENCE",
                    "error",
                    f"Claim references unknown repository evidence ID: {repo_id!r}",
                    False,
                    claim_id=claim_id,
                )
            )
    return issues


def _validate_claim_language(
    claim_id: str,
    text: str,
    has_core_citations: bool,
    dependency_versions: set[str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if _EXECUTION_RE.search(text):
        issues.append(
            make_issue(
                "V-PROHIBITED-CLAIM",
                "error",
                "Claim says code or tests were executed.",
                False,
                claim_id=claim_id,
            )
        )
    if _EXACT_HOURS_RE.search(text):
        issues.append(
            make_issue(
                "V-PROHIBITED-CLAIM",
                "error",
                "Claim includes an exact work-hour estimate.",
                False,
                claim_id=claim_id,
            )
        )
    if _DEFINITIVE_RE.search(text):
        issues.append(
            make_issue(
                "V-PROHIBITED-CLAIM",
                "error",
                "Claim overstates certainty.",
                True,
                claim_id=claim_id,
            )
        )
    if _UNCITED_RECOMMENDATION_RE.search(text) and not has_core_citations:
        issues.append(
            make_issue(
                "V-EVIDENCE-COVERAGE",
                "warning",
                "Recommendation lacks required citations.",
                True,
                claim_id=claim_id,
            )
        )
    if _PACKAGE_VERSION_RE.search(text):
        claimed_versions = set(_VERSION_CLAIM_RE.findall(text))
        if claimed_versions and claimed_versions.isdisjoint(dependency_versions):
            issues.append(
                make_issue(
                    "V-VERSION",
                    "error",
                    "Claim cites an unsupported Pydantic package version.",
                    False,
                    claim_id=claim_id,
                )
            )
    return issues


def _validate_claim_evidence_coverage(
    claim_id: str,
    text: str,
    finding_ids: list[str],
    doc_ids: list[str],
    finding_by_id: dict[str, dict[str, Any]],
    doc_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    lower_text = text.lower()
    for finding_id in finding_ids:
        finding = finding_by_id.get(finding_id)
        if not finding:
            continue
        symbol = str(finding.get("symbol") or "").strip().lower()
        rule_id = str(finding.get("rule_id") or "").strip().lower()
        if symbol and symbol not in lower_text and rule_id and rule_id not in lower_text:
            issues.append(
                make_issue(
                    "V-GROUNDING",
                    "warning",
                    "Claim does not mention the cited finding symbol or rule.",
                    True,
                    claim_id=claim_id,
                )
            )
    for evidence_id in doc_ids:
        doc = doc_by_id.get(evidence_id)
        if not doc:
            continue
        related_rules = set(doc.get("related_rule_ids") or [])
        finding_rules = {
            str(finding_by_id[fid].get("rule_id")) for fid in finding_ids if fid in finding_by_id
        }
        if related_rules and finding_rules and related_rules.isdisjoint(finding_rules):
            issues.append(
                make_issue(
                    "V-EVIDENCE-COVERAGE",
                    "warning",
                    "Claim cites documentation unrelated to the finding rule.",
                    True,
                    claim_id=claim_id,
                    evidence_id=evidence_id,
                )
            )
    return issues


def _known_dependency_versions(dependencies: list[dict[str, Any]]) -> set[str]:
    versions: set[str] = set()
    for dependency in dependencies:
        if (
            str(dependency.get("normalized_name") or dependency.get("package") or "").lower()
            != "pydantic"
        ):
            continue
        constraint = dependency.get("constraint") or {}
        if isinstance(constraint, dict):
            raw = str(constraint.get("raw") or "")
            versions.update(_VERSION_CLAIM_RE.findall(f"pydantic {raw}"))
    return versions
