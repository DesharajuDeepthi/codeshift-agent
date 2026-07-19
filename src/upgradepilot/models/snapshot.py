"""RepositorySnapshot — immutable record of an acquired repository."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class SafetyLimitsApplied(BaseModel):
    """Record of which safety limits were checked during acquisition."""

    max_compressed_bytes: int
    max_extracted_bytes: int
    max_file_count: int
    max_path_depth: int
    max_single_file_bytes: int

    actual_compressed_bytes: int = 0
    actual_extracted_bytes: int = 0
    actual_file_count: int = 0
    actual_max_depth: int = 0


class RepositorySnapshot(BaseModel):
    """Immutable record of a safely acquired repository snapshot."""

    model_config = {"frozen": True}

    owner: str
    repo: str
    requested_ref: str
    resolved_commit_sha: str
    archive_sha256: str
    # Workspace path as string; Path objects are not JSON-serialisable
    workspace_path: str
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    safety_limits: SafetyLimitsApplied

    @property
    def workspace(self) -> Path:
        return Path(self.workspace_path)

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    @property
    def short_sha(self) -> str:
        return self.resolved_commit_sha[:12]
