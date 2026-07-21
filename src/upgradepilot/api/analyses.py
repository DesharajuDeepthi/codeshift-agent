"""Analysis API endpoints, progress streaming, exports, and feedback."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from upgradepilot.auth.deps import optional_user_id, require_user_id
from upgradepilot.config import AnalysisMode, get_settings
from upgradepilot.db import history as hist
from upgradepilot.graph.build import build_graph
from upgradepilot.graph.checkpointer import get_memory_checkpointer, get_postgres_checkpointer
from upgradepilot.graph.state import FIXTURE_SUPPORTED, AnalysisStatus, make_initial_state
from upgradepilot.models.request import AnalysisRequest
from upgradepilot.observability.logging import get_logger
from upgradepilot.observability.tracing import UserFeedback, attach_user_feedback
from upgradepilot.reports.render import (
    render_github_issue_body,
    render_markdown_report,
    report_json_bytes,
    safe_report,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])

_TERMINAL_STATUSES = {
    AnalysisStatus.COMPLETED.value,
    AnalysisStatus.PARTIAL.value,
    AnalysisStatus.TERMINAL.value,
    AnalysisStatus.FAILED.value,
}
_APPEND_KEYS = {
    "node_executions",
    "errors",
    "warnings",
    "dependencies",
    "findings",
    "documentation_evidence",
    "repair_instructions",
}


class _GraphProtocol(Protocol):
    def astream(
        self,
        input: Mapping[str, Any],  # noqa: A002
        config: Mapping[str, Any] | None = None,
        *,
        stream_mode: str | None = None,
    ) -> AsyncIterator[Any]: ...


class ProgressEvent(BaseModel):
    """SSE-safe graph progress event."""

    analysis_id: str
    sequence: int
    node_name: str
    status: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    report_status: str | None = None


class AnalysisCreateResponse(BaseModel):
    analysis_id: str
    status: str
    status_url: str
    events_url: str
    report_url: str


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    report_status: str
    progress: float
    current_stage: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    commit_sha: str | None = None
    migration_pack: str | None = None
    migration_pack_version: str | None = None
    trace_id: str | None = None
    langsmith_root_run_id: str | None = None
    observability_status: str | None = None
    warnings: list[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    key: Literal["useful", "not_useful", "plan_actionable", "finding_helpful"] = "useful"
    score: bool | float | int | None = None
    value: bool | str | dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=2000)
    finding_id: str | None = Field(default=None, max_length=200)


class FeedbackResponse(BaseModel):
    analysis_id: str
    attached: bool
    status: str


class _AnalysisRecord(BaseModel):
    analysis_id: str
    request: dict[str, Any]
    status: str
    report_status: str
    state: dict[str, Any]
    events: list[ProgressEvent] = Field(default_factory=list)
    final_report: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class _AnalysisStore:
    def __init__(self) -> None:
        self._records: dict[str, _AnalysisRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, request: AnalysisRequest) -> _AnalysisRecord:
        analysis_id = str(uuid.uuid4())
        request_data = request.model_dump(mode="json")
        state = dict(make_initial_state(analysis_id, request_data, FIXTURE_SUPPORTED))
        record = _AnalysisRecord(
            analysis_id=analysis_id,
            request=request_data,
            status=AnalysisStatus.PENDING.value,
            report_status="pending",
            state=state,
        )
        async with self._lock:
            self._records[analysis_id] = record
        return record

    async def get(self, analysis_id: str) -> _AnalysisRecord:
        async with self._lock:
            record = self._records.get(analysis_id)
            if record is None:
                raise HTTPException(status_code=404, detail="analysis not found")
            return record.model_copy(deep=True)

    async def update(self, analysis_id: str, update: Mapping[str, Any]) -> _AnalysisRecord:
        async with self._lock:
            record = self._records[analysis_id]
            _merge_state(record.state, update)
            record.status = str(record.state.get("status") or record.status)
            record.report_status = str(record.state.get("report_status") or record.report_status)
            report = record.state.get("final_report")
            if isinstance(report, dict):
                record.final_report = safe_report(report)
            record.updated_at = datetime.now(UTC)
            self._records[analysis_id] = record
            return record.model_copy(deep=True)

    async def add_event(
        self,
        analysis_id: str,
        *,
        node_name: str,
        node_status: str,
        report_status: str | None,
    ) -> ProgressEvent:
        async with self._lock:
            record = self._records[analysis_id]
            event = ProgressEvent(
                analysis_id=analysis_id,
                sequence=len(record.events) + 1,
                node_name=node_name,
                status=node_status,
                message=f"Completed {node_name}",
                report_status=report_status,
            )
            record.events.append(event)
            record.updated_at = datetime.now(UTC)
            self._records[analysis_id] = record
            return event

    async def finish(
        self,
        analysis_id: str,
        *,
        status_value: str | None = None,
        error_message: str | None = None,
    ) -> _AnalysisRecord:
        async with self._lock:
            record = self._records[analysis_id]
            if status_value is not None:
                record.status = status_value
                record.state["status"] = status_value
            record.error_message = error_message
            record.completed_at = datetime.now(UTC)
            record.updated_at = record.completed_at
            self._records[analysis_id] = record
            return record.model_copy(deep=True)


STORE = _AnalysisStore()


@router.get("", response_model=list[dict[str, Any]])
async def list_analyses(
    limit: int = Query(default=10, ge=1, le=50),
    user_id: uuid.UUID = Depends(require_user_id),  # noqa: B008
) -> list[dict[str, Any]]:
    """Return the authenticated user's most recent analyses."""
    return hist.list_analyses(user_id=user_id, limit=limit)


@router.post("", response_model=AnalysisCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID | None = Depends(optional_user_id),  # noqa: B008
) -> AnalysisCreateResponse:
    """Create an analysis and start graph execution."""
    record = await STORE.create(request)
    if user_id is not None:
        hist.record_analysis(
            user_id=user_id,
            analysis_id=record.analysis_id,
            repository_url=request.repository_url,
            ref=request.ref or "main",
        )
    if request.analysis_mode == AnalysisMode.FIXTURE:
        await _run_analysis(record.analysis_id)
    else:
        background_tasks.add_task(_run_analysis, record.analysis_id)
    return _create_response(record.analysis_id, (await STORE.get(record.analysis_id)).status)


@router.get("/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis_status(analysis_id: str) -> AnalysisStatusResponse:
    record = await STORE.get(analysis_id)
    return _status_response(record)


@router.get("/{analysis_id}/events")
async def stream_analysis_events(analysis_id: str) -> StreamingResponse:
    await STORE.get(analysis_id)
    return StreamingResponse(_event_stream(analysis_id), media_type="text/event-stream")


@router.get("/{analysis_id}/report")
async def get_analysis_report(analysis_id: str) -> JSONResponse:
    record = await STORE.get(analysis_id)
    report = _require_report(record)
    return JSONResponse(content=jsonable_encoder(report))


@router.get("/{analysis_id}/report.json")
async def download_json_report(analysis_id: str) -> Response:
    record = await STORE.get(analysis_id)
    report = _require_report(record)
    return Response(
        content=report_json_bytes(report),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}.json"'},
    )


@router.get("/{analysis_id}/report.md")
async def download_markdown_report(analysis_id: str) -> PlainTextResponse:
    record = await STORE.get(analysis_id)
    report = _require_report(record)
    return PlainTextResponse(
        render_markdown_report(report),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}.md"'},
    )


@router.get("/{analysis_id}/github-issue.md")
async def download_github_issue_body(analysis_id: str) -> PlainTextResponse:
    record = await STORE.get(analysis_id)
    report = _require_report(record)
    return PlainTextResponse(
        render_github_issue_body(report),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}-issue.md"'},
    )


@router.post("/{analysis_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(analysis_id: str, feedback: FeedbackRequest) -> FeedbackResponse:
    record = await STORE.get(analysis_id)
    report = record.final_report or {}
    observability = report.get("observability") if isinstance(report, dict) else {}
    if not isinstance(observability, dict):
        observability = {}
    attached = attach_user_feedback(
        UserFeedback(
            analysis_id=analysis_id,
            request_id=str(record.request.get("request_id") or ""),
            key=feedback.key,
            score=feedback.score,
            value=feedback.value,
            comment=feedback.comment,
            finding_id=feedback.finding_id,
            trace_id=_optional_text(observability.get("trace_id")),
            langsmith_root_run_id=_optional_text(observability.get("langsmith_root_run_id")),
        )
    )
    return FeedbackResponse(
        analysis_id=analysis_id,
        attached=attached,
        status="attached" if attached else "accepted_without_trace",
    )


async def _run_analysis(analysis_id: str) -> None:
    record = await STORE.get(analysis_id)
    await STORE.update(analysis_id, {"status": AnalysisStatus.RUNNING.value})
    start = time.perf_counter()
    try:
        async with _analysis_graph(record) as graph:
            async for update in graph.astream(
                record.state,
                config={"configurable": {"thread_id": analysis_id}},
                stream_mode="updates",
            ):
                if not isinstance(update, dict):
                    continue
                for node_name, node_update in update.items():
                    if not isinstance(node_update, dict):
                        continue
                    updated = await STORE.update(analysis_id, node_update)
                    await STORE.add_event(
                        analysis_id,
                        node_name=str(node_name),
                        node_status=_node_status(str(node_name), node_update),
                        report_status=updated.report_status,
                    )
        final = await STORE.get(analysis_id)
        status_value = final.status
        if status_value not in _TERMINAL_STATUSES:
            status_value = (
                AnalysisStatus.COMPLETED.value
                if final.final_report is not None
                else AnalysisStatus.FAILED.value
            )
        await STORE.finish(analysis_id, status_value=status_value)
        hist.finish_analysis(analysis_id=analysis_id, status=status_value)
        logger.info(
            "Analysis finished through API",
            extra={
                "event": "api_analysis_finished",
                "analysis_id": analysis_id,
                "duration_ms": round((time.perf_counter() - start) * 1000, 3),
            },
        )
    except Exception:
        logger.exception(
            "Analysis failed through API",
            extra={"event": "api_analysis_failed", "analysis_id": analysis_id},
        )
        await STORE.finish(
            analysis_id,
            status_value=AnalysisStatus.FAILED.value,
            error_message="Analysis failed; see server logs with this analysis ID.",
        )
        hist.finish_analysis(analysis_id=analysis_id, status=AnalysisStatus.FAILED.value)


@asynccontextmanager
async def _analysis_graph(record: _AnalysisRecord) -> AsyncIterator[_GraphProtocol]:
    """Yield the graph with the V1 checkpointing backend required for the request."""
    if record.request.get("analysis_mode") == AnalysisMode.FIXTURE.value:
        yield cast(_GraphProtocol, build_graph(checkpointer=get_memory_checkpointer()))
        return

    settings = get_settings()
    database_url = settings.database_url.get_secret_value()
    async with get_postgres_checkpointer(database_url) as checkpointer:
        await checkpointer.setup()
        yield cast(_GraphProtocol, build_graph(checkpointer=checkpointer))


async def _event_stream(analysis_id: str) -> AsyncIterator[str]:
    sent = 0
    while True:
        record = await STORE.get(analysis_id)
        for event in record.events[sent:]:
            payload = event.model_dump(mode="json")
            yield f"event: progress\ndata: {json.dumps(payload, default=str)}\n\n"
        sent = len(record.events)
        if record.status in _TERMINAL_STATUSES:
            payload = {
                "analysis_id": analysis_id,
                "status": record.status,
                "report_status": record.report_status,
            }
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
            break
        await asyncio.sleep(0.25)


def _create_response(analysis_id: str, status_value: str) -> AnalysisCreateResponse:
    return AnalysisCreateResponse(
        analysis_id=analysis_id,
        status=status_value,
        status_url=f"/analyses/{analysis_id}",
        events_url=f"/analyses/{analysis_id}/events",
        report_url=f"/analyses/{analysis_id}/report",
    )


def _status_response(record: _AnalysisRecord) -> AnalysisStatusResponse:
    report = record.final_report or {}
    observability = report.get("observability") if isinstance(report, dict) else {}
    if not isinstance(observability, dict):
        observability = {}
    return AnalysisStatusResponse(
        analysis_id=record.analysis_id,
        status=record.status,
        report_status=record.report_status,
        progress=_progress(record),
        current_stage=record.events[-1].node_name if record.events else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        commit_sha=_optional_text(report.get("commit_sha")),
        migration_pack=_optional_text(report.get("migration_pack")),
        migration_pack_version=_optional_text(report.get("migration_pack_version")),
        trace_id=_optional_text(observability.get("trace_id")),
        langsmith_root_run_id=_optional_text(observability.get("langsmith_root_run_id")),
        observability_status=_optional_text(observability.get("status")),
        warnings=[str(item) for item in record.state.get("warnings", [])],
    )


def _progress(record: _AnalysisRecord) -> float:
    if record.status in _TERMINAL_STATUSES:
        return 1.0
    return min(0.95, len(record.events) / 12)


def _require_report(record: _AnalysisRecord) -> dict[str, Any]:
    if record.final_report is None:
        raise HTTPException(status_code=409, detail="analysis report is not ready")
    return record.final_report


def _merge_state(state: dict[str, Any], update: Mapping[str, Any]) -> None:
    for key, value in update.items():
        if key in _APPEND_KEYS:
            current = state.get(key)
            if not isinstance(current, list):
                current = []
            if isinstance(value, list):
                current.extend(jsonable_encoder(value))
            elif value is not None:
                current.append(jsonable_encoder(value))
            state[key] = current
        else:
            # State is the canonical record; secret redaction and bounding happen
            # at the report/trace export boundary (safe_report, tracing), not here.
            state[key] = jsonable_encoder(value)


def _node_status(node_name: str, node_update: Mapping[str, Any]) -> str:
    executions = node_update.get("node_executions")
    if isinstance(executions, list):
        for execution in executions:
            if isinstance(execution, dict) and execution.get("node_name") == node_name:
                return str(execution.get("status") or "completed")
    if node_update.get("errors"):
        return "failed"
    return "completed"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
