"""Tests for repository acquisition graph node behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from upgradepilot.graph.nodes.acquisition import acquire_repository
from upgradepilot.graph.state import AnalysisStatus, make_initial_state
from upgradepilot.tools.safe_archive import ArchiveExtractionResult


@pytest.mark.asyncio
async def test_standard_acquisition_resolves_ref_and_extracts_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, object] = {}
    sha = "d" * 40

    class FakeGitHubClient:
        def __init__(
            self,
            *,
            token: str | None,
            timeout_seconds: int,
            max_retries: int,
        ) -> None:
            calls["github_init"] = {
                "token": token,
                "timeout_seconds": timeout_seconds,
                "max_retries": max_retries,
            }
            self._token = token

        async def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            calls["metadata"] = (owner, repo)
            return {"full_name": f"{owner}/{repo}", "private": False}

        async def resolve_ref(self, owner: str, repo: str, ref: str) -> str:
            calls["resolve"] = (owner, repo, ref)
            return sha

        async def get_archive_url(self, owner: str, repo: str, resolved_sha: str) -> str:
            calls["archive_url"] = (owner, repo, resolved_sha)
            return f"https://codeload.github.com/{owner}/{repo}/tar.gz/{resolved_sha}"

        def get_archive_download_headers(self) -> dict[str, str]:
            return {"Authorization": f"Bearer {self._token}"}

    class FakeDownloader:
        def __init__(self, **kwargs: int) -> None:
            calls["limits"] = kwargs

        async def download_and_extract(
            self,
            *,
            url: str,
            headers: dict[str, str],
            analysis_id: str,
        ) -> ArchiveExtractionResult:
            calls["download"] = {"url": url, "headers": headers, "analysis_id": analysis_id}
            return ArchiveExtractionResult(
                workspace_path=tmp_path / analysis_id / "repo",
                archive_sha256="e" * 64,
                compressed_bytes=123,
                extracted_bytes=456,
                file_count=2,
                max_depth=3,
            )

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")
    monkeypatch.setenv("GITHUB_API_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("GITHUB_MAX_RETRIES", "1")
    monkeypatch.setattr("upgradepilot.tools.github.GitHubClient", FakeGitHubClient)
    monkeypatch.setattr("upgradepilot.tools.safe_archive.SafeArchiveDownloader", FakeDownloader)

    state = make_initial_state(
        analysis_id="analysis-standard",
        request_data={
            "repository_url": "https://github.com/pydantic/pydantic",
            "ref": "v1.10.15",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "standard",
            "request_id": "acquisition-test",
            "github_owner": "pydantic",
            "github_repo": "pydantic",
        },
    )

    result = await acquire_repository(state)

    assert result["snapshot"]["owner"] == "pydantic"
    assert result["snapshot"]["repo"] == "pydantic"
    assert result["snapshot"]["resolved_commit_sha"] == sha
    assert result["snapshot"]["archive_sha256"] == "e" * 64
    assert result["snapshot"]["workspace_path"].endswith("/analysis-standard/repo")
    assert result["snapshot"]["safety_limits"]["actual_file_count"] == 2
    assert result["node_executions"][0]["status"] == "completed"
    assert calls["metadata"] == ("pydantic", "pydantic")
    assert calls["resolve"] == ("pydantic", "pydantic", "v1.10.15")
    assert calls["archive_url"] == ("pydantic", "pydantic", sha)
    assert calls["download"] == {
        "url": f"https://codeload.github.com/pydantic/pydantic/tar.gz/{sha}",
        "headers": {"Authorization": "Bearer ghp_testtoken"},
        "analysis_id": "analysis-standard",
    }
    assert "status" not in result or result["status"] != AnalysisStatus.TERMINAL
