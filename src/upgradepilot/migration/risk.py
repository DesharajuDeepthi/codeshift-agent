"""Deterministic risk scoring for migration findings."""

from __future__ import annotations

from pydantic import BaseModel, Field

from upgradepilot.migration.loader import load_all_packs
from upgradepilot.models.finding import MigrationFinding


class RiskComponentResult(BaseModel):
    model_config = {"frozen": True}

    component_id: str
    description: str
    points: int = Field(ge=0)
    supporting_finding_ids: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    model_config = {"frozen": True}

    total_score: int = Field(ge=0)
    level: str
    components: list[RiskComponentResult]
    scoring_model_version: str


def score_risk(
    findings: list[MigrationFinding],
    test_ci: dict[str, object],
    pack_id: str,
) -> RiskAssessment:
    """Score risk deterministically from pack risk rules and repository signals."""
    pack = load_all_packs().get(pack_id)
    components: list[RiskComponentResult] = []
    total = 0
    by_rule: dict[str, list[MigrationFinding]] = {}
    for finding in findings:
        by_rule.setdefault(finding.rule_id, []).append(finding)

    for rule in pack.risk_rules.rules:
        spec = rule.scoring
        points = 0
        supporting: list[str] = []
        source = rule.source
        if rule.rule_ids:
            matched = [finding for rule_id in rule.rule_ids for finding in by_rule.get(rule_id, [])]
            supporting = [finding.finding_id for finding in matched]
            if spec.kind == "count_scaled":
                per = int(getattr(spec, "per_occurrence", 0))
                cap = int(getattr(spec, "cap", per * len(matched)))
                points = min(cap, per * len(matched))
        elif spec.kind == "threshold_step" and source == "finding_file_count":
            file_count = len({finding.file for finding in findings})
            thresholds = getattr(spec, "thresholds", [])
            for threshold in thresholds:
                if file_count > int(threshold.get("above", 0)):
                    points = int(threshold.get("points", 0))
                    break
        elif spec.kind == "boolean":
            value = _boolean_source(source, test_ci)
            if value:
                points = int(getattr(spec, "when_true_points", 0))

        if points > 0:
            components.append(
                RiskComponentResult(
                    component_id=rule.component_id,
                    description=rule.description,
                    points=points,
                    supporting_finding_ids=supporting,
                )
            )
            total += points

    max_points = pack.risk_rules.max_points
    total = min(total, max_points)
    level = "LOW"
    for threshold in sorted(pack.risk_rules.levels, key=lambda item: item.min_points):
        if total >= threshold.min_points:
            level = threshold.level.value

    return RiskAssessment(
        total_score=total,
        level=level.lower(),
        components=components,
        scoring_model_version=pack.risk_rules.scoring_version,
    )


def _boolean_source(source: str | None, test_ci: dict[str, object]) -> bool:
    if source == "no_test_files":
        raw_count = test_ci.get("test_files_count")
        count = raw_count if isinstance(raw_count, int) else 0
        return count == 0
    if source == "no_ci_detected":
        return not bool(test_ci.get("ci_systems") or [])
    return False
