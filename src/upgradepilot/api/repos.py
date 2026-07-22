"""Repository-scoped history endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from upgradepilot.services.findings_store import FindingsStore

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("/{owner}/{repo}/history")
async def get_repo_history(
    owner: str,
    repo: str,
    req: Request,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """List past analyses for a repository, most recent first."""
    findings_store: FindingsStore | None = getattr(req.app.state, "findings_store", None)
    if findings_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="cross-analysis memory is not enabled",
        )
    capped_limit = min(max(1, limit), 100)
    return await findings_store.history_for_repo(owner, repo, limit=capped_limit)
