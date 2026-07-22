"""AnalysisRequest and related input models."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from upgradepilot.config import AnalysisMode

# Only github.com is supported in V1.
_ALLOWED_GITHUB_HOST = "github.com"
_GITHUB_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
# Pack IDs must match this format; existence is validated by the pack registry.
_PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,98}[a-z0-9]$")


class ParsedGitHubURL:
    """Value object produced by GitHub URL validation."""

    __slots__ = ("owner", "repo", "canonical_url")

    def __init__(self, owner: str, repo: str) -> None:
        self.owner = owner
        self.repo = repo
        self.canonical_url = f"https://github.com/{owner}/{repo}"

    def __repr__(self) -> str:
        return f"ParsedGitHubURL(owner={self.owner!r}, repo={self.repo!r})"


def parse_github_url(raw: str) -> ParsedGitHubURL:
    """
    Validate and parse a GitHub repository URL.

    Accepts only HTTPS URLs for github.com with exactly owner/repo path.
    Raises ValueError for any other form.
    """
    raw = raw.strip()

    # Reject anything that looks like a local path, data URI, or non-HTTPS scheme
    if not raw.lower().startswith("https://"):
        raise ValueError(f"Only HTTPS GitHub URLs are accepted. Got: {raw!r}")

    # Reject embedded credentials (user:pass@) before Pydantic strips them silently
    if "@" in raw.split("?")[0]:
        raise ValueError(f"URLs with embedded credentials are not allowed: {raw!r}")

    try:
        url = HttpUrl(raw)
    except Exception as exc:
        raise ValueError(f"Invalid URL: {raw!r}") from exc

    raw_host = (url.host or "").lower()
    host = raw_host[4:] if raw_host.startswith("www.") else raw_host
    if host != _ALLOWED_GITHUB_HOST:
        raise ValueError(f"Only github.com repositories are supported in V1. Got host: {host!r}")

    # Strip leading slash and any trailing .git suffix
    path = (url.path or "").lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    parts = [p for p in path.split("/") if p]
    if len(parts) != 2:
        raise ValueError(
            f"URL must point to exactly one repository (owner/repo). Got path: {path!r}"
        )

    owner, repo = parts

    for slug, label in ((owner, "owner"), (repo, "repository")):
        if not _GITHUB_SLUG_RE.match(slug):
            raise ValueError(f"Invalid GitHub {label} name: {slug!r}")
        # Reject double-dots (path traversal via name)
        if ".." in slug:
            raise ValueError(f"Invalid GitHub {label} name (contains '..'): {slug!r}")

    return ParsedGitHubURL(owner=owner, repo=repo)


class AnalysisRequest(BaseModel):
    """Validated analysis request — the entry point for the graph."""

    model_config = {"frozen": True}

    repository_url: str
    ref: str = "main"
    migration_pack: str | None = None
    analysis_mode: AnalysisMode = AnalysisMode.STANDARD
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Derived — populated by the validator, stored for downstream use
    github_owner: str = Field(default="", init=False)
    github_repo: str = Field(default="", init=False)

    @field_validator("repository_url")
    @classmethod
    def validate_repository_url(cls, v: str) -> str:
        # parse_github_url raises ValueError which Pydantic wraps into ValidationError
        parse_github_url(v)
        return v

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ref must not be empty")
        if len(v) > 255:
            raise ValueError("ref is too long (max 255 characters)")
        return v

    @field_validator("migration_pack")
    @classmethod
    def validate_migration_pack(cls, v: str | None) -> str | None:
        if v is None:
            return None
        # Validate format only (no I/O); existence is deferred to select_migration_pack node.
        if not _PACK_ID_RE.match(v):
            raise ValueError(
                f"Invalid migration_pack format: {v!r}. "
                "Pack IDs must be lowercase alphanumeric with hyphens or underscores."
            )
        return v

    @model_validator(mode="after")
    def _populate_parsed_fields(self) -> AnalysisRequest:
        parsed = parse_github_url(self.repository_url)
        # Bypass frozen to set derived fields once during construction
        object.__setattr__(self, "github_owner", parsed.owner)
        object.__setattr__(self, "github_repo", parsed.repo)
        return self
