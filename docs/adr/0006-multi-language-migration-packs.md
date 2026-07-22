# ADR-0006 — Multi-Language Migration Pack Architecture

## Status

Proposed.

## Context

Phase 1 shipped `pydantic-v1-to-v2`, a single Python-specific migration pack.
The graph, agent, evidence, and report layers are already mostly pack-agnostic;
the coupling to Python and Pydantic lives in a small number of places:

| Location | Coupling |
|---|---|
| `models/profile.py` | `PydanticSignal` enum; `pydantic_dependencies` field; `has_pydantic_imports` |
| `migration/models.py` | `supported_python_syntax_versions`; no `language` / `analyzer_kind` fields |
| `analyzers/ast_scanner.py` | Python `ast` module — not usable for TypeScript, Go, Java, etc. |
| `analyzers/manifest_parser.py` | Only parses `requirements.txt` and `pyproject.toml` |
| `analyzers/repository_profiler.py` | Counts only `.py` files; looks only for Pydantic package names |
| `graph/nodes/profiling.py` | `select_migration_pack` contains hardcoded Pydantic applicability logic |
| `models/request.py` | `_SUPPORTED_PACKS = {"pydantic-v1-to-v2"}` — static allowlist |

The goal of this ADR is to remove all of that coupling so that adding a new
migration pack for any language (TypeScript, Go, Java, Rust, …) requires only:

1. A new `migration_packs/<pack-id>/` directory with YAML + prompts.
2. A `LanguageAnalyzer` implementation if the language needs AST-level scanning
   beyond what `RegexAnalyzer` provides.
3. A `ManifestParser` implementation if the language uses a manifest format not
   already registered.

No changes to graph topology, agent code, evidence validators, or report
renderers are needed for new packs.

## Decision

### 1. Migration pack metadata adds `language` and `analyzer_kind`

`pack.yaml` gains two required fields:

```yaml
language: python          # canonical lower-case language identifier
analyzer_kind: python-ast # which LanguageAnalyzer to dispatch to
```

`supported_python_syntax_versions` is renamed to `supported_syntax_versions`
(an ordered list of runtime/language versions the pack covers).

### 2. `LanguageAnalyzer` Protocol and registry

A new `analyzers/base.py` defines:

```python
class LanguageAnalyzer(Protocol):
    analyzer_kind: str
    def scan(self, workspace: Path, pack: LoadedMigrationPack) -> ScanResult: ...
```

`analyzers/registry.py` maps `analyzer_kind` strings to implementations and
is the single place any caller resolves an analyzer.

Built-in implementations:

| `analyzer_kind` | Class | Description |
|---|---|---|
| `python-ast` | `PythonASTAnalyzer` | AST-first + regex fallback (existing `ast_scanner.py` logic) |
| `regex` | `RegexAnalyzer` | Language-agnostic multi-line regex scanner |

Packs that require `semgrep` or `tree-sitter` can ship a plugin analyzer; the
registry supports external registration before graph startup.

### 3. `ManifestParser` Protocol and registry

A new `parsers/` subpackage defines:

```python
class ManifestParser(Protocol):
    supported_filenames: frozenset[str]
    language: str
    def parse(self, path: Path, content: str) -> list[DependencyEvidence]: ...
```

`parsers/registry.py` maps manifest filename patterns to parsers.

Built-in parsers:

| Manifest | Parser | Language |
|---|---|---|
| `requirements*.txt`, `pyproject.toml`, `setup.cfg` | `PythonManifestParser` | python |
| `package.json` | `PackageJsonParser` | typescript / javascript |
| `Cargo.toml` | `CargoTomlParser` | rust |
| `go.mod` | `GoModParser` | go |
| `pom.xml`, `build.gradle` | `MavenGradleParser` | java |
| `Gemfile` | `GemfileParser` | ruby |

The profiler uses the registry to parse every manifest it encounters,
regardless of language, and stores all results in `RepositoryProfile.all_dependencies`.

### 4. Generic `RepositoryProfile`

`PydanticSignal`, `pydantic_dependencies`, and `has_pydantic_imports` are
removed from the profile. The profile is now language-neutral:

```python
class RepositoryProfile(BaseModel):
    # Source files grouped by canonical language name
    source_files_by_language: dict[str, list[str]]  # {"python": [...], "typescript": [...]}
    detected_languages: list[str]                    # ordered by file count, descending
    primary_language: str | None                     # top language, or None if empty repo

    manifest_files: list[ManifestFile]
    all_dependencies: list[DependencyEvidence]       # from all parsers

    test_profile: TestProfile
    docker_files: list[str]
    packaging_files: list[str]
    excluded_paths: list[str]
    parse_errors: list[ParseError]
    profiler_version: str
```

`TestingFramework` and `CISystem` enums are extended with language-neutral
values; new values can be added by convention without changing graph code.

### 5. Pack-driven `ApplicabilityEngine`

A new `migration/applicability.py` implements a deterministic engine that
interprets the `applicability.yaml` already present in every pack:

```python
class ApplicabilityEngine:
    def __init__(self, pack: LoadedMigrationPack) -> None: ...
    def assess(self, profile: RepositoryProfile) -> ApplicabilityAssessment: ...
```

`ApplicabilityAssessment` carries the resulting `ApplicabilityStatus`, overall
confidence, and a list of `SignalResult` records explaining which signals fired.

The engine replaces the hardcoded Pydantic logic in `select_migration_pack`.

Signal kinds supported in `applicability.yaml`:

| `kind` | Description |
|---|---|
| `manifest_constraint` | Version constraint on a named package in any parsed manifest |
| `import_symbol` | Specific symbol imported from a module (language-aware via analyzer) |
| `v1_api_usage` | Text / AST pattern that only exists in the source version |
| `v2_api_usage` | Text / AST pattern that only exists in the target version |
| `compat_namespace` | Use of a compatibility shim (e.g. `pydantic.v1`) |
| `file_pattern` | Presence of files matching a glob (e.g. `*.ts` for TypeScript packs) |
| `language_present` | `detected_languages` contains the pack's declared language |

### 6. Dynamic pack allowlist in `AnalysisRequest`

`_SUPPORTED_PACKS` is removed. The `migration_pack` field validator defers
to the `MigrationPackRegistry` at validation time, so any pack registered in
the pack directory is automatically accepted.

### 7. `pydantic-v1-to-v2` pack changes

`pack.yaml` gains:

```yaml
language: python
analyzer_kind: python-ast
supported_syntax_versions:
  - "3.8"
  - "3.9"
  - "3.10"
  - "3.11"
  - "3.12"
```

`applicability.yaml` gains a `file_pattern` signal and a `language_present`
signal so the engine can short-circuit on non-Python repositories before
parsing manifests.

The pack's functional behaviour is unchanged.

### 8. Example second pack: `django-v3-to-v4`

A skeleton `migration_packs/django_v3_to_v4/` is added to prove the design.
It uses `language: python` and `analyzer_kind: regex` (no AST needed;
Django migration patterns are detectable with simple text patterns).

## Consequences

**Positive**
- Adding a new pack for any language requires only YAML + one optional
  Python class; no graph or agent changes.
- Pack applicability is tested in isolation via `ApplicabilityEngine` unit tests.
- `RepositoryProfile` is genuinely reusable across all packs.
- The analyzer and parser layers are independently testable and extensible.

**Negative / Risks**
- Existing fixture data in `graph/nodes/profiling.py` must be updated to
  the new `RepositoryProfile` schema; a one-time migration.
- Tests that assert on `PydanticSignal` values must be updated.
- Packs that previously relied on the hardcoded Pydantic check in
  `select_migration_pack` now depend on a correct `applicability.yaml`.

## Non-goals

- Multi-pack analysis in a single request (deferred to V3).
- Automatic pack recommendation UI (deferred to V3).
- Live package-manager invocation (permanently out of scope per CLAUDE.md).
