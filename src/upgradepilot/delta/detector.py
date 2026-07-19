"""
Delta detection between two analysis runs on the same repository.

Compares findings by (rule_id, file_path, start_line) — fully deterministic,
no LLM involved. Produces fixed, new, and still-open finding sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FindingKey:
    rule_id: str
    file_path: str
    start_line: int | None


@dataclass
class DeltaReport:
    fixed: list[dict[str, Any]]
    new: list[dict[str, Any]]
    still_open: list[dict[str, Any]]
    previous_commit_sha: str | None
    current_commit_sha: str | None

    @property
    def summary(self) -> str:
        return (
            f"{len(self.fixed)} fixed, "
            f"{len(self.new)} new, "
            f"{len(self.still_open)} still open"
        )


def _key(finding: dict[str, Any]) -> FindingKey:
    location = finding.get("location") or {}
    return FindingKey(
        rule_id=finding.get("rule_id", ""),
        file_path=location.get("file_path") or finding.get("file_path", ""),
        start_line=location.get("start_line") or finding.get("line_number"),
    )


def compute_delta(
    previous_findings: list[dict[str, Any]],
    current_findings: list[dict[str, Any]],
    previous_commit_sha: str | None = None,
    current_commit_sha: str | None = None,
) -> DeltaReport:
    """
    Compare two findings lists and return what was fixed, what is new,
    and what is still open.

    Both lists are plain dicts as returned by Finding.model_dump().
    """
    prev_keys = {_key(f): f for f in previous_findings}
    curr_keys = {_key(f): f for f in current_findings}

    fixed = [prev_keys[k] for k in prev_keys if k not in curr_keys]
    new = [curr_keys[k] for k in curr_keys if k not in prev_keys]
    still_open = [curr_keys[k] for k in curr_keys if k in prev_keys]

    return DeltaReport(
        fixed=fixed,
        new=new,
        still_open=still_open,
        previous_commit_sha=previous_commit_sha,
        current_commit_sha=current_commit_sha,
    )
