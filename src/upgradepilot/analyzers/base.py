"""
Protocol definition for language-specific code analyzers.

Every analyzer must satisfy LanguageAnalyzer.  The pack's analyzer_kind field
selects the implementation via the registry in analyzers/registry.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from upgradepilot.migration.models import LoadedMigrationPack
    from upgradepilot.models.finding import ScanResult

# Canonical kind identifiers — used in pack.yaml and the registry.
ANALYZER_KIND_PYTHON_AST = "python-ast"
ANALYZER_KIND_REGEX = "regex"


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """
    Protocol for deterministic, read-only source-code analyzers.

    Implementations must:
    - Never execute analyzed code.
    - Never write to the workspace.
    - Return a ScanResult regardless of how many files fail to parse.
    - Be safe to instantiate multiple times (stateless).
    """

    @property
    def analyzer_kind(self) -> str:
        """The kind identifier this implementation handles."""
        ...

    def scan(self, workspace: Path, pack: LoadedMigrationPack) -> ScanResult:
        """
        Walk workspace and apply pack detection rules to all relevant files.

        Parameters
        ----------
        workspace:
            Root of the extracted repository; must exist and be a directory.
        pack:
            Fully loaded and validated migration pack.  Detection rules,
            false-positive exclusions, and confidence thresholds are read
            from this object.

        Returns
        -------
        ScanResult
            All findings and scan metadata.  An empty findings list is valid.
        """
        ...
