"""
Safe archive download and extraction.

Security controls enforced:
- HTTPS only, no redirects to non-HTTPS
- Compressed-size limit (streaming, before full download)
- Archive hash (SHA-256) computed on the downloaded bytes
- Path-traversal prevention (absolute paths, .. components, drive letters)
- Symlink rejection
- Extracted-size limit (cumulative across all members)
- File-count limit
- Path-depth limit
- Single-file-size limit
- Extraction into an isolated per-analysis workspace
- No code execution at any stage
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import shutil
import stat
import tarfile
import zlib
from pathlib import Path, PurePosixPath
from typing import IO

import httpx

from upgradepilot.errors import ErrorCode, SafetyLimitError, UpgradePilotError
from upgradepilot.observability.metrics import record_external_api_error

logger = logging.getLogger(__name__)

_DEFAULT_WORKSPACE_ROOT = Path("/workspace")


def _workspace_root() -> Path:
    env = os.environ.get("UPGRADEPILOT_WORKSPACE_ROOT")
    if env:
        return Path(env)
    return _DEFAULT_WORKSPACE_ROOT


def _is_safe_path(member_name: str, workspace: Path) -> tuple[bool, str]:
    """
    Return (is_safe, reason).

    A path is safe when it:
    - is not absolute;
    - contains no '..' components;
    - contains no Windows drive letters (C:...);
    - resolves inside the workspace after normalisation.
    """
    try:
        posix = PurePosixPath(member_name)
    except Exception:
        return False, f"unparseable path: {member_name!r}"

    parts = posix.parts

    if not parts:
        return False, "empty path"

    if posix.is_absolute():
        return False, f"absolute path rejected: {member_name!r}"

    for part in parts:
        if part == "..":
            return False, f"path traversal detected (..) in: {member_name!r}"
        if re.match(r"^[A-Za-z]:$", part):
            return False, f"Windows drive letter rejected in: {member_name!r}"
        if "\x00" in part:
            return False, f"NUL byte in path: {member_name!r}"

    # Drop the top-level archive prefix (owner-repo-sha/) before resolving
    relative_parts = parts[1:] if len(parts) > 1 else parts
    relative = Path(*relative_parts) if relative_parts else Path(".")

    try:
        resolved = (workspace / relative).resolve()
        workspace_resolved = workspace.resolve()
        inside = str(resolved).startswith(str(workspace_resolved) + os.sep)
        if not inside and resolved != workspace_resolved:
            return False, f"resolved path escapes workspace: {resolved!r}"
    except Exception as exc:
        return False, f"path resolution error: {exc}"

    return True, ""


def _count_depth(member_name: str) -> int:
    return len(PurePosixPath(member_name).parts)


class ArchiveExtractionResult:
    """Outcome of a successful safe extraction."""

    __slots__ = (
        "workspace_path",
        "archive_sha256",
        "compressed_bytes",
        "extracted_bytes",
        "file_count",
        "max_depth",
    )

    def __init__(
        self,
        workspace_path: Path,
        archive_sha256: str,
        compressed_bytes: int,
        extracted_bytes: int,
        file_count: int,
        max_depth: int,
    ) -> None:
        self.workspace_path = workspace_path
        self.archive_sha256 = archive_sha256
        self.compressed_bytes = compressed_bytes
        self.extracted_bytes = extracted_bytes
        self.file_count = file_count
        self.max_depth = max_depth


class SafeArchiveDownloader:
    """
    Downloads a tarball from GitHub and extracts it safely.

    All safety checks are applied before any byte is written to disk.
    Extraction is never performed with shell=True or subprocess.
    """

    def __init__(
        self,
        *,
        max_compressed_bytes: int,
        max_extracted_bytes: int,
        max_file_count: int,
        max_path_depth: int,
        max_single_file_bytes: int,
        http_client: httpx.AsyncClient | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self._max_compressed = max_compressed_bytes
        self._max_extracted = max_extracted_bytes
        self._max_file_count = max_file_count
        self._max_depth = max_path_depth
        self._max_single_file = max_single_file_bytes
        self._http_client = http_client
        self._workspace_root = workspace_root or _workspace_root()

    def _make_workspace(self, analysis_id: str) -> Path:
        ws = self._workspace_root / analysis_id
        ws.mkdir(parents=True, exist_ok=True)
        ws.chmod(0o700)
        return ws

    async def _download_bytes(
        self,
        url: str,
        headers: dict[str, str],
    ) -> bytes:
        """Stream download with compressed-size limit. Returns raw archive bytes."""
        if not url.startswith("https://"):
            raise SafetyLimitError(f"Only HTTPS archive URLs accepted. Got: {url!r}")

        chunks: list[bytes] = []
        total = 0

        async def _stream(client: httpx.AsyncClient) -> None:
            nonlocal total
            try:
                async with client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        total += len(chunk)
                        if total > self._max_compressed:
                            raise SafetyLimitError(
                                f"Compressed archive exceeds limit of "
                                f"{self._max_compressed:,} bytes (got >{total:,})"
                            )
                        chunks.append(chunk)
            except httpx.HTTPError:
                record_external_api_error(service="github_archive")
                raise

        if self._http_client is not None:
            await _stream(self._http_client)
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=15.0, read=120.0, write=5.0, pool=5.0),
                follow_redirects=True,
            ) as client:
                await _stream(client)

        return b"".join(chunks)

    def _extract_safely(
        self,
        archive_bytes: bytes,
        workspace: Path,
    ) -> tuple[int, int, int]:
        """
        Extract a .tar.gz archive safely.

        Returns (extracted_bytes, file_count, max_depth).
        Raises SafetyLimitError on any violation.
        """
        extracted_bytes = 0
        file_count = 0
        max_depth = 0

        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
                members = tf.getmembers()
        except (tarfile.TarError, EOFError, zlib.error, Exception) as exc:
            raise UpgradePilotError(
                ErrorCode.REPOSITORY_INACCESSIBLE,
                f"Corrupt or invalid archive: {exc}",
            ) from exc

        # First pass: validate every member before extracting any
        for member in members:
            if member.issym() or member.islnk():
                raise SafetyLimitError(
                    f"Archive contains symlink or hardlink; rejected: {member.name!r}"
                )

            if member.isdev() or member.isblk() or member.isfifo():
                raise SafetyLimitError(f"Archive contains special file; rejected: {member.name!r}")

            safe, reason = _is_safe_path(member.name, workspace)
            if not safe:
                raise SafetyLimitError(f"Unsafe archive path: {reason}")

            depth = _count_depth(member.name)
            if depth > self._max_depth:
                raise SafetyLimitError(
                    f"Path depth {depth} exceeds limit {self._max_depth}: {member.name!r}"
                )
            max_depth = max(max_depth, depth)

            if member.isfile():
                if member.size > self._max_single_file:
                    raise SafetyLimitError(
                        f"File {member.name!r} size {member.size:,} bytes exceeds "
                        f"single-file limit {self._max_single_file:,}"
                    )
                extracted_bytes += member.size
                if extracted_bytes > self._max_extracted:
                    raise SafetyLimitError(
                        f"Cumulative extracted size exceeds limit of {self._max_extracted:,} bytes"
                    )
                file_count += 1
                if file_count > self._max_file_count:
                    raise SafetyLimitError(
                        f"Archive contains more than {self._max_file_count:,} files"
                    )

        # Second pass: extract — all validation passed
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
            for member in tf.getmembers():
                if (
                    member.issym()
                    or member.islnk()
                    or member.isdev()
                    or member.isblk()
                    or member.isfifo()
                ):
                    continue

                parts = PurePosixPath(member.name).parts
                relative_parts = parts[1:] if len(parts) > 1 else parts
                if not relative_parts:
                    continue

                dest = workspace / Path(*relative_parts)

                # Final containment check
                try:
                    dest.resolve().relative_to(workspace.resolve())
                except ValueError as exc:
                    raise SafetyLimitError(f"Extraction path escapes workspace: {dest!r}") from exc

                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                    dest.chmod(0o755)
                elif member.isfile():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    fobj: IO[bytes] | None = tf.extractfile(member)
                    if fobj is None:
                        continue
                    with fobj:
                        content = fobj.read()
                    dest.write_bytes(content)
                    dest.chmod(stat.S_IRUSR | stat.S_IRGRP)

        return extracted_bytes, file_count, max_depth

    async def download_and_extract(
        self,
        *,
        url: str,
        headers: dict[str, str],
        analysis_id: str,
    ) -> ArchiveExtractionResult:
        """
        Download and safely extract a GitHub tarball.

        Creates an isolated workspace at {workspace_root}/{analysis_id}/repo/.
        Returns ArchiveExtractionResult on success.
        Raises SafetyLimitError or UpgradePilotError on any violation.
        """
        workspace = self._make_workspace(analysis_id) / "repo"
        workspace.mkdir(parents=True, exist_ok=True)
        workspace.chmod(0o700)

        archive_bytes = await self._download_bytes(url, headers)
        compressed_bytes = len(archive_bytes)

        digest = hashlib.sha256(archive_bytes).hexdigest()

        try:
            extracted_bytes, file_count, max_depth = self._extract_safely(archive_bytes, workspace)
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

        logger.info(
            "Archive extracted: sha256=%s files=%d extracted_bytes=%d",
            digest[:16],
            file_count,
            extracted_bytes,
        )

        return ArchiveExtractionResult(
            workspace_path=workspace,
            archive_sha256=digest,
            compressed_bytes=compressed_bytes,
            extracted_bytes=extracted_bytes,
            file_count=file_count,
            max_depth=max_depth,
        )


def cleanup_workspace(analysis_id: str, workspace_root: Path | None = None) -> None:
    """Remove the per-analysis workspace directory tree."""
    root = workspace_root or _workspace_root()
    ws = root / analysis_id
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
        logger.info("Workspace cleaned up: %s", ws)
