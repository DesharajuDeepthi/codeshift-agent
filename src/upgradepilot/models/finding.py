"""
MigrationFinding — the atomic unit produced by the compatibility scanner.

Every finding carries stable rule metadata, exact source location,
a bounded evidence excerpt, and a confidence score.  Nothing here
is Pydantic-pack-specific; the scanner is pack-agnostic.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class MatchKind(StrEnum):
    AST = "ast"
    TEXT = "text"


class MigrationFinding(BaseModel):
    """One detected Pydantic v1 pattern in a source file."""

    model_config = {"frozen": True}

    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str
    pack_id: str
    pack_version: str
    category: str
    severity: str

    # Location — all paths are repository-relative, normalized to forward slashes
    file: str
    line_start: Annotated[int, Field(ge=1)]
    line_end: Annotated[int, Field(ge=1)]

    # Evidence — bounded to ≤ 8 lines; never the full file
    evidence: str
    symbol: str

    # Migration guidance
    migration_concept: str
    source_ids: list[str]

    # Provenance
    detector: str
    detector_version: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    match_kind: MatchKind


class ScanResult(BaseModel):
    """Aggregate output from scanning a workspace."""

    model_config = {"frozen": True}

    findings: list[MigrationFinding]
    scanned_files: int
    files_with_findings: int
    syntax_error_files: list[str]
    detector: str
    detector_version: str

    def by_rule(self) -> dict[str, list[MigrationFinding]]:
        result: dict[str, list[MigrationFinding]] = {}
        for f in self.findings:
            result.setdefault(f.rule_id, []).append(f)
        return result

    def langsmith_metadata(self) -> dict[str, str | int]:
        return {
            "detector": self.detector,
            "detector_version": self.detector_version,
            "scanned_files": self.scanned_files,
            "total_findings": len(self.findings),
            "syntax_error_files": len(self.syntax_error_files),
        }
