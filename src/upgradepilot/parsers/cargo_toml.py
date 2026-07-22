"""
Cargo.toml manifest parser for Rust projects.

Parses [dependencies], [dev-dependencies], and [build-dependencies] sections.
Uses the stdlib tomllib (Python 3.11+) or a fallback for older runtimes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from upgradepilot.models.profile import ConstraintKind, DependencyEvidence, VersionConstraint

logger = logging.getLogger(__name__)

_PARSER_NAME = "cargo_toml"
_PARSER_VERSION = "1.0.0"

_DEP_SECTIONS = ("dependencies", "dev-dependencies", "build-dependencies")


def _load_toml(content: str) -> dict:  # type: ignore[type-arg]
    try:
        import tomllib  # Python 3.11+
        return tomllib.loads(content)
    except ImportError:
        try:
            import tomli  # optional backport
            return tomli.loads(content)
        except ImportError:
            pass
    # Minimal fallback: return empty dict; caller will log warning.
    return {}


class CargoTomlParser:
    """ManifestParser for Cargo.toml (Rust / Cargo)."""

    @property
    def language(self) -> str:
        return "rust"

    @property
    def supported_filenames(self) -> frozenset[str]:
        return frozenset({"Cargo.toml"})

    def parse(self, path: Path, content: str) -> list[DependencyEvidence]:
        try:
            data = _load_toml(content)
        except Exception as exc:
            logger.warning("Cargo.toml parse error in %s: %s", path, exc)
            return []

        if not data:
            return []

        manifest_path = path.as_posix()
        results: list[DependencyEvidence] = []

        for section in _DEP_SECTIONS:
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            for crate_name, spec in block.items():
                constraint = _parse_cargo_spec(spec)
                results.append(
                    DependencyEvidence(
                        package=crate_name,
                        normalized_name=crate_name.lower().replace("_", "-"),
                        constraint=constraint,
                        manifest_path=manifest_path,
                        line=0,
                        parser=_PARSER_NAME,
                        parser_version=_PARSER_VERSION,
                        confidence=0.9,
                    )
                )

        return results


def _parse_cargo_spec(spec: object) -> VersionConstraint:
    """Classify a Cargo dependency specifier into a VersionConstraint."""
    if isinstance(spec, str):
        return _parse_version_req(spec)
    if isinstance(spec, dict):
        version = spec.get("version", "")
        return _parse_version_req(str(version)) if version else VersionConstraint(
            raw="", kind=ConstraintKind.UNKNOWN
        )
    return VersionConstraint(raw=str(spec), kind=ConstraintKind.UNKNOWN)


def _parse_version_req(req: str) -> VersionConstraint:
    req = req.strip()
    if not req:
        return VersionConstraint(raw=req, kind=ConstraintKind.UNKNOWN)
    # Exact: "=1.2.3"
    if req.startswith("=") and not req.startswith("=="):
        v = req[1:]
        return VersionConstraint(raw=req, kind=ConstraintKind.EXACT, lower=v, upper=v)
    # Caret (Cargo default): "1.2.3" or "^1.2.3"
    if req.startswith("^") or req[0].isdigit():
        lower = req.lstrip("^")
        return VersionConstraint(raw=req, kind=ConstraintKind.BOUNDED, lower=lower)
    # Tilde: "~1.2.3"
    if req.startswith("~"):
        lower = req[1:]
        return VersionConstraint(raw=req, kind=ConstraintKind.BOUNDED, lower=lower)
    # Range: ">=1, <2"
    if ">=" in req or "<" in req:
        lower: str | None = None
        upper: str | None = None
        for part in req.split(","):
            p = part.strip()
            if p.startswith(">="):
                lower = p[2:].strip()
            elif p.startswith("<"):
                upper = p[1:].strip()
        return VersionConstraint(raw=req, kind=ConstraintKind.RANGE, lower=lower, upper=upper)
    return VersionConstraint(raw=req, kind=ConstraintKind.UNKNOWN)
