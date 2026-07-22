"""
go.mod manifest parser for Go projects.

Parses the require directives from a go.mod file.
Does not resolve indirect dependencies or handle replace directives.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from upgradepilot.models.profile import ConstraintKind, DependencyEvidence, VersionConstraint

logger = logging.getLogger(__name__)

_PARSER_NAME = "go_mod"
_PARSER_VERSION = "1.0.0"

# Matches:  require module/path v1.2.3
_SINGLE_RE = re.compile(r"^\s*require\s+([\w./\-]+)\s+(v[\w.\-+]+)", re.MULTILINE)
# Matches lines inside a require ( ... ) block
_BLOCK_LINE_RE = re.compile(r"^\s+([\w./\-]+)\s+(v[\w.\-+]+)", re.MULTILINE)
_BLOCK_RE = re.compile(r"require\s*\(([^)]*)\)", re.DOTALL)


class GoModParser:
    """ManifestParser for go.mod (Go modules)."""

    @property
    def language(self) -> str:
        return "go"

    @property
    def supported_filenames(self) -> frozenset[str]:
        return frozenset({"go.mod"})

    def parse(self, path: Path, content: str) -> list[DependencyEvidence]:
        manifest_path = path.as_posix()
        results: list[DependencyEvidence] = []
        seen: set[str] = set()

        def _add(module: str, version: str, line_no: int) -> None:
            key = (module, version)
            if key in seen:
                return
            seen.add(key)
            results.append(
                DependencyEvidence(
                    package=module,
                    normalized_name=module.lower(),
                    constraint=_parse_go_version(version),
                    manifest_path=manifest_path,
                    line=line_no,
                    parser=_PARSER_NAME,
                    parser_version=_PARSER_VERSION,
                    confidence=0.95,
                )
            )

        # Single-line require statements
        for match in _SINGLE_RE.finditer(content):
            line_no = content[: match.start()].count("\n") + 1
            _add(match.group(1), match.group(2), line_no)

        # Block require statements
        for block_match in _BLOCK_RE.finditer(content):
            block_start_line = content[: block_match.start()].count("\n") + 1
            for line_match in _BLOCK_LINE_RE.finditer(block_match.group(1)):
                offset = block_match.group(1)[: line_match.start()].count("\n")
                line_no = block_start_line + offset + 1
                _add(line_match.group(1), line_match.group(2), line_no)

        return results


def _parse_go_version(version: str) -> VersionConstraint:
    """Go modules use exact pseudo-versions or tagged versions."""
    v = version.lstrip("v")
    # Pseudo-version: vX.Y.Z-YYYYMMDDHHMMSS-abcdef012345
    if "-" in v and len(v) > 20:
        return VersionConstraint(raw=version, kind=ConstraintKind.EXACT, lower=v, upper=v)
    # Tagged: v1.2.3
    return VersionConstraint(raw=version, kind=ConstraintKind.EXACT, lower=v, upper=v)
