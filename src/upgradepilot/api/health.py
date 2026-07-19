"""Health check endpoints: /health/live and /health/ready."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from upgradepilot.api.dependencies import get_readiness_checks

router = APIRouter(tags=["health"])


class ServiceStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class ComponentHealth(BaseModel):
    status: ServiceStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    status: ServiceStatus
    version: str
    components: dict[str, ComponentHealth] = {}


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Returns 200 as long as the process is alive."""
    from upgradepilot import __version__

    return HealthResponse(status=ServiceStatus.OK, version=__version__)


@router.get("/health/ready", response_model=HealthResponse)
async def readiness() -> JSONResponse:
    """
    Checks that required dependencies are reachable.
    Returns 200 when OK or DEGRADED (optional deps missing).
    Returns 503 when any required dependency is DOWN.
    Redis and LangSmith are optional — degraded-but-ready with disclosure.
    """
    from upgradepilot import __version__

    components: dict[str, ComponentHealth] = {}
    overall = ServiceStatus.OK

    checks: dict[str, Any] = await get_readiness_checks()
    for name, result in checks.items():
        if result["ok"]:
            components[name] = ComponentHealth(status=ServiceStatus.OK)
        elif result.get("required", True):
            components[name] = ComponentHealth(
                status=ServiceStatus.DOWN, detail=result.get("detail")
            )
            overall = ServiceStatus.DOWN
        else:
            components[name] = ComponentHealth(
                status=ServiceStatus.DEGRADED, detail=result.get("detail")
            )
            if overall != ServiceStatus.DOWN:
                overall = ServiceStatus.DEGRADED

    body = HealthResponse(status=overall, version=__version__, components=components)
    http_status = 503 if overall == ServiceStatus.DOWN else 200
    return JSONResponse(content=body.model_dump(), status_code=http_status)
