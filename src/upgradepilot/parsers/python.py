"""
Python manifest parser — wraps the existing analyzers/manifest_parser.py logic
behind the ManifestParser protocol so it is accessible through the registry.
"""

from __future__ import annotations

from pathlib import Path

from upgradepilot.analyzers.manifest_parser import (
    parse_pyproject_toml,
    parse_requirements_txt,
)
from upgradepilot.models.profile import DependencyEvidence


class PythonManifestParser:
    """ManifestParser for Python requirement files and pyproject.toml."""

    @property
    def language(self) -> str:
        return "python"

    @property
    def supported_filenames(self) -> frozenset[str]:
        return frozenset(
            {
                "requirements.txt",
                "requirements-dev.txt",
                "requirements_dev.txt",
                "requirements-test.txt",
                "requirements_test.txt",
                "requirements-prod.txt",
                "requirements_prod.txt",
                "dev-requirements.txt",
                "test-requirements.txt",
                "pyproject.toml",
                "setup.cfg",
            }
        )

    def parse(self, path: Path, content: str) -> list[DependencyEvidence]:
        # Both parse_* functions take (content: str, manifest_path: str) and
        # return tuples; we discard error lists and runtime declarations here
        # since the ManifestParser protocol only returns DependencyEvidence.
        manifest_path = path.as_posix()
        name = path.name.lower()
        if name == "pyproject.toml":
            deps, _errors, _runtime = parse_pyproject_toml(content, manifest_path)
            return deps
        deps, _errors = parse_requirements_txt(content, manifest_path)
        return deps
