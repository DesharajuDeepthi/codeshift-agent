"""
acquire_repository node.

Downloads the repository archive, extracts it to a workspace, and records
the immutable snapshot.  In FIXTURE mode, returns a canned snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from upgradepilot.graph.nodes._helpers import (
    _now,
    graph_error,
    is_fixture,
    node_error_record,
    node_record,
)
from upgradepilot.graph.state import (
    FIXTURE_ACQUISITION_FAILURE,
    AnalysisStatus,
    UpgradePilotState,
)
from upgradepilot.models.snapshot import RepositorySnapshot, SafetyLimitsApplied

_NODE = "acquire_repository"


def _fixture_snapshot(state: UpgradePilotState) -> dict[str, Any]:
    """Return a minimal deterministic snapshot for FIXTURE mode."""
    req = state["request_data"]
    owner = req.get("github_owner", "test-owner")
    repo = req.get("github_repo", "test-repo")
    return RepositorySnapshot(
        owner=owner,
        repo=repo,
        requested_ref=req.get("ref", "main"),
        resolved_commit_sha="a" * 40,
        archive_sha256="b" * 64,
        workspace_path=f"/tmp/upgradepilot/{state['analysis_id']}",  # noqa: S108
        acquired_at=datetime(2024, 1, 1, tzinfo=UTC),
        safety_limits=SafetyLimitsApplied(
            max_compressed_bytes=100_000_000,
            max_extracted_bytes=500_000_000,
            max_file_count=10_000,
            max_path_depth=20,
            max_single_file_bytes=5_000_000,
            actual_file_count=42,
        ),
    ).model_dump()


async def acquire_repository(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        if state.get("fixture_scenario") == FIXTURE_ACQUISITION_FAILURE:
            return {
                "status": AnalysisStatus.TERMINAL,
                "node_executions": [node_error_record(_NODE, started, "REPOSITORY_INACCESSIBLE")],
                "errors": [
                    graph_error(_NODE, "REPOSITORY_INACCESSIBLE", "Repository not found (fixture)")
                ],
            }
        return {
            "snapshot": _fixture_snapshot(state),
            "node_executions": [node_record(_NODE, started)],
        }

    # ── STANDARD mode: call real GitHub service ────────────────────────────
    from upgradepilot.config import get_settings
    from upgradepilot.errors import RepositoryInaccessibleError, SafetyLimitError
    from upgradepilot.models.request import AnalysisRequest
    from upgradepilot.models.snapshot import RepositorySnapshot, SafetyLimitsApplied
    from upgradepilot.tools.github import GitHubClient
    from upgradepilot.tools.safe_archive import SafeArchiveDownloader

    settings = get_settings()
    req = AnalysisRequest.model_validate(state["request_data"])

    try:
        gh = GitHubClient(
            token=settings.github_token.get_secret_value() if settings.github_token else None,
            timeout_seconds=settings.github_api_timeout_seconds,
            max_retries=settings.github_max_retries,
        )
        await gh.get_repo_metadata(req.github_owner, req.github_repo)
        sha = await gh.resolve_ref(req.github_owner, req.github_repo, req.ref)
        archive_url = await gh.get_archive_url(req.github_owner, req.github_repo, sha)

        downloader = SafeArchiveDownloader(
            max_compressed_bytes=settings.max_archive_compressed_bytes,
            max_extracted_bytes=settings.max_archive_extracted_bytes,
            max_file_count=settings.max_archive_file_count,
            max_path_depth=settings.max_path_depth,
            max_single_file_bytes=settings.max_single_file_bytes,
        )
        result = await downloader.download_and_extract(
            url=archive_url,
            headers=gh.get_archive_download_headers(),
            analysis_id=state["analysis_id"],
        )

        snapshot = RepositorySnapshot(
            owner=req.github_owner,
            repo=req.github_repo,
            requested_ref=req.ref,
            resolved_commit_sha=sha,
            archive_sha256=result.archive_sha256,
            workspace_path=str(result.workspace_path),
            safety_limits=SafetyLimitsApplied(
                max_compressed_bytes=settings.max_archive_compressed_bytes,
                max_extracted_bytes=settings.max_archive_extracted_bytes,
                max_file_count=settings.max_archive_file_count,
                max_path_depth=settings.max_path_depth,
                max_single_file_bytes=settings.max_single_file_bytes,
                actual_file_count=result.file_count,
                actual_compressed_bytes=result.compressed_bytes,
                actual_extracted_bytes=result.extracted_bytes,
            ),
        )
        return {
            "snapshot": snapshot.model_dump(),
            "node_executions": [node_record(_NODE, started)],
        }

    except (RepositoryInaccessibleError, SafetyLimitError) as exc:
        code = exc.code.value if hasattr(exc, "code") else "ACQUISITION_ERROR"
        return {
            "status": AnalysisStatus.TERMINAL,
            "node_executions": [node_error_record(_NODE, started, code)],
            "errors": [graph_error(_NODE, code, str(exc))],
        }
    except Exception as exc:
        return {
            "status": AnalysisStatus.TERMINAL,
            "node_executions": [node_error_record(_NODE, started, "INTERNAL_ERROR")],
            "errors": [graph_error(_NODE, "INTERNAL_ERROR", str(exc))],
        }
