"""Compare two local evaluation result artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.common import RESULTS_DIR

HARD_METRICS = {
    "hard_failure_count",
    "valid_file_references",
    "valid_line_references",
    "valid_source_references",
    "prohibited_claim_count",
    "unsupported_claim_count",
    "correct_graph_routing",
    "graceful_chaos_handling",
    "schema_valid_agent_outputs",
    "call_budget_compliance",
}

HIGHER_IS_BETTER = {
    "valid_file_references",
    "valid_line_references",
    "valid_source_references",
    "correct_graph_routing",
    "graceful_chaos_handling",
    "schema_valid_agent_outputs",
    "call_budget_compliance",
}

LOWER_IS_BETTER = {
    "hard_failure_count",
    "prohibited_claim_count",
    "unsupported_claim_count",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare UpgradePilot evaluation runs")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()

    comparison = compare_results(args.baseline, args.candidate)
    _write_comparison(comparison)
    _print_comparison(comparison)
    sys.exit(0 if comparison["passed"] else 1)


def compare_results(baseline_name: str, candidate_name: str) -> dict[str, Any]:
    baseline = _load_result(baseline_name)
    candidate = _load_result(candidate_name)
    deltas: dict[str, dict[str, float | int | bool | str | None]] = {}
    regressions: list[str] = []
    baseline_metrics = baseline.get("aggregate_metrics") or {}
    candidate_metrics = candidate.get("aggregate_metrics") or {}
    for metric in sorted(HARD_METRICS):
        before = baseline_metrics.get(metric)
        after = candidate_metrics.get(metric)
        delta = _numeric_delta(before, after)
        deltas[metric] = {"baseline": before, "candidate": after, "delta": delta}
        if metric in HIGHER_IS_BETTER and delta is not None and delta < 0:
            regressions.append(metric)
        if metric in LOWER_IS_BETTER and delta is not None and delta > 0:
            regressions.append(metric)
    return {
        "baseline": baseline_name,
        "candidate": candidate_name,
        "created_at": datetime.now(UTC).isoformat(),
        "passed": not regressions,
        "hard_metric_regressions": regressions,
        "deltas": deltas,
        "semantic_note": "Semantic metrics are tracked for review and do not override hard gates.",
    }


def _load_result(name: str) -> dict[str, Any]:
    path = _resolve_result_path(name)
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_result_path(name: str) -> Path:
    if name == "latest":
        return RESULTS_DIR / "latest.json"
    direct = Path(name)
    if direct.exists():
        return direct
    candidate = RESULTS_DIR / "cases" / f"{name}.json"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"evaluation result not found: {name}")


def _numeric_delta(before: object, after: object) -> float | int | None:
    if isinstance(before, bool) or isinstance(after, bool):
        return None
    if isinstance(before, int | float) and isinstance(after, int | float):
        return after - before
    return None


def _write_comparison(comparison: dict[str, Any]) -> None:
    comparisons_dir = RESULTS_DIR / "comparisons"
    comparisons_dir.mkdir(parents=True, exist_ok=True)
    name = f"{comparison['baseline']}_vs_{comparison['candidate']}".replace("/", "_")
    (comparisons_dir / f"{name}.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    lines = [
        f"# Evaluation Comparison: {comparison['baseline']} vs {comparison['candidate']}",
        "",
        f"- Passed: `{comparison['passed']}`",
        f"- Hard metric regressions: {', '.join(comparison['hard_metric_regressions']) or 'none'}",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric, delta in comparison["deltas"].items():
        lines.append(
            f"| {metric} | {delta['baseline']} | {delta['candidate']} | {delta['delta']} |"
        )
    lines.append("")
    (comparisons_dir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def _print_comparison(comparison: dict[str, Any]) -> None:
    print(json.dumps(comparison, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
