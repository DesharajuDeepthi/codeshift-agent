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
# Applicability signals
#
# PydanticSignal is kept for backward compatibility with the existing
# pydantic-v1-to-v2 pack and its fixture data.  New packs should use the
# ApplicabilityEngine in migration/applicability.py which produces
# SignalResult objects instead.
# ---------------------------------------------------------------------------


class PydanticSignal(StrEnum):
    V1_DETECTED = "v1_detected"
    V2_DETECTED = "v2_detected"
    UNPINNED = "unpinned"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class ApplicabilitySignals(BaseModel):
    """
    Applicability signals for the pydantic-v1-to-v2 pack.

    Deprecated: new packs use migration.applicability.ApplicabilityEngine
    which returns migration.applicability.ApplicabilityAssessment instead.
    This model is retained for backward compatibility.
    """

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

    Multi-language fields (detected_languages, primary_language,
    source_files_by_language) are populated by the language-agnostic profiler
    path and are used by the ApplicabilityEngine.  The legacy Python-specific
    fields (python_files, python_file_count, pydantic_dependencies, applicability)
    are retained for backward compatibility with the existing pydantic-v1-to-v2
    pack and its tests.
    """

    model_config = {"frozen": True}

    # ── Multi-language inventory (new) ────────────────────────────────────
    # Source files grouped by canonical language name.
    # Populated by the repository profiler for all detected languages.
    source_files_by_language: dict[str, list[str]] = Field(default_factory=dict)
    # Ordered list of detected languages, descending by file count.
    detected_languages: list[str] = Field(default_factory=list)
    # Top language by file count, or None for empty repositories.
    primary_language: str | None = None

    # ── Python file inventory (retained for backward compat) ──────────────
    python_files: list[str] = Field(default_factory=list)
    python_file_count: int = 0
    source_roots: list[str] = Field(default_factory=list)

    # Manifest files found
    manifest_files: list[ManifestFile] = Field(default_factory=list)

    # All parsed dependency evidence (all packages, all languages)
    all_dependencies: list[DependencyEvidence] = Field(default_factory=list)

    # Pydantic-specific (retained for backward compat; new packs use all_dependencies)
    pydantic_dependencies: list[DependencyEvidence] = Field(default_factory=list)

    # Runtime declarations (python_requires, .python-version, .nvmrc, go.toolchain, etc.)
    runtime_declarations: list[str] = Field(default_factory=list)

    # Test/CI
    test_profile: TestProfile = Field(default_factory=TestProfile)

    # Docker/packaging
    docker_files: list[str] = Field(default_factory=list)
    packaging_files: list[str] = Field(default_factory=list)

    # Exclusions and generated paths that were skipped
    excluded_paths: list[str] = Field(default_factory=list)

    # Parse/syntax errors captured without failing the analysis
    syntax_errors: list[SyntaxError_] = Field(default_factory=list)

    # Legacy pydantic-specific applicability signals (new packs use ApplicabilityEngine)
    applicability: ApplicabilitySignals = Field(default_factory=ApplicabilitySignals)

    # Profiler metadata
    profiler_version: str = "2.0.0"
