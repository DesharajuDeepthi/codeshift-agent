# 07 — Pydantic Migration Pack

## Purpose

Package-specific logic must live in a migration pack, not in the core graph.

## Directory

```text
migration_packs/pydantic_v1_to_v2/
├── pack.yaml
├── applicability.yaml
├── detection_rules.yaml
├── risk_rules.yaml
├── trusted_sources.yaml
├── validation_rules.yaml
├── prompts/
│   ├── documentation_research.md
│   ├── compatibility_interpretation.md
│   ├── migration_planning.md
│   └── evidence_critic.md
└── fixtures/
```

## Pack metadata

Include:

- pack ID;
- semantic version;
- source and target major versions;
- supported manifest formats;
- supported Python syntax versions;
- curated source snapshot version;
- detector version;
- scoring version;
- prompt versions.

## V1 detection-rule categories

Implement deterministic detection for common patterns, including:

- `BaseModel.parse_obj`
- model `.dict()`
- model `.json()`
- `BaseModel.schema`
- `BaseModel.schema_json`
- `BaseModel.copy`
- `@validator`
- `@root_validator`
- inner `class Config`
- `orm_mode`
- `allow_population_by_field_name`
- `validate_all`
- `smart_union`
- `json_encoders`
- `GenericModel`
- `pydantic.dataclasses`
- `parse_obj_as`
- `from_orm`
- `__fields__`
- custom `GetterDict`
- `pydantic.v1` compatibility imports
- imports from moved/changed modules.

Every rule must specify:

- rule ID;
- rationale;
- AST matcher or narrowly bounded fallback matcher;
- false-positive exclusions;
- severity;
- migration concept;
- official source IDs;
- risk points;
- tests.

## Detection policy

- Prefer AST.
- Fallback text scanning must be marked lower confidence.
- Never recommend a blind replacement when semantics may differ.
- Dynamic imports, aliases, decorators, metaprogramming, and wrappers should trigger review flags.
- Generated, vendored, virtual-environment, cache, and build directories are excluded by default.

## Applicability

Use multiple signals:

- manifest constraint;
- imports;
- v1-specific symbols;
- compatibility namespace;
- lock file when supported.

Do not infer an exact installed version without lock or manifest evidence.

## Risk model examples

Potential components:

- removed or behavior-changing API usage;
- validator migration complexity;
- ORM/model population behavior;
- serialization behavior;
- custom schema generation;
- widespread affected files;
- public API models;
- low or missing test coverage signals;
- CI not detected;
- dynamic patterns requiring review.

Risk scoring remains deterministic and versioned.

## Trusted sources

Use only official Pydantic documentation and official repository release/migration material identified in `trusted_sources.yaml`.

## Pack extensibility

Core services load the pack through an interface such as:

```python
class MigrationPack(Protocol):
    metadata: MigrationPackMetadata
    def assess_applicability(...) -> ApplicabilityResult: ...
    def scan(...) -> list[MigrationFinding]: ...
    def score(...) -> RiskAssessment: ...
    def trusted_sources(...) -> list[TrustedSource]: ...
    def validate(...) -> list[ValidationIssue]: ...
```
