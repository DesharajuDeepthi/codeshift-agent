"""
Per-analysis workspace lifecycle management.

Each analysis gets an isolated directory under UPGRADEPILOT_WORKSPACE_ROOT.
The workspace is never shared between analyses and is removed after use.
"""

from __future__ import annotations

import logging
from pathlib import Path

from upgradepilot.tools.safe_archive import _workspace_root, cleanup_workspace

logger = logging.getLogger(__name__)


class Workspace:
    """Context-manager for a per-analysis workspace directory."""

    def __init__(self, analysis_id: str, workspace_root: Path | None = None) -> None:
        self._analysis_id = analysis_id
        self._root = workspace_root or _workspace_root()
        self._path = self._root / analysis_id

    @property
    def path(self) -> Path:
        return self._path

    def create(self) -> Path:
        self._path.mkdir(parents=True, exist_ok=True)
        self._path.chmod(0o700)
        logger.debug("Workspace created: %s", self._path)
        return self._path

    def cleanup(self) -> None:
        cleanup_workspace(self._analysis_id, self._root)

    def __enter__(self) -> Workspace:
        self.create()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()
