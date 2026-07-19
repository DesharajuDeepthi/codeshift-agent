"""
Schema-validated models for migration-pack YAML files.

All models are frozen after construction.
Loading a pack validates all YAML against these schemas at startup;
a validation failure raises PackSchemaError and prevents startup.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Core enums
# ---------------------------------------------------------------------------


class DetectionRuleCategory(StrEnum):
    VALIDATOR_MIGRATION = "validator_migration"
    CONFIG_MIGRATION = "config_migration"
    SERIALISATION_MIGRATION = "serialisation_migration"
    PARSING_MIGRATION = "parsing_migration"
    SCHEMA_MIGRATION = "schema_migration"
    IMPORT_MIGRATION = "import_migration"
    INTERNAL_API_MIGRATION = "internal_api_migration"
    COMPAT_MIGRATION = "compat_migration"


class RuleSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ValidationSeverity(StrEnum):
    BLOCKING = "BLOCKING"
    REPAIRABLE = "REPAIRABLE"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceKind(StrEnum):
    MIGRATION_GUIDE = "migration_guide"
    CONCEPT_REFERENCE = "concept_reference"
    CHANGELOG = "changelog"
    API_REFERENCE = "api_reference"


# ---------------------------------------------------------------------------
# Pack metadata (pack.yaml)
# ---------------------------------------------------------------------------


class PromptVersions(BaseModel):
    model_config = {"frozen": True}

    documentation_research: str
    compatibility_interpretation: str
    migration_planning: str
    evidence_critic: str


class MigrationPackMetadata(BaseModel):
    """Schema for pack.yaml.  All fields are required unless defaulted."""

    model_config = {"frozen": True}

    pack_id: str
    version: str
    display_name: str
    description: str

    source_package: str
    source_major: int
    target_major: int

    supported_manifest_formats: list[str]
    supported_python_syntax_versions: list[str]

    curated_source_snapshot_version: str
    detector_version: str
    scoring_version: str
    prompt_versions: PromptVersions

    required_files: list[str] = Field(default_factory=list)

    @field_validator("pack_id")
    @classmethod
    def pack_id_format(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"pack_id must be alphanumeric with hyphens/underscores, got {v!r}")
        return v

    @field_validator(
        "version", "curated_source_snapshot_version", "detector_version", "scoring_version"
    )
    @classmethod
    def semver_like(cls, v: str) -> str:
        parts = v.split(".")
        if not (1 <= len(parts) <= 3) or not all(p.isdigit() for p in parts):
            raise ValueError(f"version must be a numeric semver (e.g. 1.0.0), got {v!r}")
        return v


# ---------------------------------------------------------------------------
# Trusted sources (trusted_sources.yaml)
# ---------------------------------------------------------------------------


class TrustedSource(BaseModel):
    model_config = {"frozen": True}

    source_id: str
    title: str
    canonical_url: str
    domain: str
    kind: SourceKind
    curated_snapshot_version: str
    content_hash: str | None = None
    notes: str | None = None


class TrustedSourcesConfig(BaseModel):
    model_config = {"frozen": True}

    version: str
    sources: list[TrustedSource]
    allowed_domains: list[str]

    @field_validator("sources")
    @classmethod
    def no_duplicate_source_ids(cls, v: list[TrustedSource]) -> list[TrustedSource]:
        ids = [s.source_id for s in v]
        if len(ids) != len(set(ids)):
            dupes = {x for x in ids if ids.count(x) > 1}
            raise ValueError(f"Duplicate source_ids: {dupes}")
        return v


# ---------------------------------------------------------------------------
# Detection rules (detection_rules.yaml)
# ---------------------------------------------------------------------------


class MatcherSpec(BaseModel):
    """Flexible matcher specification — exact fields depend on kind."""

    model_config = {"frozen": True, "extra": "allow"}

    kind: str


class DetectionRule(BaseModel):
    model_config = {"frozen": True}

    rule_id: str
    category: DetectionRuleCategory
    severity: RuleSeverity
    rationale: str
    migration_concept: str
    source_ids: list[str]
    risk_points: Annotated[int, Field(ge=0)]
    matcher: MatcherSpec
    confidence_ast: Annotated[float, Field(ge=0.0, le=1.0)]
    confidence_text: Annotated[float, Field(ge=0.0, le=1.0)]
    false_positive_exclusions: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("rule_id")
    @classmethod
    def rule_id_format(cls, v: str) -> str:
        import re

        if not re.match(r"^[A-Z]{2,6}\d{3,6}$", v):
            raise ValueError(f"rule_id must match PYD001 pattern, got {v!r}")
        return v


class DetectionRulesConfig(BaseModel):
    model_config = {"frozen": True}

    version: str
    rules: list[DetectionRule]

    @field_validator("rules")
    @classmethod
    def no_duplicate_rule_ids(cls, v: list[DetectionRule]) -> list[DetectionRule]:
        ids = [r.rule_id for r in v]
        if len(ids) != len(set(ids)):
            dupes = {x for x in ids if ids.count(x) > 1}
            raise ValueError(f"Duplicate rule_ids: {dupes}")
        return v


# ---------------------------------------------------------------------------
# Risk rules (risk_rules.yaml)
# ---------------------------------------------------------------------------


class RiskLevelThreshold(BaseModel):
    model_config = {"frozen": True}

    level: RiskLevel
    min_points: Annotated[int, Field(ge=0)]


class RiskScoringSpec(BaseModel):
    """Flexible scoring specification."""

    model_config = {"frozen": True, "extra": "allow"}

    kind: str


class RiskComponent(BaseModel):
    model_config = {"frozen": True}

    component_id: str
    description: str
    scoring: RiskScoringSpec
    rationale: str
    rule_ids: list[str] = Field(default_factory=list)
    source: str | None = None


class RiskRulesConfig(BaseModel):
    model_config = {"frozen": True}

    version: str
    scoring_version: str
    max_points: Annotated[int, Field(gt=0)]
    levels: list[RiskLevelThreshold]
    rules: list[RiskComponent]

    @field_validator("levels")
    @classmethod
    def levels_include_low(cls, v: list[RiskLevelThreshold]) -> list[RiskLevelThreshold]:
        level_names = {lvl.level for lvl in v}
        if RiskLevel.LOW not in level_names:
            raise ValueError("risk levels must include LOW")
        return v


# ---------------------------------------------------------------------------
# Validation rules (validation_rules.yaml)
# ---------------------------------------------------------------------------


class ValidationRule(BaseModel):
    model_config = {"frozen": True}

    validator_id: str
    description: str
    severity: ValidationSeverity
    check: str
    message_template: str
    patterns: list[str] = Field(default_factory=list)


class ValidationRulesConfig(BaseModel):
    model_config = {"frozen": True}

    version: str
    rules: list[ValidationRule]

    @field_validator("rules")
    @classmethod
    def no_duplicate_validator_ids(cls, v: list[ValidationRule]) -> list[ValidationRule]:
        ids = [r.validator_id for r in v]
        if len(ids) != len(set(ids)):
            dupes = {x for x in ids if ids.count(x) > 1}
            raise ValueError(f"Duplicate validator_ids: {dupes}")
        return v


# ---------------------------------------------------------------------------
# Applicability config (applicability.yaml) — loosely typed
# ---------------------------------------------------------------------------


class ApplicabilityConfig(BaseModel):
    """Parsed applicability.yaml — loosely typed for flexibility."""

    model_config = {"frozen": True}

    version: str
    manifest_signals: list[dict[str, Any]] = Field(default_factory=list)
    code_signals: list[dict[str, Any]] = Field(default_factory=list)
    aggregation: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------


class PromptTemplate(BaseModel):
    """A loaded and parsed prompt template from a .md file."""

    model_config = {"frozen": True}

    prompt_id: str
    version: str
    pack_id: str
    description: str
    max_tokens: int
    body: str


# ---------------------------------------------------------------------------
# Composite: everything loaded for one pack
# ---------------------------------------------------------------------------


class LoadedMigrationPack(BaseModel):
    """
    All validated content for a migration pack.

    This is the object that the core services receive.
    It contains no Pydantic-specific logic — that lives in the YAML definitions.
    """

    model_config = {"frozen": True}

    metadata: MigrationPackMetadata
    applicability: ApplicabilityConfig
    detection_rules: DetectionRulesConfig
    risk_rules: RiskRulesConfig
    trusted_sources: TrustedSourcesConfig
    validation_rules: ValidationRulesConfig
    prompts: dict[str, PromptTemplate]

    # ── Convenience accessors ──────────────────────────────────────────────

    def get_rule(self, rule_id: str) -> DetectionRule | None:
        return next((r for r in self.detection_rules.rules if r.rule_id == rule_id), None)

    def get_source(self, source_id: str) -> TrustedSource | None:
        return next((s for s in self.trusted_sources.sources if s.source_id == source_id), None)

    def get_prompt(self, prompt_id: str) -> PromptTemplate | None:
        return self.prompts.get(prompt_id)

    def known_rule_ids(self) -> frozenset[str]:
        return frozenset(r.rule_id for r in self.detection_rules.rules)

    def known_source_ids(self) -> frozenset[str]:
        return frozenset(s.source_id for s in self.trusted_sources.sources)

    def langsmith_metadata(self) -> dict[str, str]:
        """Version metadata to attach to every LangSmith trace for this pack."""
        return {
            "pack_id": self.metadata.pack_id,
            "pack_version": self.metadata.version,
            "detector_version": self.metadata.detector_version,
            "scoring_version": self.metadata.scoring_version,
            "curated_source_snapshot_version": self.metadata.curated_source_snapshot_version,
            "prompt_version_documentation_research": (
                self.metadata.prompt_versions.documentation_research
            ),
            "prompt_version_compatibility_interpretation": (
                self.metadata.prompt_versions.compatibility_interpretation
            ),
            "prompt_version_migration_planning": (self.metadata.prompt_versions.migration_planning),
            "prompt_version_evidence_critic": (self.metadata.prompt_versions.evidence_critic),
        }
