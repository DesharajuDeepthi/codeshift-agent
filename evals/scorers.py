"""
Scorer functions for UpgradePilot LLM evals.

Each scorer takes (run_output, expected_output) and returns a score 0.0–1.0
plus a reason string. LangSmith displays these per-example in the eval report.

Scorers are deliberately deterministic — no LLM judge — so eval results are
reproducible and cheap to run.
"""

from __future__ import annotations

from typing import Any


def score_applicability(
    output: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Does the pipeline correctly identify whether the repo needs migration?"""
    got = (output.get("applicability_status") or "").upper()
    want = (expected.get("expected_applicability") or "").upper()
    if not want:
        return {"key": "applicability", "score": 1.0, "comment": "no expectation set"}
    correct = got == want
    return {
        "key": "applicability",
        "score": 1.0 if correct else 0.0,
        "comment": f"got={got!r} want={want!r}",
    }


def score_finding_count(
    output: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Did we surface at least the expected minimum number of findings?"""
    findings = output.get("findings") or []
    got = len(findings)
    minimum = int(expected.get("min_finding_count") or 0)
    score = 1.0 if got >= minimum else got / max(minimum, 1)
    return {
        "key": "finding_count",
        "score": round(score, 3),
        "comment": f"got={got} min={minimum}",
    }


def score_risk_score(
    output: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Is the risk score at or above the expected minimum?"""
    risk = output.get("risk_assessment") or {}
    got = float(risk.get("overall_score") or risk.get("score") or 0.0)
    minimum = float(expected.get("min_risk_score") or 0.0)
    if minimum == 0.0:
        return {"key": "risk_score", "score": 1.0, "comment": "no minimum set"}
    score = 1.0 if got >= minimum else got / minimum
    return {
        "key": "risk_score",
        "score": round(score, 3),
        "comment": f"got={got:.3f} min={minimum:.3f}",
    }


def score_plan_keywords(
    output: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Does the migration plan mention all required keywords?"""
    keywords: list[str] = expected.get("plan_must_mention") or []
    if not keywords:
        return {"key": "plan_keywords", "score": 1.0, "comment": "no keywords required"}

    # Look in plan_draft claims + migration phases text
    plan = output.get("plan_draft") or {}
    plan_text = str(plan).lower()
    report = output.get("report") or {}
    plan_text += str(report.get("migration_phases") or "").lower()
    plan_text += str(report.get("recommendations") or "").lower()

    found = [kw for kw in keywords if kw.lower() in plan_text]
    score = len(found) / len(keywords)
    missing = [kw for kw in keywords if kw not in found]
    comment = f"found={found} missing={missing}"
    return {"key": "plan_keywords", "score": round(score, 3), "comment": comment}


def score_interpretation_coverage(
    output: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Did the LLM interpret at least the expected number of findings?"""
    minimum = int(expected.get("min_interpreted_findings") or 0)
    if minimum == 0:
        return {"key": "interpretation_coverage", "score": 1.0, "comment": "none required"}

    interp = output.get("compatibility_interpretation") or {}
    claims = interp.get("claims") or []
    got = len([c for c in claims if c.get("claim_text")])
    score = 1.0 if got >= minimum else got / minimum
    return {
        "key": "interpretation_coverage",
        "score": round(score, 3),
        "comment": f"got={got} min={minimum}",
    }


def score_no_hallucination(
    output: dict[str, Any],
    _expected: dict[str, Any],
) -> dict[str, Any]:
    """
    Did the evidence validator pass without critical failures?

    Checks that the pipeline didn't hallucinate finding IDs or line numbers
    that don't exist in the repo. Uses the deterministic validation results
    already computed by the pipeline.
    """
    issues = output.get("validation_issues") or []
    critical = [i for i in issues if i.get("severity") == "error"]
    total = len(issues)
    errors = len(critical)

    if total == 0:
        return {"key": "no_hallucination", "score": 1.0, "comment": "no validation issues"}

    score = 1.0 - (errors / total)
    return {
        "key": "no_hallucination",
        "score": round(score, 3),
        "comment": f"errors={errors} warnings={total - errors}",
    }


# All scorers in order — run_evals.py iterates this list
ALL_SCORERS = [
    score_applicability,
    score_finding_count,
    score_risk_score,
    score_plan_keywords,
    score_interpretation_coverage,
    score_no_hallucination,
]
