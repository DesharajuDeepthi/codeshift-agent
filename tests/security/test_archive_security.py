"""
Security tests for SafeArchiveDownloader — all scenarios use in-memory archives.

Scenarios covered:
  7.  Corrupt archive — raises UpgradePilotError (not crash)
  8.  Path traversal — rejected before any byte hits disk
  9.  Symlink — rejected before any byte hits disk
  10. Oversized archive — compressed-size limit enforced during streaming
  11. File-count overflow — file-count limit enforced in first pass
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

import httpx
import pytest
import pytest_httpx

from upgradepilot.errors import SafetyLimitError, UpgradePilotError
from upgradepilot.tools.safe_archive import SafeArchiveDownloader, _is_safe_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tar_gz(members: list[tuple[str, bytes | None, int]]) -> bytes:
    """
    Build an in-memory .tar.gz.
    members: list of (name, content_bytes_or_None_for_dir, tarfile_type)
    """
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        inner = io.BytesIO()
        with tarfile.open(fileobj=inner, mode="w") as tf:
            for name, content, ttype in members:
                info = tarfile.TarInfo(name=name)
                info.type = ttype
                if content is not None:
                    info.size = len(content)
                    tf.addfile(info, io.BytesIO(content))
                else:
                    tf.addfile(info)
        gz.write(inner.getvalue())
    return buf.getvalue()


def _valid_archive() -> bytes:
    """A minimal valid archive with one file."""
    return _make_tar_gz(
        [
            ("owner-repo-abc123/", None, tarfile.DIRTYPE),
            ("owner-repo-abc123/main.py", b"print('hello')\n", tarfile.REGTYPE),
        ]
    )


def _make_downloader(
    tmp_path: Path,
    *,
    max_compressed: int = 100 * 1024 * 1024,
    max_extracted: int = 500 * 1024 * 1024,
    max_files: int = 10_000,
    max_depth: int = 20,
    max_single: int = 5 * 1024 * 1024,
    http_client: httpx.AsyncClient | None = None,
) -> SafeArchiveDownloader:
    return SafeArchiveDownloader(
        max_compressed_bytes=max_compressed,
        max_extracted_bytes=max_extracted,
        max_file_count=max_files,
        max_path_depth=max_depth,
        max_single_file_bytes=max_single,
        http_client=http_client,
        workspace_root=tmp_path,
    )


# ---------------------------------------------------------------------------
# Scenario 7: Corrupt archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupt_archive_raises_error(
    tmp_path: Path, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    corrupt = b"this is not a gzip stream at all"
    httpx_mock.add_response(
        url="https://codeload.github.com/owner/repo/tar.gz/abc123",
        content=corrupt,
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        dl = _make_downloader(tmp_path, http_client=http)
        with pytest.raises(UpgradePilotError):
            await dl.download_and_extract(
                url="https://codeload.github.com/owner/repo/tar.gz/abc123",
                headers={},
                analysis_id="test-corrupt",
            )


# ---------------------------------------------------------------------------
# Scenario 8: Path traversal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_traversal_rejected(tmp_path: Path, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    evil = _make_tar_gz(
        [
            ("repo-abc/", None, tarfile.DIRTYPE),
            ("repo-abc/../../etc/passwd", b"root:x:0:0\n", tarfile.REGTYPE),
        ]
    )
    httpx_mock.add_response(
        url="https://codeload.github.com/owner/repo/tar.gz/abc123",
        content=evil,
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        dl = _make_downloader(tmp_path, http_client=http)
        with pytest.raises(SafetyLimitError, match="(?i)traversal|unsafe|path"):
            await dl.download_and_extract(
                url="https://codeload.github.com/owner/repo/tar.gz/abc123",
                headers={},
                analysis_id="test-traversal",
            )


def test_is_safe_path_rejects_dotdot(tmp_path: Path) -> None:
    ok, reason = _is_safe_path("repo/../etc/passwd", tmp_path)
    assert not ok
    assert ".." in reason


def test_is_safe_path_rejects_absolute(tmp_path: Path) -> None:
    ok, reason = _is_safe_path("/etc/passwd", tmp_path)
    assert not ok
    assert "absolute" in reason.lower()


def test_is_safe_path_accepts_normal(tmp_path: Path) -> None:
    ok, _ = _is_safe_path("repo-abc/src/main.py", tmp_path)
    assert ok


# ---------------------------------------------------------------------------
# Scenario 9: Symlink rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_symlink_rejected(tmp_path: Path, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        inner = io.BytesIO()
        with tarfile.open(fileobj=inner, mode="w") as tf:
            # dir entry
            di = tarfile.TarInfo(name="repo-abc/")
            di.type = tarfile.DIRTYPE
            tf.addfile(di)
            # symlink entry
            si = tarfile.TarInfo(name="repo-abc/evil_link")
            si.type = tarfile.SYMTYPE
            si.linkname = "/etc/passwd"
            tf.addfile(si)
        gz.write(inner.getvalue())
    archive = buf.getvalue()

    httpx_mock.add_response(
        url="https://codeload.github.com/owner/repo/tar.gz/abc123",
        content=archive,
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        dl = _make_downloader(tmp_path, http_client=http)
        with pytest.raises(SafetyLimitError, match="(?i)symlink"):
            await dl.download_and_extract(
                url="https://codeload.github.com/owner/repo/tar.gz/abc123",
                headers={},
                analysis_id="test-symlink",
            )


# ---------------------------------------------------------------------------
# Scenario 10: Oversized compressed archive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_compressed_rejected(
    tmp_path: Path, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    # 10 bytes of real archive content, but limit is 5 bytes
    archive = _valid_archive()
    httpx_mock.add_response(
        url="https://codeload.github.com/owner/repo/tar.gz/abc123",
        content=archive,
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        # max_compressed = 5 bytes — guaranteed to trigger
        dl = _make_downloader(tmp_path, max_compressed=5, http_client=http)
        with pytest.raises(SafetyLimitError, match="(?i)compress|limit|exceed"):
            await dl.download_and_extract(
                url="https://codeload.github.com/owner/repo/tar.gz/abc123",
                headers={},
                analysis_id="test-oversize",
            )


# ---------------------------------------------------------------------------
# Scenario 11: File-count overflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_count_overflow_rejected(
    tmp_path: Path, httpx_mock: pytest_httpx.HTTPXMock
) -> None:
    members: list[tuple[str, bytes | None, int]] = [
        ("repo-abc/", None, tarfile.DIRTYPE),
    ]
    for i in range(5):
        members.append((f"repo-abc/file{i}.py", b"x = 1\n", tarfile.REGTYPE))
    archive = _make_tar_gz(members)

    httpx_mock.add_response(
        url="https://codeload.github.com/owner/repo/tar.gz/abc123",
        content=archive,
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        # max_files = 3 — archive has 5 files
        dl = _make_downloader(tmp_path, max_files=3, http_client=http)
        with pytest.raises(SafetyLimitError, match="(?i)file|count|more than"):
            await dl.download_and_extract(
                url="https://codeload.github.com/owner/repo/tar.gz/abc123",
                headers={},
                analysis_id="test-filecount",
            )


# ---------------------------------------------------------------------------
# Happy path: valid archive extracts correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_archive_extracts(tmp_path: Path, httpx_mock: pytest_httpx.HTTPXMock) -> None:
    archive = _valid_archive()
    httpx_mock.add_response(
        url="https://codeload.github.com/owner/repo/tar.gz/abc123",
        content=archive,
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        dl = _make_downloader(tmp_path, http_client=http)
        result = await dl.download_and_extract(
            url="https://codeload.github.com/owner/repo/tar.gz/abc123",
            headers={},
            analysis_id="test-valid",
        )

    assert result.file_count == 1
    assert result.compressed_bytes == len(archive)
    assert len(result.archive_sha256) == 64
    assert (result.workspace_path / "main.py").exists()


# ---------------------------------------------------------------------------
# HTTPS enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_url_rejected(tmp_path: Path) -> None:
    dl = _make_downloader(tmp_path)
    with pytest.raises(SafetyLimitError, match="(?i)https"):
        await dl.download_and_extract(
            url="http://codeload.github.com/owner/repo/tar.gz/abc",
            headers={},
            analysis_id="test-http",
        )
