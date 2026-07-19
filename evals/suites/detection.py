"""
Detection evaluation suite — D2.

Metrics:
  rule_precision   = TP / (TP + FP)   per rule, micro-averaged
  rule_recall      = TP / (TP + FN)   per rule, micro-averaged
  exact_file_acc   = findings with correct file / total findings
  exact_line_acc   = findings with correct line / findings with expected lines

Release targets (from spec):
  precision >= 95%
  recall    >= 90%
  valid file references = 100%
  valid line references = 100%
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from evals.datasets.detection_cases import DETECTION_CASES, DetectionCase
from upgradepilot.analyzers.ast_scanner import scan_file
from upgradepilot.migration.loader import load_pack
from upgradepilot.models.finding import MigrationFinding

_ROOT = Path(__file__).parent.parent.parent
PACK_DIR = _ROOT / "migration_packs" / "pydantic_v1_to_v2"
RESULTS_DIR = _ROOT / "eval_results"


@dataclass
class CaseResult:
    case: DetectionCase
    findings: list[MigrationFinding]
    # per-case booleans
    precision_ok: bool
    recall_ok: bool
    line_ok: bool  # True if no expected_lines violations


@dataclass
class DetectionSuiteResult:
    case_results: list[CaseResult]
    micro_precision: float
    micro_recall: float
    exact_file_acc: float
    exact_line_acc: float
    elapsed_s: float

    @property
    def passed(self) -> bool:
        return (
            self.micro_precision >= 0.95
            and self.micro_recall >= 0.90
            and self.exact_file_acc >= 1.0
        )

    def print_report(self) -> None:
        _print_report(self)


def _evaluate_case(case: DetectionCase, pack) -> tuple[CaseResult, dict[str, int]]:
    """
    Returns (CaseResult, per-rule TP/FP/FN counts as side effect of counters).

    Precision / recall are computed externally across all cases.
    """
    src = case.fixture_path.read_text(encoding="utf-8")
    rel = case.fixture_path.name
    findings, _ = scan_file(src, rel, pack)
    found_rule_ids = {f.rule_id for f in findings}

    # Recall: expected rules that fired
    precision_ok = not (found_rule_ids & case.forbidden_rule_ids)
    recall_ok = case.expected_rule_ids.issubset(found_rule_ids)

    # Line accuracy
    line_ok = True
    for rule_id, expected_line in case.expected_lines.items():
        matches = [f for f in findings if f.rule_id == rule_id]
        if not any(f.line_start == expected_line for f in matches):
            line_ok = False

    return CaseResult(
        case=case,
        findings=findings,
        precision_ok=precision_ok,
        recall_ok=recall_ok,
        line_ok=line_ok,
    )


def _compute_metrics(
    case_results: list[CaseResult],
) -> tuple[float, float, float, float]:
    """Returns (precision, recall, file_acc, line_acc)."""
    tp_total = 0
    fp_total = 0
    fn_total = 0
    line_correct = 0
    line_total = 0
    file_correct = 0
    file_total = 0

    for cr in case_results:
        found = {f.rule_id for f in cr.findings}
        expected = cr.case.expected_rule_ids
        forbidden = cr.case.forbidden_rule_ids

        # TP: found rules that were expected
        tp = len(found & expected)
        # FP: found rules that were forbidden
        fp = len(found & forbidden)
        # FN: expected rules that were not found
        fn = len(expected - found)

        tp_total += tp
        fp_total += fp
        fn_total += fn

        # File accuracy: all findings should reference the correct file
        for f in cr.findings:
            file_total += 1
            if f.file == cr.case.fixture_path.name:
                file_correct += 1

        # Line accuracy
        for rule_id, expected_line in cr.case.expected_lines.items():
            matches = [f for f in cr.findings if f.rule_id == rule_id]
            line_total += 1
            if any(f.line_start == expected_line for f in matches):
                line_correct += 1

    precision = tp_total / max(1, tp_total + fp_total)
    recall = tp_total / max(1, tp_total + fn_total)
    file_acc = file_correct / max(1, file_total)
    line_acc = line_correct / max(1, line_total) if line_total else 1.0

    return precision, recall, file_acc, line_acc


def _print_report(result: DetectionSuiteResult) -> None:
    sep = "─" * 78
    print(f"\n{'=' * 78}")
    print("  UpgradePilot — Detection Evaluation Suite (D2)")
    print(f"{'=' * 78}")
    print(f"  Cases:    {len(result.case_results)}")
    print(f"  Elapsed:  {result.elapsed_s:.2f}s")
    print()

    # Per-case table
    header = f"{'Case':<30} {'Prec':>6} {'Rec':>6} {'Line':>6} {'Findings':>8}"
    print(header)
    print(sep)
    for cr in result.case_results:
        prec = "✓" if cr.precision_ok else "✗"
        rec = "✓" if cr.recall_ok else "✗"
        line = "✓" if cr.line_ok else "✗"
        cnt = len(cr.findings)
        print(f"  {cr.case.name:<28} {prec:>6} {rec:>6} {line:>6} {cnt:>8}")
    print(sep)

    # Aggregate metrics
    print(f"\n  Micro-precision:  {result.micro_precision * 100:.1f}%  (target ≥ 95%)")
    print(f"  Micro-recall:     {result.micro_recall * 100:.1f}%  (target ≥ 90%)")
    print(f"  File accuracy:    {result.exact_file_acc * 100:.1f}%  (target = 100%)")
    print(f"  Line accuracy:    {result.exact_line_acc * 100:.1f}%")
    print()

    status = "PASS" if result.passed else "FAIL"
    print(f"  Result:  {status}")
    print(f"{'=' * 78}\n")


def run_detection_suite(backend: str = "local") -> DetectionSuiteResult:
    pack = load_pack(PACK_DIR)
    t0 = time.monotonic()
    case_results = [_evaluate_case(c, pack) for c in DETECTION_CASES]
    elapsed = time.monotonic() - t0
    precision, recall, file_acc, line_acc = _compute_metrics(case_results)

    result = DetectionSuiteResult(
        case_results=case_results,
        micro_precision=precision,
        micro_recall=recall,
        exact_file_acc=file_acc,
        exact_line_acc=line_acc,
        elapsed_s=elapsed,
    )

    # Write JSON result
    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "suite": "detection",
        "backend": backend,
        "micro_precision": precision,
        "micro_recall": recall,
        "exact_file_acc": file_acc,
        "exact_line_acc": line_acc,
        "elapsed_s": elapsed,
        "passed": result.passed,
        "cases": [
            {
                "name": cr.case.name,
                "precision_ok": cr.precision_ok,
                "recall_ok": cr.recall_ok,
                "line_ok": cr.line_ok,
                "findings": len(cr.findings),
            }
            for cr in case_results
        ],
    }
    (RESULTS_DIR / "latest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    return result
