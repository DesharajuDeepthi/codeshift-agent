"""
Unit tests for the deterministic AST scanner.

Coverage:
    S01  PYD001 – @validator fires, carries correct metadata
    S02  PYD001 – negative: @validator not from pydantic → no finding
    S03  PYD002 – @root_validator fires
    S04  PYD002 – negative: @model_validator (v2) → no finding
    S05  PYD003 – inner class Config inside BaseModel subclass
    S06  PYD003 – negative: class Config NOT in BaseModel subclass → no finding
    S07  PYD004–PYD008 – Config attribute assignments
    S08  PYD004 – negative: from_attributes (v2) → no finding
    S09  PYD009 – .dict() call in pydantic file
    S10  PYD009 – negative: .dict() but no pydantic import → no finding
    S11  PYD010 – .json() call
    S12  PYD011 – .copy() call
    S13  PYD012 – .parse_obj() call
    S14  PYD013 – .parse_raw() call
    S15  PYD014 – parse_obj_as() function call
    S16  PYD015 – .from_orm() call
    S17  PYD016 – .schema() call
    S18  PYD017 – .schema_json() call
    S19  PYD018 – .__fields__ access
    S20  PYD018 – negative: .model_fields (v2) → no finding
    S21  PYD019 – GenericModel import
    S22  PYD019 – negative: BaseModel + Generic (v2) → no finding
    S23  PYD020 – pydantic.dataclasses import
    S24  PYD020 – negative: stdlib dataclasses → no finding
    S25  PYD021 – pydantic.v1 compat import
    S26  PYD021 – negative: plain pydantic v2 import → no finding
    S27  PYD022 – GetterDict import
    S28  PYD022 – negative: no GetterDict → no finding
    S29  Mixed v1 fixture triggers multiple rules
    S30  Mixed v2 negative fixture → zero findings
    S31  Syntax error file falls back to text scanner (lower confidence)
    S32  MigrationFinding has all required fields populated
    S33  Line numbers are accurate for @validator
    S34  Line numbers are accurate for class Config
    S35  scan_workspace processes multiple files correctly
    S36  scan_workspace skips files without pydantic import
"""

from __future__ import annotations

from pathlib import Path

import pytest

from upgradepilot.analyzers.ast_scanner import scan_file, scan_workspace
from upgradepilot.migration.loader import load_pack
from upgradepilot.models.finding import MatchKind

FIXTURES = Path(__file__).parent.parent / "fixtures" / "detection"
REAL_PACK_DIR = Path(__file__).parent.parent.parent / "migration_packs" / "pydantic_v1_to_v2"


@pytest.fixture(scope="module")
def pack():
    return load_pack(REAL_PACK_DIR)


def _scan(filename: str, pack) -> list:
    src = (FIXTURES / filename).read_text(encoding="utf-8")
    findings, _ = scan_file(src, filename, pack)
    return findings


def _rule_ids(findings) -> set[str]:
    return {f.rule_id for f in findings}


# ---------------------------------------------------------------------------
# PYD001
# ---------------------------------------------------------------------------


class TestPYD001:
    def test_s01_validator_fires(self, pack) -> None:
        findings = _scan("pyd001_pos.py", pack)
        assert "PYD001" in _rule_ids(findings)

    def test_s02_validator_not_from_pydantic(self, pack) -> None:
        findings = _scan("pyd001_neg.py", pack)
        # field_validator (v2) must NOT trigger PYD001
        assert "PYD001" not in _rule_ids(findings)

    def test_s01_finding_metadata(self, pack) -> None:
        findings = _scan("pyd001_pos.py", pack)
        pyd001 = [f for f in findings if f.rule_id == "PYD001"][0]
        assert pyd001.pack_id == "pydantic-v1-to-v2"
        assert pyd001.severity == "HIGH"
        assert pyd001.match_kind == MatchKind.AST
        assert pyd001.confidence >= 0.90
        assert pyd001.file == "pyd001_pos.py"
        assert pyd001.line_start >= 1
        assert "validator" in pyd001.symbol

    def test_s33_line_numbers_accurate(self, pack) -> None:
        src = (FIXTURES / "pyd001_pos.py").read_text()
        lines = src.splitlines()
        findings, _ = scan_file(src, "pyd001_pos.py", pack)
        for f in findings:
            if f.rule_id == "PYD001":
                # The reported line should contain "@validator"
                line_content = lines[f.line_start - 1]
                assert "validator" in line_content


# ---------------------------------------------------------------------------
# PYD002
# ---------------------------------------------------------------------------


class TestPYD002:
    def test_s03_root_validator_fires(self, pack) -> None:
        findings = _scan("pyd002_pos.py", pack)
        assert "PYD002" in _rule_ids(findings)

    def test_s04_model_validator_v2_no_finding(self, pack) -> None:
        findings = _scan("pyd002_neg.py", pack)
        assert "PYD002" not in _rule_ids(findings)


# ---------------------------------------------------------------------------
# PYD003 – class Config
# ---------------------------------------------------------------------------


class TestPYD003:
    def test_s05_config_inside_basemodel(self, pack) -> None:
        findings = _scan("pyd003_008_pos.py", pack)
        assert "PYD003" in _rule_ids(findings)

    def test_s06_config_not_in_basemodel(self, pack) -> None:
        findings = _scan("pyd003_neg.py", pack)
        assert "PYD003" not in _rule_ids(findings)

    def test_s34_config_line_accurate(self, pack) -> None:
        src = (FIXTURES / "pyd003_008_pos.py").read_text()
        lines = src.splitlines()
        findings, _ = scan_file(src, "pyd003_008_pos.py", pack)
        for f in findings:
            if f.rule_id == "PYD003":
                line_content = lines[f.line_start - 1]
                assert "class Config" in line_content


# ---------------------------------------------------------------------------
# PYD004–PYD008 – Config attribute assignments
# ---------------------------------------------------------------------------


class TestConfigAttributes:
    def test_s07_config_attributes_fire(self, pack) -> None:
        found = _rule_ids(_scan("pyd003_008_pos.py", pack))
        assert "PYD004" in found  # orm_mode
        assert "PYD005" in found  # allow_population_by_field_name
        assert "PYD006" in found  # validate_all
        assert "PYD007" in found  # smart_union
        assert "PYD008" in found  # json_encoders

    def test_s08_from_attributes_no_finding(self, pack) -> None:
        findings = _scan("pyd004_neg.py", pack)
        assert "PYD004" not in _rule_ids(findings)


# ---------------------------------------------------------------------------
# PYD009–PYD011 – serialization method calls
# ---------------------------------------------------------------------------


class TestSerializationMethods:
    def test_s09_dict_call_fires(self, pack) -> None:
        assert "PYD009" in _rule_ids(_scan("pyd009_011_pos.py", pack))

    def test_s10_dict_no_pydantic_no_finding(self, pack) -> None:
        assert "PYD009" not in _rule_ids(_scan("pyd009_neg.py", pack))

    def test_s11_json_call_fires(self, pack) -> None:
        assert "PYD010" in _rule_ids(_scan("pyd009_011_pos.py", pack))

    def test_s12_copy_call_fires(self, pack) -> None:
        assert "PYD011" in _rule_ids(_scan("pyd009_011_pos.py", pack))


# ---------------------------------------------------------------------------
# PYD012–PYD015 – parsing methods
# ---------------------------------------------------------------------------


class TestParsingMethods:
    def test_s13_parse_obj_fires(self, pack) -> None:
        assert "PYD012" in _rule_ids(_scan("pyd012_015_pos.py", pack))

    def test_s14_parse_raw_fires(self, pack) -> None:
        assert "PYD013" in _rule_ids(_scan("pyd012_015_pos.py", pack))

    def test_s15_parse_obj_as_fires(self, pack) -> None:
        assert "PYD014" in _rule_ids(_scan("pyd014_pos.py", pack))

    def test_s16_from_orm_fires(self, pack) -> None:
        assert "PYD015" in _rule_ids(_scan("pyd012_015_pos.py", pack))

    def test_v2_methods_no_finding(self, pack) -> None:
        found = _rule_ids(_scan("pyd012_neg.py", pack))
        assert "PYD012" not in found
        assert "PYD013" not in found


# ---------------------------------------------------------------------------
# PYD016–PYD017 – schema methods
# ---------------------------------------------------------------------------


class TestSchemaMethods:
    def test_s17_schema_fires(self, pack) -> None:
        assert "PYD016" in _rule_ids(_scan("pyd016_017_pos.py", pack))

    def test_s18_schema_json_fires(self, pack) -> None:
        assert "PYD017" in _rule_ids(_scan("pyd016_017_pos.py", pack))

    def test_v2_schema_no_finding(self, pack) -> None:
        found = _rule_ids(_scan("pyd016_neg.py", pack))
        assert "PYD016" not in found
        assert "PYD017" not in found


# ---------------------------------------------------------------------------
# PYD018 – __fields__
# ---------------------------------------------------------------------------


class TestFields:
    def test_s19_fields_fires(self, pack) -> None:
        assert "PYD018" in _rule_ids(_scan("pyd018_pos.py", pack))

    def test_s20_model_fields_no_finding(self, pack) -> None:
        assert "PYD018" not in _rule_ids(_scan("pyd018_neg.py", pack))


# ---------------------------------------------------------------------------
# PYD019 – GenericModel
# ---------------------------------------------------------------------------


class TestGenericModel:
    def test_s21_generic_model_fires(self, pack) -> None:
        assert "PYD019" in _rule_ids(_scan("pyd019_pos.py", pack))

    def test_s22_base_model_generic_no_finding(self, pack) -> None:
        assert "PYD019" not in _rule_ids(_scan("pyd019_neg.py", pack))


# ---------------------------------------------------------------------------
# PYD020 – pydantic.dataclasses
# ---------------------------------------------------------------------------


class TestPydanticDataclasses:
    def test_s23_pydantic_dataclasses_fires(self, pack) -> None:
        assert "PYD020" in _rule_ids(_scan("pyd020_pos.py", pack))

    def test_s24_stdlib_dataclasses_no_finding(self, pack) -> None:
        assert "PYD020" not in _rule_ids(_scan("pyd020_neg.py", pack))


# ---------------------------------------------------------------------------
# PYD021 – pydantic.v1 compat shim
# ---------------------------------------------------------------------------


class TestCompatShim:
    def test_s25_v1_shim_fires(self, pack) -> None:
        assert "PYD021" in _rule_ids(_scan("pyd021_pos.py", pack))

    def test_s26_v2_import_no_finding(self, pack) -> None:
        assert "PYD021" not in _rule_ids(_scan("pyd021_neg.py", pack))


# ---------------------------------------------------------------------------
# PYD022 – GetterDict
# ---------------------------------------------------------------------------


class TestGetterDict:
    def test_s27_getter_dict_fires(self, pack) -> None:
        assert "PYD022" in _rule_ids(_scan("pyd022_pos.py", pack))

    def test_s28_no_getter_dict_no_finding(self, pack) -> None:
        assert "PYD022" not in _rule_ids(_scan("pyd022_neg.py", pack))


# ---------------------------------------------------------------------------
# Mixed fixtures
# ---------------------------------------------------------------------------


class TestMixedFixtures:
    def test_s29_mixed_v1_triggers_many_rules(self, pack) -> None:
        found = _rule_ids(_scan("mixed_v1_pos.py", pack))
        expected = {
            "PYD001",
            "PYD002",
            "PYD003",
            "PYD004",
            "PYD005",
            "PYD008",
            "PYD009",
            "PYD010",
            "PYD011",
            "PYD012",
            "PYD018",
            "PYD019",
        }
        assert expected.issubset(found), f"Missing rules: {expected - found}"

    def test_s30_mixed_v2_zero_findings(self, pack) -> None:
        findings = _scan("mixed_v2_neg.py", pack)
        v1_rules = {f.rule_id for f in findings}
        # v2 file should have no findings at all (or only INFO-level false positives
        # that are acceptable — but ideally none)
        assert not v1_rules, f"Unexpected v1 findings in v2 file: {v1_rules}"


# ---------------------------------------------------------------------------
# Syntax error fallback
# ---------------------------------------------------------------------------


class TestSyntaxError:
    def test_s31_syntax_error_uses_text_fallback(self, pack) -> None:
        src = (FIXTURES / "syntax_error_pos.py").read_text()
        findings, syntax_ok = scan_file(src, "syntax_error_pos.py", pack)
        assert not syntax_ok, "Expected syntax_ok=False for malformed file"
        # Text fallback should still find @validator
        found = {f.rule_id for f in findings}
        assert "PYD001" in found
        for f in findings:
            assert f.match_kind == MatchKind.TEXT
            # Text fallback has lower confidence
            assert f.confidence <= 0.90


# ---------------------------------------------------------------------------
# Finding fields completeness
# ---------------------------------------------------------------------------


class TestFindingFields:
    def test_s32_all_required_fields_present(self, pack) -> None:
        findings = _scan("pyd001_pos.py", pack)
        assert findings, "Expected at least one finding"
        f = findings[0]
        assert f.finding_id  # non-empty UUID
        assert f.rule_id.startswith("PYD")
        assert f.pack_id == "pydantic-v1-to-v2"
        assert f.pack_version
        assert f.category
        assert f.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
        assert f.file
        assert f.line_start >= 1
        assert f.line_end >= f.line_start
        assert f.evidence
        assert f.symbol
        assert f.migration_concept
        assert f.source_ids
        assert f.detector == "ast_scanner"
        assert f.detector_version
        assert 0.0 <= f.confidence <= 1.0
        assert f.match_kind in (MatchKind.AST, MatchKind.TEXT)


# ---------------------------------------------------------------------------
# scan_workspace
# ---------------------------------------------------------------------------


class TestScanWorkspace:
    def test_s35_workspace_scans_multiple_files(self, pack, tmp_path) -> None:
        # Create a small workspace with two Python files
        f1 = tmp_path / "models.py"
        f1.write_text(
            "from pydantic import BaseModel, validator\n\n"
            "class M(BaseModel):\n"
            "    name: str\n\n"
            "    @validator('name')\n"
            "    def check(cls, v): return v\n",
            encoding="utf-8",
        )
        f2 = tmp_path / "other.py"
        f2.write_text(
            "from pydantic import BaseModel\n\n"
            "class N(BaseModel):\n"
            "    x: int\n\n"
            "def use(n): return n.dict()\n",
            encoding="utf-8",
        )
        result = scan_workspace(tmp_path, pack)
        assert result.scanned_files == 2
        rule_ids = {f.rule_id for f in result.findings}
        assert "PYD001" in rule_ids
        assert "PYD009" in rule_ids

    def test_s36_workspace_skips_non_pydantic(self, pack, tmp_path) -> None:
        f = tmp_path / "utils.py"
        f.write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        result = scan_workspace(tmp_path, pack)
        assert result.scanned_files == 1
        assert result.findings == []
