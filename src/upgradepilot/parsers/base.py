"""
Protocol definition for language-specific manifest parsers.

Every parser must satisfy ManifestParser.  The registry in parsers/registry.py
maps manifest filenames to parser implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from upgradepilot.models.profile import DependencyEvidence


@runtime_checkable
class ManifestParser(Protocol):
    """
    Protocol for deterministic, read-only manifest file parsers.

    Implementations must:
    - Never execute manifest code or invoke package managers.
    - Return an empty list (not raise) for empty or unrecognised manifests.
    - Be safe to instantiate multiple times (stateless).
    """

    @property
    def language(self) -> str:
        """Canonical lower-case language this parser serves (e.g. 'python')."""
        ...

    @property
    def supported_filenames(self) -> frozenset[str]:
        """
        Exact filenames (not paths) this parser can handle.

        The registry matches on ``Path(manifest).name`` so patterns like
        ``requirements*.txt`` are not supported — use glob matching in the
        registry if needed.
        """
        ...

    def parse(self, path: Path, content: str) -> list[DependencyEvidence]:
        """
        Parse a manifest file and return a list of dependency entries.

        Parameters
        ----------
        path:
            Absolute path to the manifest file (for error messages and the
            manifest_path field of DependencyEvidence records).
        content:
            Full UTF-8 text of the manifest file.

        Returns
        -------
        list[DependencyEvidence]
            Zero or more dependency entries.  Parse errors are captured in the
            DependencyEvidence.parse_error field rather than being raised.
        """
        ...
