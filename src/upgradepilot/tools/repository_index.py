"""
Repository file index with bounded reads.

Builds a metadata index of files in an extracted workspace.
Never executes repository code. Never writes to the workspace.
Line reads are bounded by MAX_LINES_PER_FILE.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_LINES_PER_FILE = 2000
MAX_INDEX_FILES = 10_000

# Extensions we index; everything else is noted but content is not read
_TEXT_EXTENSIONS = frozenset(
    {
        ".py",
        ".txt",
        ".md",
        ".rst",
        ".toml",
        ".cfg",
        ".ini",
        ".yaml",
        ".yml",
        ".json",
        ".lock",
        ".in",
        ".setup",
        ".dockerfile",
        "",  # files with no extension (Dockerfile, Makefile, etc.)
    }
)


class FileEntry(BaseModel):
    model_config = {"frozen": True}

    relative_path: str
    size_bytes: int
    extension: str
    lines_read: int
    truncated: bool


class RepositoryIndex(BaseModel):
    model_config = {"frozen": True}

    workspace_path: str
    total_files: int
    indexed_files: int
    entries: list[FileEntry] = Field(default_factory=list)
    skipped_count: int = 0


def build_index(workspace: Path, *, max_files: int = MAX_INDEX_FILES) -> RepositoryIndex:
    """
    Walk the workspace and build a metadata index.

    Files are listed but content is not retained in the index itself —
    use read_bounded_lines() separately when content is needed.
    """
    entries: list[FileEntry] = []
    total_files = 0
    skipped = 0

    for fpath in sorted(workspace.rglob("*")):
        if not fpath.is_file():
            continue

        total_files += 1
        if total_files > max_files:
            skipped += 1
            continue

        rel = fpath.relative_to(workspace)
        ext = fpath.suffix.lower()
        size = fpath.stat().st_size

        entries.append(
            FileEntry(
                relative_path=str(rel),
                size_bytes=size,
                extension=ext,
                lines_read=0,
                truncated=False,
            )
        )

    logger.debug(
        "Repository indexed: total=%d indexed=%d skipped=%d",
        total_files,
        len(entries),
        skipped,
    )

    return RepositoryIndex(
        workspace_path=str(workspace),
        total_files=total_files,
        indexed_files=len(entries),
        entries=entries,
        skipped_count=skipped,
    )


def read_bounded_lines(
    file_path: Path,
    *,
    max_lines: int = MAX_LINES_PER_FILE,
    max_bytes: int = 5 * 1024 * 1024,
) -> tuple[list[str], bool]:
    """
    Read up to max_lines lines from a file.

    Returns (lines, truncated). Never raises on encoding errors —
    uses replace error handler so hostile filenames or binary files
    are handled gracefully rather than crashing the analysis.
    """
    lines: list[str] = []
    truncated = False
    bytes_read = 0

    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                bytes_read += len(line.encode("utf-8", errors="replace"))
                if bytes_read > max_bytes:
                    truncated = True
                    break
                lines.append(line.rstrip("\n"))
                if len(lines) >= max_lines:
                    # Check whether there's more content
                    if fh.read(1):
                        truncated = True
                    break
    except OSError as exc:
        logger.warning("Could not read file %s: %s", file_path, exc)
        return [], False

    return lines, truncated
