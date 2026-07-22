"""Unit tests for AnalysisRequest model and GitHub URL parsing."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from upgradepilot.models.request import AnalysisMode, AnalysisRequest, parse_github_url


class TestParseGitHubURL:
    def test_valid_url(self) -> None:
        result = parse_github_url("https://github.com/owner/repo")
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.canonical_url == "https://github.com/owner/repo"

    def test_trailing_slash_stripped(self) -> None:
        result = parse_github_url("https://github.com/owner/repo/")
        assert result.owner == "owner"
        assert result.repo == "repo"

    def test_dot_git_stripped(self) -> None:
        result = parse_github_url("https://github.com/owner/repo.git")
        assert result.repo == "repo"

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            parse_github_url("http://github.com/owner/repo")

    def test_rejects_non_github_host(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("https://gitlab.com/owner/repo")

    def test_rejects_credentials_in_url(self) -> None:
        with pytest.raises((ValueError, Exception)):
            parse_github_url("https://user:pass@github.com/owner/repo")

    def test_rejects_path_traversal_in_segment(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("https://github.com/owner/repo/blob/main/file.py")

    def test_rejects_missing_repo(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("https://github.com/owner")

    def test_rejects_too_many_path_components(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("https://github.com/owner/repo/blob/main/file.py")

    def test_rejects_invalid_owner_slug(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("https://github.com/ow!ner/repo")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("")

    def test_rejects_double_dot_in_owner(self) -> None:
        with pytest.raises(ValueError):
            parse_github_url("https://github.com/ow..ner/repo")


class TestAnalysisRequest:
    def test_valid_request(self) -> None:
        req = AnalysisRequest(repository_url="https://github.com/owner/repo")
        assert req.github_owner == "owner"
        assert req.github_repo == "repo"
        assert req.ref == "main"
        assert req.migration_pack == "pydantic-v1-to-v2"
        assert req.analysis_mode == AnalysisMode.STANDARD

    def test_request_is_frozen(self) -> None:
        req = AnalysisRequest(repository_url="https://github.com/owner/repo")
        with pytest.raises((ValidationError, TypeError)):
            req.ref = "other"  # type: ignore[misc]

    def test_request_id_is_uuid(self) -> None:
        req = AnalysisRequest(repository_url="https://github.com/owner/repo")
        uuid.UUID(req.request_id)  # raises if not valid UUID

    def test_invalid_url_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            AnalysisRequest(repository_url="not-a-url")

    def test_invalid_migration_pack_format(self) -> None:
        # Only format is validated at construction time; existence is checked
        # by the select_migration_pack graph node at analysis time.
        # Invalid formats (uppercase, path separators, empty) must still be rejected.
        for bad in ["UPPER-CASE", "has/slash", "has space", ""]:
            with pytest.raises(ValidationError, match="migration_pack|pack"):
                AnalysisRequest(
                    repository_url="https://github.com/owner/repo",
                    migration_pack=bad,
                )

    def test_valid_format_unknown_pack_accepted(self) -> None:
        # A well-formed pack ID that doesn't exist yet is accepted at construction;
        # the graph node will reject it with a typed error.
        req = AnalysisRequest(
            repository_url="https://github.com/owner/repo",
            migration_pack="future-pack-v1-to-v2",
        )
        assert req.migration_pack == "future-pack-v1-to-v2"

    def test_custom_ref(self) -> None:
        req = AnalysisRequest(
            repository_url="https://github.com/owner/repo",
            ref="v2.0.0",
        )
        assert req.ref == "v2.0.0"
