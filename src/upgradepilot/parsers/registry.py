"""
Manifest parser registry.

Maps manifest filenames to ManifestParser implementations.  Supports both
exact-name matching and suffix/prefix glob patterns.

Usage
-----
    from upgradepilot.parsers.registry import parse_manifest, get_parser_for_file

    deps = parse_manifest(Path("/repo/package.json"))
    parser = get_parser_for_file(Path("/repo/requirements.txt"))
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from upgradepilot.parsers.base import ManifestParser

if TYPE_CHECKING:
    from upgradepilot.models.profile import DependencyEvidence

logger = logging.getLogger(__name__)

# Exact name → parser class
_EXACT: dict[str, type[ManifestParser]] = {}
# Compiled regex → parser class (checked after exact match fails)
_PATTERNS: list[tuple[re.Pattern[str], type[ManifestParser]]] = []


def register_parser(impl: type[ManifestParser]) -> None:
    """Register a ManifestParser by its supported_filenames and any patterns."""
    instance = impl()
    for name in instance.supported_filenames:
        if name in _EXACT:
            logger.warning("Overwriting existing parser for filename %r", name)
        _EXACT[name] = impl
        logger.debug("Registered parser %s for filename %r", impl.__name__, name)


def register_pattern_parser(pattern: str, impl: type[ManifestParser]) -> None:
    """Register a ManifestParser for filenames matching a regex pattern."""
    compiled = re.compile(pattern, re.IGNORECASE)
    _PATTERNS.append((compiled, impl))
    logger.debug("Registered pattern parser %s for pattern %r", impl.__name__, pattern)


def get_parser_for_file(path: Path) -> ManifestParser | None:
    """
    Return a parser instance for the given manifest path, or None if unknown.

    Tries exact filename match first, then regex patterns.
    """
    name = path.name
    if name in _EXACT:
        return _EXACT[name]()
    for pattern, impl in _PATTERNS:
        if pattern.fullmatch(name):
            return impl()
    return None


def parse_manifest(path: Path) -> list[DependencyEvidence]:
    """
    Parse a manifest file, returning dependency evidence.

    Returns an empty list (not raises) if no parser is registered for the file.
    """
    parser = get_parser_for_file(path)
    if parser is None:
        logger.debug("No parser registered for %s — skipping", path.name)
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return parser.parse(path, content)
    except Exception as exc:
        logger.warning("Parser %s failed on %s: %s", type(parser).__name__, path, exc)
        return []


def registered_languages() -> list[str]:
    """Return all languages for which at least one parser is registered."""
    langs: set[str] = set()
    for impl in _EXACT.values():
        langs.add(impl().language)
    for _, impl in _PATTERNS:
        langs.add(impl().language)
    return sorted(langs)


# ---------------------------------------------------------------------------
# Built-in registration
# ---------------------------------------------------------------------------


def _register_defaults() -> None:
    from upgradepilot.parsers.cargo_toml import CargoTomlParser
    from upgradepilot.parsers.go_mod import GoModParser
    from upgradepilot.parsers.package_json import PackageJsonParser
    from upgradepilot.parsers.python import PythonManifestParser

    register_parser(PythonManifestParser)
    register_parser(PackageJsonParser)
    register_parser(CargoTomlParser)
    register_parser(GoModParser)

    # requirements*.txt pattern (not just requirements.txt)
    register_pattern_parser(r"requirements.*\.txt", PythonManifestParser)


_register_defaults()
