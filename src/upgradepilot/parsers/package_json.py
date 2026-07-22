"""
package.json manifest parser for JavaScript / TypeScript projects.

Parses dependencies, devDependencies, and peerDependencies sections.
Semver ranges are classified into VersionConstraint kinds using simple heuristics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from upgradepilot.models.profile import ConstraintKind, DependencyEvidence, VersionConstraint

logger = logging.getLogger(__name__)

_PARSER_NAME = "package_json"
_PARSER_VERSION = "1.0.0"

_DEP_SECTIONS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")


class PackageJsonParser:
    """ManifestParser for package.json (npm / yarn / pnpm)."""

    @property
    def language(self) -> str:
        return "typescript"

    @property
    def supported_filenames(self) -> frozenset[str]:
        return frozenset({"package.json"})

    def parse(self, path: Path, content: str) -> list[DependencyEvidence]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("package.json parse error in %s: %s", path, exc)
            return []

        if not isinstance(data, dict):
            return []

        manifest_path = path.as_posix()
        results: list[DependencyEvidence] = []

        for section in _DEP_SECTIONS:
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            for pkg_name, version_spec in block.items():
                if not isinstance(version_spec, str):
                    continue
                constraint = _parse_semver_range(version_spec)
                results.append(
                    DependencyEvidence(
                        package=pkg_name,
                        normalized_name=pkg_name.lower().replace("_", "-"),
                        constraint=constraint,
                        manifest_path=manifest_path,
                        line=0,  # JSON has no meaningful line numbers without extra work
                        parser=_PARSER_NAME,
                        parser_version=_PARSER_VERSION,
                        confidence=0.95,
                    )
                )

        return results


def _parse_semver_range(spec: str) -> VersionConstraint:
    """Classify a npm semver range string into a VersionConstraint."""
    spec = spec.strip()

    if not spec or spec in ("*", "latest", "x"):
        return VersionConstraint(raw=spec, kind=ConstraintKind.UNPINNED)

    # Exact: "1.2.3" or "=1.2.3"
    if spec.lstrip("=").replace(".", "").isdigit():
        version = spec.lstrip("=")
        return VersionConstraint(raw=spec, kind=ConstraintKind.EXACT, lower=version, upper=version)

    # Caret: ^1.2.3 — compatible with 1.x
    if spec.startswith("^"):
        lower = spec[1:].split("-")[0]
        return VersionConstraint(raw=spec, kind=ConstraintKind.BOUNDED, lower=lower)

    # Tilde: ~1.2.3 — patch-compatible
    if spec.startswith("~"):
        lower = spec[1:].split("-")[0]
        return VersionConstraint(raw=spec, kind=ConstraintKind.BOUNDED, lower=lower)

    # Range: ">=1.0.0 <2.0.0"
    if ">=" in spec or "<=" in spec or ">" in spec or "<" in spec:
        lower: str | None = None
        upper: str | None = None
        for part in spec.split():
            part = part.strip()
            if part.startswith(">="):
                lower = part[2:]
            elif part.startswith(">"):
                lower = part[1:]
            elif part.startswith("<="):
                upper = part[2:]
            elif part.startswith("<"):
                upper = part[1:]
        return VersionConstraint(raw=spec, kind=ConstraintKind.RANGE, lower=lower, upper=upper)

    return VersionConstraint(raw=spec, kind=ConstraintKind.UNKNOWN)
