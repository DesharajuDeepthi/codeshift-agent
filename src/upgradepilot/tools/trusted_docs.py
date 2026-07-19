"""Trusted official-document retrieval, cache, and section search tools."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from upgradepilot.migration.models import DetectionRule, LoadedMigrationPack, TrustedSource
from upgradepilot.models.documentation import (
    NormalizedDocumentSection,
    SourceRetrievalStatus,
)

_SECTION_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


class TrustedSourceError(ValueError):
    """Raised when a source is outside the migration-pack trusted catalog."""


class TrustedDocumentCatalog:
    """Read-only catalog wrapper around pack trusted sources and rule mappings."""

    def __init__(self, pack: LoadedMigrationPack) -> None:
        self._pack = pack
        self._sources = {source.source_id: source for source in pack.trusted_sources.sources}
        self._allowed_domains = frozenset(pack.trusted_sources.allowed_domains)

    @property
    def allowed_domains(self) -> frozenset[str]:
        return self._allowed_domains

    def source(self, source_id: str) -> TrustedSource:
        source = self._sources.get(source_id)
        if source is None:
            raise TrustedSourceError(f"Unknown trusted source_id: {source_id}")
        self.validate_source(source)
        return source

    def sources_for_rules(self, rule_ids: Iterable[str]) -> list[TrustedSource]:
        ordered: list[TrustedSource] = []
        seen: set[str] = set()
        for rule_id in rule_ids:
            rule = self._pack.get_rule(rule_id)
            if rule is None:
                continue
            for source_id in rule.source_ids:
                if source_id not in seen:
                    ordered.append(self.source(source_id))
                    seen.add(source_id)
        return ordered

    def rule(self, rule_id: str) -> DetectionRule | None:
        return self._pack.get_rule(rule_id)

    def validate_source(self, source: TrustedSource) -> None:
        parsed = urlparse(source.canonical_url)
        if parsed.scheme != "https":
            raise TrustedSourceError(f"Trusted source must use HTTPS: {source.source_id}")
        if source.domain not in self._allowed_domains:
            raise TrustedSourceError(f"Trusted source domain is not allowlisted: {source.domain}")
        if parsed.hostname != source.domain:
            raise TrustedSourceError(
                f"Trusted source URL host does not match catalog domain: {source.source_id}"
            )

    def validate_redirect_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self._allowed_domains:
            raise TrustedSourceError("Redirected source URL left the trusted allowlist")


class CuratedDocumentCache:
    """Read-only local snapshot cache for trusted official sources."""

    def __init__(self, pack_dir: Path) -> None:
        self._snapshot_dir = pack_dir / "snapshots"

    def snapshot_path(self, source_id: str) -> Path:
        safe_name = source_id.upper().replace("-", "_")
        return self._snapshot_dir / f"{safe_name}.md"

    def read(self, source_id: str) -> str | None:
        path = self.snapshot_path(source_id)
        if not path.exists() or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")


class TrustedDocumentFetcher:
    """Approved official-source fetcher with timeout, retry, and cache fallback."""

    def __init__(
        self,
        *,
        catalog: TrustedDocumentCatalog,
        cache: CuratedDocumentCache,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
    ) -> None:
        self._catalog = catalog
        self._cache = cache
        self._http_client = http_client
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    async def retrieve(
        self, source_id: str, *, prefer_live: bool = True
    ) -> list[NormalizedDocumentSection]:
        source = self._catalog.source(source_id)
        started = time.perf_counter()
        text: str | None = None
        status = SourceRetrievalStatus.UNAVAILABLE
        cache_hit = False
        retrieved_at = datetime.now(UTC)

        if prefer_live:
            try:
                text = await self._fetch_live(source)
                status = SourceRetrievalStatus.LIVE
            except (httpx.HTTPError, TrustedSourceError):
                text = None

        if text is None:
            text = self._cache.read(source.source_id)
            if text is not None:
                status = SourceRetrievalStatus.CACHED_SNAPSHOT
                cache_hit = True

        if text is None:
            return []

        retrieval_ms = (time.perf_counter() - started) * 1000
        content_hash = _sha256(text)
        freshness = (
            "Live official source retrieved during analysis."
            if status == SourceRetrievalStatus.LIVE
            else (
                "Curated local snapshot used because live retrieval was unavailable "
                f"or disabled; snapshot version {source.curated_snapshot_version}."
            )
        )
        return normalize_document_sections(
            source=source,
            text=text,
            content_hash=content_hash,
            retrieved_at=retrieved_at,
            retrieval_ms=retrieval_ms,
            status=status,
            cache_hit=cache_hit,
            freshness_disclosure=freshness,
        )

    async def _fetch_live(self, source: TrustedSource) -> str:
        if self._http_client is None:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
            ) as client:
                return await self._fetch_with_client(client, source)
        return await self._fetch_with_client(self._http_client, source)

    async def _fetch_with_client(self, client: httpx.AsyncClient, source: TrustedSource) -> str:
        last_exc: httpx.HTTPError | None = None
        for _ in range(self._max_retries + 1):
            try:
                response = await client.get(source.canonical_url)
                self._catalog.validate_redirect_url(str(response.url))
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise httpx.TransportError("source retrieval failed")


async def refresh_trusted_source_snapshot(
    *,
    catalog: TrustedDocumentCatalog,
    cache: CuratedDocumentCache,
    source_id: str,
    http_client: httpx.AsyncClient | None = None,
) -> str:
    """
    Refresh one curated snapshot from its cataloged official source.

    The caller chooses a source_id, not a URL. The URL is resolved only from the
    trusted-source catalog, and redirects must remain inside the allowlist.
    Returns the SHA-256 hash of the refreshed snapshot content.
    """
    source = catalog.source(source_id)
    fetcher = TrustedDocumentFetcher(
        catalog=catalog,
        cache=cache,
        http_client=http_client,
        max_retries=1,
    )
    text = await fetcher._fetch_live(source)  # noqa: SLF001 - refresh is part of this tool.
    path = cache.snapshot_path(source.source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return _sha256(text)


class DocumentSectionSearch:
    """Search normalized sections without exposing arbitrary document access."""

    def search(
        self,
        *,
        sections: Iterable[NormalizedDocumentSection],
        rule: DetectionRule,
        limit: int = 2,
    ) -> list[NormalizedDocumentSection]:
        terms = _terms(rule.rule_id, rule.migration_concept, rule.rationale)
        scored: list[tuple[int, NormalizedDocumentSection]] = []
        for section in sections:
            haystack = f"{section.section}\n{section.text}".lower()
            score = sum(1 for term in terms if term in haystack)
            if rule.rule_id.lower() in haystack:
                score += 5
            if any(source_id.lower() in haystack for source_id in rule.source_ids):
                score += 2
            if score > 0:
                scored.append((score, section))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [section for _, section in scored[:limit]]


def normalize_document_sections(
    *,
    source: TrustedSource,
    text: str,
    content_hash: str,
    retrieved_at: datetime,
    retrieval_ms: float,
    status: SourceRetrievalStatus,
    cache_hit: bool,
    freshness_disclosure: str,
) -> list[NormalizedDocumentSection]:
    """Split markdown-ish official docs into bounded, normalized sections."""
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Overview"
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = _SECTION_HEADING_RE.match(line)
        if match:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = match.group(2).strip()
            current_lines = []
        elif line.strip():
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines))

    normalized: list[NormalizedDocumentSection] = []
    for heading, lines in sections:
        bounded = "\n".join(lines[:20])[:4000]
        if not bounded.strip():
            continue
        normalized.append(
            NormalizedDocumentSection(
                source_id=source.source_id,
                title=source.title,
                canonical_url=source.canonical_url,
                section=heading,
                text=bounded,
                content_hash=content_hash,
                retrieved_at=retrieved_at,
                retrieval_ms=retrieval_ms,
                retrieval_status=status,
                cache_hit=cache_hit,
                snapshot_version=source.curated_snapshot_version,
                freshness_disclosure=freshness_disclosure,
            )
        )
    return normalized


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _terms(*values: str) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for term in _WORD_RE.findall(value.lower()):
            if term not in {
                "pydantic",
                "migration",
                "source",
                "guide",
                "the",
                "and",
                "with",
                "replace",
                "replaced",
                "removed",
                "adding",
                "adjusting",
                "signature",
            }:
                terms.add(term)
    return terms
