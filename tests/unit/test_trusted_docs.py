from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_httpx

from upgradepilot.migration.loader import load_all_packs
from upgradepilot.migration.models import SourceKind, TrustedSource
from upgradepilot.tools.trusted_docs import (
    CuratedDocumentCache,
    TrustedDocumentCatalog,
    TrustedDocumentFetcher,
    TrustedSourceError,
)


def _pack():
    return load_all_packs().get("pydantic-v1-to-v2")


@pytest.mark.asyncio
async def test_approved_source_retrieves_and_normalizes(
    httpx_mock: pytest_httpx.HTTPXMock, tmp_path: Path
) -> None:
    pack = _pack()
    catalog = TrustedDocumentCatalog(pack)
    source = catalog.source("PYDANTIC_MIGRATION_GUIDE")
    httpx_mock.add_response(
        url=source.canonical_url,
        text="# Model methods\n.dict() maps to model_dump().\n.json() maps to model_dump_json().",
    )
    async with httpx.AsyncClient() as http:
        fetcher = TrustedDocumentFetcher(
            catalog=catalog,
            cache=CuratedDocumentCache(tmp_path),
            http_client=http,
        )
        sections = await fetcher.retrieve(source.source_id, prefer_live=True)

    assert sections
    assert sections[0].source_id == source.source_id
    assert sections[0].retrieval_status == "live"
    assert sections[0].content_hash


def test_rejected_source_domain_is_blocked() -> None:
    catalog = TrustedDocumentCatalog(_pack())
    bad = TrustedSource(
        source_id="BAD",
        title="Bad",
        canonical_url="https://stackoverflow.com/questions/1",
        domain="stackoverflow.com",
        kind=SourceKind.CONCEPT_REFERENCE,
        curated_snapshot_version="1.0.0",
    )

    with pytest.raises(TrustedSourceError):
        catalog.validate_source(bad)


@pytest.mark.asyncio
async def test_live_retrieval_failure_uses_cached_snapshot(
    httpx_mock: pytest_httpx.HTTPXMock, tmp_path: Path
) -> None:
    pack = _pack()
    catalog = TrustedDocumentCatalog(pack)
    source = catalog.source("PYDANTIC_MIGRATION_GUIDE")
    cache = CuratedDocumentCache(tmp_path)
    cache.snapshot_path(source.source_id).parent.mkdir(parents=True)
    cache.snapshot_path(source.source_id).write_text(
        "# Cached section\nCached model_dump evidence.",
        encoding="utf-8",
    )
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"), url=source.canonical_url)

    async with httpx.AsyncClient() as http:
        fetcher = TrustedDocumentFetcher(
            catalog=catalog,
            cache=cache,
            http_client=http,
            max_retries=0,
        )
        sections = await fetcher.retrieve(source.source_id, prefer_live=True)

    assert sections
    assert sections[0].cache_hit is True
    assert sections[0].retrieval_status == "cached_snapshot"


@pytest.mark.asyncio
async def test_no_source_available_returns_empty_sections(tmp_path: Path) -> None:
    catalog = TrustedDocumentCatalog(_pack())
    fetcher = TrustedDocumentFetcher(
        catalog=catalog,
        cache=CuratedDocumentCache(tmp_path),
    )

    sections = await fetcher.retrieve("PYDANTIC_MIGRATION_GUIDE", prefer_live=False)

    assert sections == []
