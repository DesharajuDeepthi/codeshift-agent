"""Unit tests for V2 delta detection."""

from __future__ import annotations

from upgradepilot.delta.detector import compute_delta


def _finding(rule_id: str, file_path: str, line: int) -> dict:
    return {
        "rule_id": rule_id,
        "location": {"file_path": file_path, "start_line": line},
        "severity": "HIGH",
    }


PREV = [
    _finding("PYD001", "app/models.py", 18),
    _finding("PYD003", "app/schemas.py", 42),
    _finding("PYD005", "app/models.py", 55),
    _finding("PYD008", "app/config.py", 12),
    _finding("PYD009", "app/validators.py", 7),
    _finding("PYD009", "app/validators.py", 31),
    _finding("PYD011", "app/schemas.py", 89),
]

CURR = [
    # PYD001 fixed, PYD011 fixed
    _finding("PYD003", "app/schemas.py", 42),
    _finding("PYD005", "app/models.py", 55),
    _finding("PYD008", "app/config.py", 12),
    _finding("PYD009", "app/validators.py", 7),
    _finding("PYD009", "app/validators.py", 31),
]


def test_fixed_findings_detected():
    report = compute_delta(PREV, CURR)
    fixed_rules = {f["rule_id"] for f in report.fixed}
    assert "PYD001" in fixed_rules
    assert "PYD011" in fixed_rules
    assert len(report.fixed) == 2


def test_still_open_findings():
    report = compute_delta(PREV, CURR)
    assert len(report.still_open) == 5


def test_no_new_regressions():
    report = compute_delta(PREV, CURR)
    assert report.new == []


def test_new_regression_detected():
    new_finding = _finding("PYD001", "app/new_file.py", 10)
    report = compute_delta(PREV, CURR + [new_finding])
    assert len(report.new) == 1
    assert report.new[0]["rule_id"] == "PYD001"


def test_empty_previous_all_new():
    report = compute_delta([], CURR)
    assert report.fixed == []
    assert report.still_open == []
    assert len(report.new) == len(CURR)


def test_all_fixed():
    report = compute_delta(PREV, [])
    assert len(report.fixed) == len(PREV)
    assert report.new == []
    assert report.still_open == []


def test_summary_string():
    report = compute_delta(PREV, CURR)
    assert "2 fixed" in report.summary
    assert "0 new" in report.summary
    assert "5 still open" in report.summary


def test_commit_shas_recorded():
    report = compute_delta(
        PREV,
        CURR,
        previous_commit_sha="abc123",
        current_commit_sha="def456",
    )
    assert report.previous_commit_sha == "abc123"
    assert report.current_commit_sha == "def456"
