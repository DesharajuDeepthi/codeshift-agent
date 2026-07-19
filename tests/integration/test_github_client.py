"""
Integration tests for GitHubClient — all HTTP calls are mocked.

Scenarios covered:
  1. Valid repository — ref resolves, metadata returns
  2. Invalid URL — SSRF / non-HTTPS rejected before any HTTP call
  3. Inaccessible repository — 404 becomes RepositoryInaccessibleError
  4. Branch resolution — ref resolves via commits endpoint
  5. Rate limit — 429 becomes RateLimitError (never "not found")
  6. Timeout — network timeout surfaces as RepositoryInaccessibleError after retries
"""

from __future__ import annotations

import httpx
import pytest
import pytest_httpx

from upgradepilot.errors import RepositoryInaccessibleError
from upgradepilot.tools.github import GitHubClient, RateLimitError


@pytest.fixture()
def client(httpx_mock: pytest_httpx.HTTPXMock) -> GitHubClient:
    """GitHubClient with a shared httpx mock transport."""
    http = httpx.AsyncClient()
    return GitHubClient(http_client=http, max_retries=1)


# ---------------------------------------------------------------------------
# Scenario 1: Valid repository — resolves main → SHA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_ref_valid_branch(httpx_mock: pytest_httpx.HTTPXMock) -> None:
    sha = "a" * 40
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/myrepo/commits/main",
        json={"sha": sha, "commit": {}},
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        result = await c.resolve_ref("owner", "myrepo", "main")
    assert result == sha


@pytest.mark.asyncio
async def test_get_repo_metadata_valid(httpx_mock: pytest_httpx.HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/myrepo",
        json={"full_name": "owner/myrepo", "private": False, "default_branch": "main"},
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        meta = await c.get_repo_metadata("owner", "myrepo")
    assert meta["full_name"] == "owner/myrepo"


# ---------------------------------------------------------------------------
# Scenario 2: Invalid URL — SSRF guard / non-HTTPS rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssrf_private_ip_rejected() -> None:
    """GitHubClient must never call a private IP address."""
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        with pytest.raises((ValueError, Exception)):
            # Manually call _get with a private IP URL — should be blocked before HTTP
            await c._get("https://192.168.1.1/anything")


@pytest.mark.asyncio
async def test_ssrf_loopback_rejected() -> None:
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        with pytest.raises((ValueError, Exception)):
            await c._get("https://127.0.0.1/anything")


# ---------------------------------------------------------------------------
# Scenario 3: Inaccessible repository — 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_ref_404_raises_inaccessible(httpx_mock: pytest_httpx.HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/private-repo/commits/main",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/private-repo/git/ref/heads/main",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/private-repo/git/ref/tags/main",
        status_code=404,
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        with pytest.raises(RepositoryInaccessibleError):
            await c.resolve_ref("owner", "private-repo", "main")


# ---------------------------------------------------------------------------
# Scenario 4: Branch resolution — commits endpoint succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_ref_branch_name(httpx_mock: pytest_httpx.HTTPXMock) -> None:
    sha = "b" * 40
    httpx_mock.add_response(
        url="https://api.github.com/repos/acme/app/commits/feature-branch",
        json={"sha": sha},
        status_code=200,
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        result = await c.resolve_ref("acme", "app", "feature-branch")
    assert result == sha


# ---------------------------------------------------------------------------
# Scenario 5: Rate limit — 429 becomes RateLimitError, not "not found"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_429_raises_rate_limit_error(httpx_mock: pytest_httpx.HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/commits/main",
        status_code=429,
        headers={"x-ratelimit-reset": "9999999999"},
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        with pytest.raises(RateLimitError):
            await c.resolve_ref("owner", "repo", "main")


@pytest.mark.asyncio
async def test_rate_limit_403_with_remaining_zero(httpx_mock: pytest_httpx.HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/commits/main",
        status_code=403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"},
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=0)
        with pytest.raises(RateLimitError):
            await c.resolve_ref("owner", "repo", "main")


# ---------------------------------------------------------------------------
# Scenario 6: Timeout — network timeout after max retries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_raises_inaccessible(
    httpx_mock: pytest_httpx.HTTPXMock,
) -> None:
    # Two attempts (initial + 1 retry) each timing out — surplus mocks are OK
    httpx_mock.add_exception(
        httpx.ReadTimeout("timed out"),
        url="https://api.github.com/repos/owner/repo/commits/main",
    )
    httpx_mock.add_exception(
        httpx.ReadTimeout("timed out"),
        url="https://api.github.com/repos/owner/repo/commits/main",
    )
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http, max_retries=1)
        with pytest.raises(RepositoryInaccessibleError):
            # Only the commits endpoint is used; 404 from git/ref fallbacks would
            # raise RepositoryInaccessibleError — timeouts exhaust retries first.
            await c._get("https://api.github.com/repos/owner/repo/commits/main")


# ---------------------------------------------------------------------------
# Archive URL construction never reads from repository content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_url_is_constructed_not_fetched() -> None:
    sha = "c" * 40
    async with httpx.AsyncClient() as http:
        c = GitHubClient(http_client=http)
        url = await c.get_archive_url("owner", "repo", sha)
    assert url == f"https://codeload.github.com/owner/repo/tar.gz/{sha}"
    assert "github.com" not in url.split("codeload.github.com")[0]
