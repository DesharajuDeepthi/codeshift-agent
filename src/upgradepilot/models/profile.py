"""
RepositoryProfile, DependencyEvidence, and related models for M2.

All paths are repository-relative POSIX strings.
All models are frozen (immutable) after construction.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constraint classification
# ---------------------------------------------------------------------------


class ConstraintKind(StrEnum):
    EXACT = "exact"
    BOUNDED = "bounded"
    RANGE = "range"
    UNPINNED = "unpinned"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class VersionConstraint(BaseModel):
    """Parsed version specifier from a manifest entry."""

    model_config = {"frozen": True}

    raw: str
    kind: ConstraintKind
    lower: str | None = None
    upper: str | None = None


# ---------------------------------------------------------------------------
# Dependency evidence
# ---------------------------------------------------------------------------


class DependencyEvidence(BaseModel):
    """A single dependency entry found in a manifest file."""

    model_config = {"frozen": True}

    package: str
    normalized_name: str
    constraint: VersionConstraint
    manifest_path: str
    line: int
    parser: str
    parser_version: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


# ---------------------------------------------------------------------------
# Test and CI signals
# ---------------------------------------------------------------------------


class TestingFramework(StrEnum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    UNKNOWN = "unknown"


class CISystem(StrEnum):
    GITHUB_ACTIONS = "github_actions"
    TOX = "tox"
    NOX = "nox"
    UNKNOWN = "unknown"


class TestProfile(BaseModel):
    model_config = {"frozen": True}

    test_files: list[str] = Field(default_factory=list)
    frameworks: list[TestingFramework] = Field(default_factory=list)
    ci_systems: list[CISystem] = Field(default_factory=list)
    ci_files: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pydantic-specific applicability signals
# ---------------------------------------------------------------------------


class PydanticSignal(StrEnum):
    V1_DETECTED = "v1_detected"
    V2_DETECTED = "v2_detected"
    UNPINNED = "unpinned"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class ApplicabilitySignals(BaseModel):
    model_config = {"frozen": True}

    pydantic_signal: PydanticSignal = PydanticSignal.NOT_FOUND
    pydantic_evidence: list[DependencyEvidence] = Field(default_factory=list)
    is_python_repo: bool = False
    has_pydantic_imports: bool = False
    python_file_count: int = 0


# ---------------------------------------------------------------------------
# Repository profile
# ---------------------------------------------------------------------------


class ManifestFile(BaseModel):
    model_config = {"frozen": True}

    path: str
    kind: str
    parse_error: str | None = None


class SyntaxError_(BaseModel):
    """Captured syntax error from a Python file (does not crash the analysis)."""

    model_config = {"frozen": True}

    path: str
    line: int | None
    col: int | None
    message: str


class RepositoryProfile(BaseModel):
    """
    Deterministic profile of an extracted repository workspace.
    Produced by the profiler; consumed by applicability checks and agents.
    """

    model_config = {"frozen": True}

    # Python file inventory
    python_files: list[str] = Field(default_factory=list)
    python_file_count: int = 0
    source_roots: list[str] = Field(default_factory=list)

    # Manifest files found
    manifest_files: list[ManifestFile] = Field(default_factory=list)

    # All parsed dependency evidence (all packages)
    all_dependencies: list[DependencyEvidence] = Field(default_factory=list)

    # Pydantic-specific
    pydantic_dependencies: list[DependencyEvidence] = Field(default_factory=list)

    # Runtime declarations (python_requires, .python-version, etc.)
    runtime_declarations: list[str] = Field(default_factory=list)

    # Test/CI
    test_profile: TestProfile = Field(default_factory=TestProfile)

    # Docker/packaging
    docker_files: list[str] = Field(default_factory=list)
    packaging_files: list[str] = Field(default_factory=list)

    # Exclusions and generated paths that were skipped
    excluded_paths: list[str] = Field(default_factory=list)

    # Syntax errors captured without failing the analysis
    syntax_errors: list[SyntaxError_] = Field(default_factory=list)

    # Top-level applicability signals
    applicability: ApplicabilitySignals = Field(default_factory=ApplicabilitySignals)

    # Profiler metadata
    profiler_version: str = "1.0.0"
