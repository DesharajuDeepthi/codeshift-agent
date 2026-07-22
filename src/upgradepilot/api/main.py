"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from upgradepilot import __version__
from upgradepilot.api.analyses import router as analyses_router
from upgradepilot.api.health import router as health_router
from upgradepilot.api.middleware import PrometheusMiddleware
from upgradepilot.api.packs import router as packs_router
from upgradepilot.api.repos import router as repos_router
from upgradepilot.config import get_settings
from upgradepilot.observability.logging import configure_logging, get_logger
from upgradepilot.observability.metrics import REGISTRY
from upgradepilot.observability.tracing import configure_langsmith

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    configure_langsmith(
        api_key=settings.langsmith_api_key.get_secret_value()
        if settings.langsmith_api_key
        else None,
        project=settings.langsmith_project_name,
        endpoint=settings.langsmith_endpoint,
        tracing_enabled=settings.langsmith_tracing,
        hide_inputs=settings.langsmith_hide_inputs,
        hide_outputs=settings.langsmith_hide_outputs,
    )
    logger.info("UpgradePilot API started", extra={"event": "startup", "version": __version__})

    # Wire FindingsStore when a database URL is configured (skipped in fixture/CI mode)
    app.state.findings_store = None
    if settings.database_url:
        try:
            from psycopg_pool import AsyncConnectionPool

            from upgradepilot.services.findings_store import FindingsStore

            pool = AsyncConnectionPool(
                settings.database_url.get_secret_value(),
                open=False,
                min_size=1,
                max_size=5,
            )
            await pool.open()
            app.state.findings_store = FindingsStore(pool)
            logger.info(
                "FindingsStore ready",
                extra={"event": "findings_store_ready"},
            )
        except Exception:
            logger.warning(
                "FindingsStore unavailable; cross-analysis memory disabled",
                extra={"event": "findings_store_unavailable"},
                exc_info=True,
            )

    yield

    if app.state.findings_store is not None:
        try:
            await app.state.findings_store._pool.close()
        except Exception:
            logger.warning(
                "Error closing findings pool",
                extra={"event": "findings_pool_close_error"},
            )

    logger.info("UpgradePilot API stopped", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    app = FastAPI(
        title="UpgradePilot",
        description="Agentic Pydantic v1-to-v2 migration intelligence",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(PrometheusMiddleware)
    app.include_router(health_router)
    app.include_router(packs_router)
    app.include_router(analyses_router)
    app.include_router(repos_router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        data = generate_latest(REGISTRY)
        return PlainTextResponse(content=data.decode(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
