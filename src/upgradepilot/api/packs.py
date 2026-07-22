"""Migration pack discovery endpoint."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel

if TYPE_CHECKING:
    from upgradepilot.migration.loader import MigrationPackRegistry

router = APIRouter(prefix="/packs", tags=["packs"])


class PackSummary(BaseModel):
    pack_id: str
    display_name: str
    language: str
    analyzer_kind: str
    version: str
    description: str
    source_package: str
    source_major: int
    target_major: int


class PacksListResponse(BaseModel):
    packs: list[PackSummary]


@functools.lru_cache(maxsize=1)
def _load_registry() -> MigrationPackRegistry:
    from upgradepilot.migration.loader import load_all_packs

    return load_all_packs()


@router.get("", response_model=PacksListResponse)
async def list_packs() -> PacksListResponse:
    """List all installed migration packs."""
    registry = _load_registry()
    packs = [
        PackSummary(
            pack_id=pid,
            display_name=registry.get(pid).metadata.display_name,
            language=registry.get(pid).metadata.language,
            analyzer_kind=registry.get(pid).metadata.analyzer_kind,
            version=registry.get(pid).metadata.version,
            description=registry.get(pid).metadata.description,
            source_package=registry.get(pid).metadata.source_package,
            source_major=registry.get(pid).metadata.source_major,
            target_major=registry.get(pid).metadata.target_major,
        )
        for pid in registry.list_ids()
    ]
    return PacksListResponse(packs=packs)
