"""
Tests for the migration-pack loader.

Positive scenarios:
    P1  The real pydantic-v1-to-v2 pack loads without errors.
    P2  LoadedMigrationPack helpers return expected values.
    P3  langsmith_metadata() returns all required version keys.
    P4  PackRegistry stores and retrieves by pack_id.
    P5  load_all_packs() populates the registry from the real packs directory.

Negative scenarios:
    N1  Missing pack.yaml → PackMissingFileError.
    N2  Invalid YAML in pack.yaml → PackSchemaError.
    N3  Missing required YAML file → PackMissingFileError.
    N4  Schema violation in detection_rules.yaml → PackSchemaError.
    N5  Missing prompt file → PackMissingFileError.
    N6  Prompt front-matter missing required keys → PackPromptError.
    N7  prompt_id in front-matter does not match filename → PackPromptError.
    N8  Detection rule references unknown source_id → PackSchemaError.
    N9  PackRegistry.get() with unknown id → PackNotFoundError.
    N10 load_all_packs() on empty directory → PackLoadError.
    N11 Prompt version mismatch with pack.yaml declaration → PackSchemaError.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from upgradepilot.migration.errors import (
    PackLoadError,
    PackMissingFileError,
    PackNotFoundError,
    PackPromptError,
    PackSchemaError,
)
from upgradepilot.migration.loader import (
    MigrationPackRegistry,
    load_all_packs,
    load_pack,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REAL_PACK_DIR = Path(__file__).parent.parent.parent / "migration_packs" / "pydantic_v1_to_v2"


def _copy_pack(tmp_path: Path) -> Path:
    """Return a fresh, mutable copy of the real pack under tmp_path."""
    dest = tmp_path / "pydantic_v1_to_v2"
    shutil.copytree(REAL_PACK_DIR, dest)
    return dest


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


class TestPositive:
    def test_p1_real_pack_loads(self) -> None:
        pack = load_pack(REAL_PACK_DIR)
        assert pack.metadata.pack_id == "pydantic-v1-to-v2"
        assert pack.metadata.source_major == 1
        assert pack.metadata.target_major == 2

    def test_p2_helper_methods(self) -> None:
        pack = load_pack(REAL_PACK_DIR)
        # Detection rules
        assert len(pack.known_rule_ids()) > 0
        some_id = next(iter(pack.known_rule_ids()))
        rule = pack.get_rule(some_id)
        assert rule is not None
        assert rule.rule_id == some_id

        # Trusted sources
        assert len(pack.known_source_ids()) > 0
        some_src = next(iter(pack.known_source_ids()))
        src = pack.get_source(some_src)
        assert src is not None
        assert src.source_id == some_src

        # Prompts
        pt = pack.get_prompt("documentation_research")
        assert pt is not None
        assert pt.prompt_id == "documentation_research"
        assert len(pt.body) > 0

        # Missing lookup returns None
        assert pack.get_rule("NOSUCHID") is None
        assert pack.get_source("NOSUCHID") is None
        assert pack.get_prompt("nosuchprompt") is None

    def test_p3_langsmith_metadata(self) -> None:
        pack = load_pack(REAL_PACK_DIR)
        meta = pack.langsmith_metadata()
        assert meta["pack_id"] == "pydantic-v1-to-v2"
        assert "pack_version" in meta
        assert "detector_version" in meta
        assert "scoring_version" in meta
        for key in (
            "prompt_version_documentation_research",
            "prompt_version_compatibility_interpretation",
            "prompt_version_migration_planning",
            "prompt_version_evidence_critic",
        ):
            assert key in meta, f"missing key {key!r} in langsmith_metadata"

    def test_p4_registry_store_retrieve(self) -> None:
        pack = load_pack(REAL_PACK_DIR)
        reg = MigrationPackRegistry()
        reg.register(pack)
        assert len(reg) == 1
        retrieved = reg.get("pydantic-v1-to-v2")
        assert retrieved is pack
        assert reg.list_ids() == ["pydantic-v1-to-v2"]

    def test_p5_load_all_packs(self) -> None:
        packs_dir = REAL_PACK_DIR.parent
        reg = load_all_packs(packs_dir)
        assert len(reg) >= 1
        assert "pydantic-v1-to-v2" in reg.list_ids()


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


class TestNegative:
    def test_n1_missing_pack_yaml(self, tmp_path: Path) -> None:
        pack_dir = tmp_path / "my_pack"
        pack_dir.mkdir()
        with pytest.raises(PackMissingFileError) as exc_info:
            load_pack(pack_dir)
        assert "pack.yaml" in str(exc_info.value)

    def test_n2_invalid_yaml_in_pack_yaml(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        (pack_dir / "pack.yaml").write_text(":: invalid: yaml: {{", encoding="utf-8")
        with pytest.raises(PackSchemaError) as exc_info:
            load_pack(pack_dir)
        assert "pack.yaml" in str(exc_info.value)

    def test_n3_missing_required_yaml_file(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        (pack_dir / "detection_rules.yaml").unlink()
        with pytest.raises(PackMissingFileError) as exc_info:
            load_pack(pack_dir)
        assert "detection_rules.yaml" in str(exc_info.value)

    def test_n4_schema_violation_in_detection_rules(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        bad_data = {"version": "1.0.0", "rules": [{"bad_field": "no_rule_id"}]}
        (pack_dir / "detection_rules.yaml").write_text(yaml.dump(bad_data), encoding="utf-8")
        with pytest.raises(PackSchemaError) as exc_info:
            load_pack(pack_dir)
        assert "detection_rules.yaml" in str(exc_info.value)

    def test_n5_missing_prompt_file(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        (pack_dir / "prompts" / "evidence_critic.md").unlink()
        with pytest.raises(PackMissingFileError) as exc_info:
            load_pack(pack_dir)
        assert "evidence_critic" in str(exc_info.value)

    def test_n6_prompt_missing_front_matter_keys(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        prompt_path = pack_dir / "prompts" / "documentation_research.md"
        prompt_path.write_text(
            "---\nprompt_id: documentation_research\n---\nBody text.",
            encoding="utf-8",
        )
        with pytest.raises(PackPromptError) as exc_info:
            load_pack(pack_dir)
        assert "documentation_research" in str(exc_info.value)

    def test_n7_prompt_id_mismatch(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        prompt_path = pack_dir / "prompts" / "documentation_research.md"
        content = (
            "---\n"
            "prompt_id: wrong_id\n"
            "version: '1.0.0'\n"
            "pack_id: pydantic-v1-to-v2\n"
            "description: desc\n"
            "max_tokens: 1024\n"
            "---\nBody.\n"
        )
        prompt_path.write_text(content, encoding="utf-8")
        with pytest.raises(PackPromptError) as exc_info:
            load_pack(pack_dir)
        assert "wrong_id" in str(exc_info.value) or "documentation_research" in str(exc_info.value)

    def test_n8_detection_rule_unknown_source_id(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        dr_path = pack_dir / "detection_rules.yaml"
        data: dict = yaml.safe_load(dr_path.read_text(encoding="utf-8"))
        # Inject a bad source_id into the first rule
        data["rules"][0]["source_ids"] = ["NONEXISTENT_SOURCE_XYZ"]
        dr_path.write_text(yaml.dump(data), encoding="utf-8")
        with pytest.raises(PackSchemaError) as exc_info:
            load_pack(pack_dir)
        assert "NONEXISTENT_SOURCE_XYZ" in str(exc_info.value)

    def test_n9_registry_unknown_pack_id(self) -> None:
        reg = MigrationPackRegistry()
        with pytest.raises(PackNotFoundError):
            reg.get("does-not-exist")

    def test_n10_load_all_packs_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "packs"
        empty.mkdir()
        with pytest.raises(PackLoadError):
            load_all_packs(empty)

    def test_n11_prompt_version_mismatch(self, tmp_path: Path) -> None:
        pack_dir = _copy_pack(tmp_path)
        prompt_path = pack_dir / "prompts" / "documentation_research.md"
        content = (
            "---\n"
            "prompt_id: documentation_research\n"
            "version: '99.0.0'\n"
            "pack_id: pydantic-v1-to-v2\n"
            "description: desc\n"
            "max_tokens: 4096\n"
            "---\nBody text.\n"
        )
        prompt_path.write_text(content, encoding="utf-8")
        with pytest.raises(PackSchemaError) as exc_info:
            load_pack(pack_dir)
        assert "99.0.0" in str(exc_info.value) or "version" in str(exc_info.value).lower()
