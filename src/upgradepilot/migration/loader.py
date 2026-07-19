"""
Migration-pack loader with startup validation.

Responsibilities:
- Discover pack directories under MIGRATION_PACKS_DIR.
- Parse and schema-validate each YAML file.
- Load and parse prompt templates.
- Raise PackLoadError (or a subclass) for any validation failure.
- Provide a typed registry accessible to graph nodes and services.

Design:
- No Pydantic-specific logic lives here; the loader is pack-agnostic.
- Invalid packs fail loudly at startup; they do not silently degrade.
- The loader is synchronous (called once at app startup, not per-request).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from upgradepilot.migration.errors import (
    PackLoadError,
    PackMissingFileError,
    PackNotFoundError,
    PackPromptError,
    PackSchemaError,
)
from upgradepilot.migration.models import (
    ApplicabilityConfig,
    DetectionRulesConfig,
    LoadedMigrationPack,
    MigrationPackMetadata,
    PromptTemplate,
    RiskRulesConfig,
    TrustedSourcesConfig,
    ValidationRulesConfig,
)

logger = logging.getLogger(__name__)

# Default location — can be overridden in tests or via environment
_DEFAULT_PACKS_DIR = Path(__file__).parent.parent.parent.parent / "migration_packs"

# Prompt front-matter pattern  ---key: value---
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Required YAML files beyond pack.yaml
_REQUIRED_YAML = (
    "applicability.yaml",
    "detection_rules.yaml",
    "risk_rules.yaml",
    "trusted_sources.yaml",
    "validation_rules.yaml",
)

# Required prompt IDs
_REQUIRED_PROMPTS = (
    "documentation_research",
    "compatibility_interpretation",
    "migration_planning",
    "evidence_critic",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path, pack_id: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise PackSchemaError(pack_id, path.name, "expected a YAML mapping at top level")
        return data
    except yaml.YAMLError as exc:
        raise PackSchemaError(pack_id, path.name, f"YAML parse error: {exc}") from exc
    except OSError as exc:
        raise PackMissingFileError(pack_id, path.name) from exc


def _validate_model(model_cls: type[Any], data: dict[str, Any], pack_id: str, filename: str) -> Any:  # noqa: ANN401
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise PackSchemaError(pack_id, filename, str(exc)) from exc


def _load_prompt(path: Path, pack_id: str, prompt_id: str) -> PromptTemplate:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackMissingFileError(pack_id, str(path.name)) from exc

    m = _FRONTMATTER_RE.match(raw)
    if not m:
        raise PackPromptError(pack_id, prompt_id, "missing YAML front-matter block (--- ... ---)")

    try:
        front = yaml.safe_load(m.group(1))
        if not isinstance(front, dict):
            raise PackPromptError(pack_id, prompt_id, "front-matter must be a YAML mapping")
    except yaml.YAMLError as exc:
        raise PackPromptError(pack_id, prompt_id, f"front-matter YAML error: {exc}") from exc

    body = raw[m.end() :]

    required_keys = {"prompt_id", "version", "pack_id", "description", "max_tokens"}
    missing = required_keys - set(front)
    if missing:
        raise PackPromptError(
            pack_id, prompt_id, f"front-matter missing required keys: {sorted(missing)}"
        )

    if front["prompt_id"] != prompt_id:
        raise PackPromptError(
            pack_id,
            prompt_id,
            f"prompt_id in front-matter ({front['prompt_id']!r}) "
            f"does not match expected ({prompt_id!r})",
        )

    if front["pack_id"] != pack_id:
        raise PackPromptError(
            pack_id,
            prompt_id,
            f"pack_id in front-matter ({front['pack_id']!r}) does not match pack ({pack_id!r})",
        )

    return PromptTemplate(
        prompt_id=str(front["prompt_id"]),
        version=str(front["version"]),
        pack_id=str(front["pack_id"]),
        description=str(front["description"]),
        max_tokens=int(front["max_tokens"]),
        body=body,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_pack(pack_dir: Path) -> LoadedMigrationPack:
    """
    Load and validate a single migration pack from a directory.

    Raises PackLoadError (or a subclass) on any validation failure.
    This is intentionally strict: a bad pack must not allow startup.
    """
    pack_yaml_path = pack_dir / "pack.yaml"
    if not pack_yaml_path.exists():
        raise PackMissingFileError(pack_dir.name, "pack.yaml")

    # 1 — Load and validate pack.yaml first (gives us the pack_id)
    raw_meta = _load_yaml(pack_yaml_path, pack_dir.name)
    metadata: MigrationPackMetadata = _validate_model(
        MigrationPackMetadata, raw_meta, pack_dir.name, "pack.yaml"
    )
    pack_id = metadata.pack_id

    logger.debug("Loading pack %r from %s", pack_id, pack_dir)

    # 2 — Verify all required YAML files exist
    for fname in _REQUIRED_YAML:
        if not (pack_dir / fname).exists():
            raise PackMissingFileError(pack_id, fname)

    # 3 — Load and validate each YAML config file
    applicability = _validate_model(
        ApplicabilityConfig,
        _load_yaml(pack_dir / "applicability.yaml", pack_id),
        pack_id,
        "applicability.yaml",
    )

    detection_rules = _validate_model(
        DetectionRulesConfig,
        _load_yaml(pack_dir / "detection_rules.yaml", pack_id),
        pack_id,
        "detection_rules.yaml",
    )

    risk_rules = _validate_model(
        RiskRulesConfig,
        _load_yaml(pack_dir / "risk_rules.yaml", pack_id),
        pack_id,
        "risk_rules.yaml",
    )

    trusted_sources = _validate_model(
        TrustedSourcesConfig,
        _load_yaml(pack_dir / "trusted_sources.yaml", pack_id),
        pack_id,
        "trusted_sources.yaml",
    )

    validation_rules = _validate_model(
        ValidationRulesConfig,
        _load_yaml(pack_dir / "validation_rules.yaml", pack_id),
        pack_id,
        "validation_rules.yaml",
    )

    # 4 — Cross-validate: detection rules must cite known source IDs
    known_source_ids = {s.source_id for s in trusted_sources.sources}
    for rule in detection_rules.rules:
        unknown = set(rule.source_ids) - known_source_ids
        if unknown:
            raise PackSchemaError(
                pack_id,
                "detection_rules.yaml",
                f"Rule {rule.rule_id} references unknown source_ids: {sorted(unknown)}",
            )

    # 5 — Load prompt templates
    prompts_dir = pack_dir / "prompts"
    prompts: dict[str, PromptTemplate] = {}
    for prompt_id in _REQUIRED_PROMPTS:
        prompt_path = prompts_dir / f"{prompt_id}.md"
        if not prompt_path.exists():
            raise PackMissingFileError(pack_id, f"prompts/{prompt_id}.md")
        prompts[prompt_id] = _load_prompt(prompt_path, pack_id, prompt_id)

    # 6 — Verify prompt versions match pack.yaml declarations
    pv = metadata.prompt_versions
    version_map = {
        "documentation_research": pv.documentation_research,
        "compatibility_interpretation": pv.compatibility_interpretation,
        "migration_planning": pv.migration_planning,
        "evidence_critic": pv.evidence_critic,
    }
    for prompt_id, expected_version in version_map.items():
        actual = prompts[prompt_id].version
        if actual != expected_version:
            raise PackSchemaError(
                pack_id,
                f"prompts/{prompt_id}.md",
                f"prompt version {actual!r} does not match pack.yaml declaration "
                f"{expected_version!r}",
            )

    logger.info(
        "Pack %r loaded: %d detection rules, %d risk components, %d sources, %d prompts",
        pack_id,
        len(detection_rules.rules),
        len(risk_rules.rules),
        len(trusted_sources.sources),
        len(prompts),
    )

    return LoadedMigrationPack(
        metadata=metadata,
        applicability=applicability,
        detection_rules=detection_rules,
        risk_rules=risk_rules,
        trusted_sources=trusted_sources,
        validation_rules=validation_rules,
        prompts=prompts,
    )


class MigrationPackRegistry:
    """
    In-memory registry of all loaded migration packs.

    Populated at startup.  Read-only after initialisation.
    """

    def __init__(self) -> None:
        self._packs: dict[str, LoadedMigrationPack] = {}

    def register(self, pack: LoadedMigrationPack) -> None:
        self._packs[pack.metadata.pack_id] = pack
        logger.debug("Registered pack %r", pack.metadata.pack_id)

    def get(self, pack_id: str) -> LoadedMigrationPack:
        if pack_id not in self._packs:
            raise PackNotFoundError(pack_id)
        return self._packs[pack_id]

    def list_ids(self) -> list[str]:
        return sorted(self._packs)

    def __len__(self) -> int:
        return len(self._packs)


def load_all_packs(packs_dir: Path | None = None) -> MigrationPackRegistry:
    """
    Discover and load all packs from the packs directory.

    Raises PackLoadError on the first invalid pack encountered.
    Call this at application startup before serving requests.
    """
    root = packs_dir or _DEFAULT_PACKS_DIR
    if not root.is_dir():
        raise PackLoadError("*", f"migration_packs directory not found: {root}")

    registry = MigrationPackRegistry()
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        pack = load_pack(entry)
        registry.register(pack)

    if len(registry) == 0:
        raise PackLoadError("*", f"no packs found in {root}")

    logger.info("Loaded %d migration pack(s): %s", len(registry), registry.list_ids())
    return registry
