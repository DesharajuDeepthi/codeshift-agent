"""
Detection evaluation dataset — D2.

Each DetectionCase specifies:
- fixture_path: path relative to project root
- expected_rule_ids: rules that MUST fire (for recall)
- forbidden_rule_ids: rules that must NOT fire (for precision)
- expected_lines: rule_id → expected 1-based line number (for line accuracy)
- is_negative: True if this case should produce ZERO findings

Rules with expected_lines require exact line-number verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Project root — two levels up from this file
_ROOT = Path(__file__).parent.parent.parent

FIXTURES = _ROOT / "tests" / "fixtures" / "detection"


@dataclass(frozen=True)
class DetectionCase:
    name: str
    fixture_path: Path
    expected_rule_ids: frozenset[str] = field(default_factory=frozenset)
    forbidden_rule_ids: frozenset[str] = field(default_factory=frozenset)
    # rule_id -> expected line number (1-based)
    expected_lines: dict[str, int] = field(default_factory=dict)
    is_negative: bool = False


def _case(
    name: str,
    filename: str,
    expected: list[str] | None = None,
    forbidden: list[str] | None = None,
    lines: dict[str, int] | None = None,
    negative: bool = False,
) -> DetectionCase:
    return DetectionCase(
        name=name,
        fixture_path=FIXTURES / filename,
        expected_rule_ids=frozenset(expected or []),
        forbidden_rule_ids=frozenset(forbidden or []),
        expected_lines=lines or {},
        is_negative=negative,
    )


DETECTION_CASES: list[DetectionCase] = [
    # ── PYD001 ───────────────────────────────────────────────────────────────
    _case(
        "pyd001_pos",
        "pyd001_pos.py",
        expected=["PYD001"],
        lines={"PYD001": 9},  # @validator("name") line
    ),
    _case(
        "pyd001_neg",
        "pyd001_neg.py",
        forbidden=["PYD001"],
        negative=True,
    ),
    # ── PYD002 ───────────────────────────────────────────────────────────────
    _case(
        "pyd002_pos",
        "pyd002_pos.py",
        expected=["PYD002"],
    ),
    _case(
        "pyd002_neg",
        "pyd002_neg.py",
        forbidden=["PYD002"],
        negative=True,
    ),
    # ── PYD003–PYD008 (class Config + attributes) ─────────────────────────────
    _case(
        "pyd003_008_pos",
        "pyd003_008_pos.py",
        expected=["PYD003", "PYD004", "PYD005", "PYD006", "PYD007", "PYD008"],
    ),
    _case(
        "pyd003_neg",
        "pyd003_neg.py",
        forbidden=["PYD003"],
        negative=True,
    ),
    _case(
        "pyd004_neg",
        "pyd004_neg.py",
        forbidden=["PYD004"],
        negative=True,
    ),
    # ── PYD009–PYD011 (serialization methods) ─────────────────────────────────
    _case(
        "pyd009_011_pos",
        "pyd009_011_pos.py",
        expected=["PYD009", "PYD010", "PYD011"],
    ),
    _case(
        "pyd009_neg",
        "pyd009_neg.py",
        forbidden=["PYD009"],
        negative=True,
    ),
    # ── PYD012–PYD015 (parsing methods) ───────────────────────────────────────
    _case(
        "pyd012_015_pos",
        "pyd012_015_pos.py",
        expected=["PYD012", "PYD013", "PYD015"],
    ),
    _case(
        "pyd014_pos",
        "pyd014_pos.py",
        expected=["PYD014"],
    ),
    _case(
        "pyd012_neg",
        "pyd012_neg.py",
        forbidden=["PYD012", "PYD013"],
        negative=True,
    ),
    # ── PYD016–PYD017 (schema methods) ────────────────────────────────────────
    _case(
        "pyd016_017_pos",
        "pyd016_017_pos.py",
        expected=["PYD016", "PYD017"],
    ),
    _case(
        "pyd016_neg",
        "pyd016_neg.py",
        forbidden=["PYD016", "PYD017"],
        negative=True,
    ),
    # ── PYD018 ───────────────────────────────────────────────────────────────
    _case(
        "pyd018_pos",
        "pyd018_pos.py",
        expected=["PYD018"],
    ),
    _case(
        "pyd018_neg",
        "pyd018_neg.py",
        forbidden=["PYD018"],
        negative=True,
    ),
    # ── PYD019 ───────────────────────────────────────────────────────────────
    _case(
        "pyd019_pos",
        "pyd019_pos.py",
        expected=["PYD019"],
    ),
    _case(
        "pyd019_neg",
        "pyd019_neg.py",
        forbidden=["PYD019"],
        negative=True,
    ),
    # ── PYD020 ───────────────────────────────────────────────────────────────
    _case(
        "pyd020_pos",
        "pyd020_pos.py",
        expected=["PYD020"],
    ),
    _case(
        "pyd020_neg",
        "pyd020_neg.py",
        forbidden=["PYD020"],
        negative=True,
    ),
    # ── PYD021 ───────────────────────────────────────────────────────────────
    _case(
        "pyd021_pos",
        "pyd021_pos.py",
        expected=["PYD021"],
    ),
    _case(
        "pyd021_neg",
        "pyd021_neg.py",
        forbidden=["PYD021"],
        negative=True,
    ),
    # ── PYD022 ───────────────────────────────────────────────────────────────
    _case(
        "pyd022_pos",
        "pyd022_pos.py",
        expected=["PYD022"],
    ),
    _case(
        "pyd022_neg",
        "pyd022_neg.py",
        forbidden=["PYD022"],
        negative=True,
    ),
    # ── Mixed fixtures ────────────────────────────────────────────────────────
    _case(
        "mixed_v1_pos",
        "mixed_v1_pos.py",
        expected=[
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
        ],
    ),
    _case(
        "mixed_v2_neg",
        "mixed_v2_neg.py",
        forbidden=[
            "PYD001",
            "PYD002",
            "PYD003",
            "PYD004",
            "PYD005",
            "PYD006",
            "PYD007",
            "PYD008",
            "PYD009",
            "PYD010",
            "PYD011",
            "PYD012",
            "PYD013",
            "PYD014",
            "PYD015",
            "PYD016",
            "PYD017",
            "PYD018",
            "PYD019",
            "PYD020",
            "PYD021",
            "PYD022",
        ],
        negative=True,
    ),
]

# ---------------------------------------------------------------------------
# Django v3 → v4 detection cases (regex analyzer)
# ---------------------------------------------------------------------------

_DJG_FORBIDDEN = [
    "DJG001", "DJG002", "DJG003", "DJG004", "DJG005",
    "DJG006", "DJG007", "DJG008", "DJG009", "DJG010",
]

DJANGO_DETECTION_CASES: list[DetectionCase] = [
    _case("djg001-model-class", "django_v3_app.py", expected=["DJG001"]),
    _case("djg002-use-l10n", "django_v3_app.py", expected=["DJG002"]),
    _case("djg003-csrf-origins", "django_v3_app.py", expected=["DJG003"]),
    _case("djg004-timezone-utc", "django_v3_app.py", expected=["DJG004"]),
    _case("djg005-conf-url", "django_v3_app.py", expected=["DJG005"]),
    _case("djg006-force-text", "django_v3_app.py", expected=["DJG006"]),
    _case("djg007-smart-text", "django_v3_app.py", expected=["DJG007"]),
    _case("djg008-ugettext", "django_v3_app.py", expected=["DJG008"]),
    _case("djg009-conn-max-age", "django_v3_app.py", expected=["DJG009"]),
    _case("djg010-formfield-callback", "django_v3_app.py", expected=["DJG010"]),
    _case(
        "django-v4-negative",
        "django_v4_negative.py",
        forbidden=_DJG_FORBIDDEN,
        negative=True,
    ),
]
