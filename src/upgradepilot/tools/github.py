"""
Read-only GitHub API client.

Responsibilities:
- resolve a ref (branch/tag/SHA) to an immutable commit SHA;
- retrieve basic repository metadata;
- respect rate-limit headers and retry with jitter;
- never follow URLs found inside repository content;
- never expose a shell command.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
from typing import Any
from urllib.parse import urlparse

import httpx

from upgradepilot.errors import ErrorCode, RepositoryInaccessibleError, UpgradePilotError
from upgradepilot.observability.metrics import record_external_api_error

logger = logging.getLogger(__name__)

# GitHub REST API v3 base
_GITHUB_API_BASE = "https://api.github.com"
# Only github.com archive host is accepted
_ALLOWED_ARCHIVE_HOST = "codeload.github.com"

# Private/link-local address ranges that must never be contacted (SSRF guard)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


class RateLimitError(UpgradePilotError):
    def __init__(self, reset_at: int | None = None) -> None:
        super().__init__(ErrorCode.REPOSITORY_INACCESSIBLE, "GitHub rate limit exceeded")
        self.reset_at = reset_at


def _is_private_address(host: str) -> bool:
    """Return True if host resolves to a private/link-local address (SSRF guard)."""
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        # host is a name, not an IP — cannot determine at parse time; allow DNS
        return False


def _assert_safe_url(url: str) -> None:
    """
    Raise ValueError if url is not HTTPS or points to a private/localhost address.
    This is a defence-in-depth check before any HTTP call.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URLs are allowed. Got scheme: {parsed.scheme!r}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL has no host")
    if _is_private_address(host):
        raise ValueError(f"SSRF: refused connection to private address: {host!r}")


def _jitter(base: float, attempt: int) -> float:
    """Exponential backoff with full jitter: sleep = uniform(0, base * 2^attempt)."""
    cap = base * (2**attempt)
    return random.uniform(0, min(cap, 60.0))  # noqa: S311 — non-crypto jitter


def _build_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "UpgradePilot/0.1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class GitHubClient:
    """
    Thin read-only GitHub REST client.

    - uses HTTPX with explicit connect/read timeouts;
    - retries transient errors (5xx, network) with bounded jitter backoff;
    - turns 429/rate-limit into RateLimitError (never into "not found");
    - never logs Authorization header values.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._timeout = httpx.Timeout(
            connect=10.0, read=float(timeout_seconds), write=5.0, pool=5.0
        )
        self._max_retries = max_retries
        self._http_client = http_client  # injected in tests

    async def _get(self, url: str) -> dict[str, Any]:
        """GET url with retries; returns parsed JSON dict."""
        _assert_safe_url(url)
        headers = _build_headers(self._token)

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                sleep = _jitter(1.0, attempt - 1)
                logger.debug("GitHub retry %d after %.2fs", attempt, sleep)
                await asyncio.sleep(sleep)

            try:
                if self._http_client is not None:
                    resp = await self._http_client.get(url, headers=headers, follow_redirects=True)
                else:
                    async with httpx.AsyncClient(timeout=self._timeout) as c:
                        resp = await c.get(url, headers=headers, follow_redirects=True)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                record_external_api_error(service="github")
                logger.warning(
                    "GitHub request failed (attempt %d): %s",
                    attempt + 1,
                    type(exc).__name__,
                )
                continue

            if resp.status_code == 429 or (
                resp.status_code == 403 and int(resp.headers.get("x-ratelimit-remaining", "1")) == 0
            ):
                record_external_api_error(service="github")
                reset_at = int(resp.headers.get("x-ratelimit-reset", "0")) or None
                raise RateLimitError(reset_at=reset_at)

            if resp.status_code == 404:
                record_external_api_error(service="github")
                raise RepositoryInaccessibleError(
                    f"GitHub returned 404 for {url!r}. "
                    "Repository may be private, deleted, or the ref does not exist."
                )

            if resp.status_code in (401, 403):
                record_external_api_error(service="github")
                raise RepositoryInaccessibleError(
                    f"GitHub returned {resp.status_code}: access denied for {url!r}"
                )

            if resp.status_code >= 500:
                record_external_api_error(service="github")
                last_exc = UpgradePilotError(
                    ErrorCode.REPOSITORY_INACCESSIBLE,
                    f"GitHub server error {resp.status_code}",
                )
                continue

            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result

        raise RepositoryInaccessibleError(
            f"GitHub request failed after {self._max_retries + 1} attempts"
        ) from last_exc

    async def resolve_ref(self, owner: str, repo: str, ref: str) -> str:
        """
        Resolve a branch name, tag, or full SHA to a 40-char commit SHA.

        Priority:
        1. If ref looks like a full 40-char hex SHA, verify it exists and return it.
        2. Try the Commits API (works for branches).
        3. Try the Tags API.
        4. Try the Git Refs API (catches lightweight tags and other refs).
        """
        owner = owner.strip()
        repo = repo.strip()
        ref = ref.strip()

        # Full SHA fast path
        if len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref):
            url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}"
            data = await self._get(url)
            sha: str = data["sha"]
            return sha

        # Try commits endpoint (works for branch names)
        try:
            url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}"
            data = await self._get(url)
            sha = data["sha"]
            logger.info(
                "Resolved ref %r to SHA %s for %s/%s",
                ref,
                sha[:12],
                owner,
                repo,
            )
            return sha
        except RepositoryInaccessibleError:
            pass

        # Fall back to git refs (branches, tags)
        url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/heads/{ref}"
        try:
            data = await self._get(url)
            sha = data["object"]["sha"]
            return sha
        except RepositoryInaccessibleError:
            pass

        url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/git/ref/tags/{ref}"
        data = await self._get(url)
        sha = data["object"]["sha"]
        return sha

    async def get_archive_url(self, owner: str, repo: str, sha: str) -> str:
        """
        Return the tarball URL for a specific commit SHA.
        Does NOT follow arbitrary URLs — constructs from the known pattern.
        """
        # We construct the URL ourselves; we never read it from repository content.
        return f"https://codeload.github.com/{owner}/{repo}/tar.gz/{sha}"

    async def get_repo_metadata(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch basic repository metadata (public repos only)."""
        url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}"
        return await self._get(url)

    def get_archive_download_headers(self) -> dict[str, str]:
        """Headers to use when downloading the archive (no JSON Accept header)."""
        headers: dict[str, str] = {
            "User-Agent": "UpgradePilot/0.1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
