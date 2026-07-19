"""LangSmith tracing, local trace correlation, and graph instrumentation."""

from __future__ import annotations

import inspect
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, cast

from pydantic import BaseModel, Field

from upgradepilot import __version__
from upgradepilot.config import AnalysisMode, get_settings
from upgradepilot.errors import ErrorCode
from upgradepilot.graph.state import UpgradePilotState
from upgradepilot.observability.logging import get_logger, log_context
from upgradepilot.observability.metrics import (
    analyses_active,
    record_analysis_finished,
    record_graph_node_duration,
    record_llm_usage,
    record_validation_issues,
)
from upgradepilot.observability.redaction import sanitize_value

logger = get_logger(__name__)

ROOT_TRACE_NAME = "upgradepilot.analysis"


class ObservabilityStatus(StrEnum):
    """Local tracing state surfaced in reports."""

    CONFIGURED = "configured"
    DISABLED = "disabled"
    DEGRADED = "degraded"


class LLMUsage(BaseModel):
    """Token/cost usage captured for one LLM run."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    retry_count: int = Field(default=0, ge=0)


class UserFeedback(BaseModel):
    """Feedback payload attached to the root LangSmith run when available."""

    analysis_id: str
    request_id: str | None = None
    key: str
    score: bool | float | int | None = None
    value: bool | str | dict[str, Any] | None = None
    comment: str | None = None
    finding_id: str | None = None
    trace_id: str | None = None
    langsmith_root_run_id: str | None = None


class _LangSmithClient(Protocol):
    def create_run(self, **kwargs: object) -> object: ...

    def update_run(self, **kwargs: object) -> object: ...

    def create_feedback(self, *args: object, **kwargs: object) -> object: ...


class _RunTree(Protocol):
    id: uuid.UUID
    trace_id: uuid.UUID
    name: str
    tags: list[str] | None

    def add_metadata(self, metadata: dict[str, object]) -> None: ...

    def add_tags(self, tags: list[str]) -> None: ...

    def create_child(self, name: str, run_type: str = "chain", **kwargs: object) -> _RunTree: ...

    def end(
        self,
        *,
        outputs: dict[str, object] | None = None,
        error: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def get_url(self) -> str | None: ...

    def patch(self, *, exclude_inputs: bool = False) -> None: ...

    def post(self, exclude_child_runs: bool = True) -> None: ...


class _RunTreeConstructor(Protocol):
    def __call__(
        self,
        *,
        id: uuid.UUID,
        name: str,
        run_type: str,
        inputs: dict[str, object],
        tags: list[str],
        extra: dict[str, object],
        project_name: str,
        ls_client: _LangSmithClient,
    ) -> _RunTree: ...


@dataclass
class _RuntimeConfig:
    configured: bool = False
    enabled: bool = False
    project: str = "upgradepilot-dev"
    endpoint: str = "https://api.smith.langchain.com"
    api_key: str | None = None
    hide_inputs: bool = False
    hide_outputs: bool = False
    status: ObservabilityStatus = ObservabilityStatus.DISABLED
    degraded_reason: str | None = None
    client_override: _LangSmithClient | None = None


@dataclass
class _TraceSession:
    analysis_id: str
    request_id: str | None
    trace_id: str
    root_run_id: str
    project: str
    status: ObservabilityStatus
    started_perf: float
    root_run: _RunTree | None = None
    posted: bool = False
    completed: bool = False
    degraded_reason: str | None = None
    trace_url: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChildRunHandle:
    """Local handle for a graph/node/tool/LLM child trace."""

    run_id: str
    name: str
    category: str
    started_perf: float
    run: _RunTree | None = None
    posted: bool = False


_RUNTIME = _RuntimeConfig()
_ACTIVE_TRACES: dict[str, _TraceSession] = {}

NodeResult = dict[str, Any]
NodeCallable = Callable[[UpgradePilotState], NodeResult | Awaitable[NodeResult]]

_NODE_CATEGORIES: dict[str, str] = {
    "validate_request": "node",
    "acquire_repository": "tool",
    "profile_repository": "node",
    "select_migration_pack": "node",
    "parse_dependencies": "tool",
    "scan_compatibility": "tool",
    "analyze_tests_and_ci": "tool",
    "documentation_research": "agent",
    "aggregate_analysis": "node",
    "calculate_risk": "tool",
    "compatibility_interpretation": "agent",
    "migration_planning": "agent",
    "deterministic_evidence_validator": "validator",
    "evidence_critic": "agent",
    "repair_plan": "node",
    "assemble_validated_report": "report",
    "assemble_partial_report": "report",
    "assemble_terminal_report": "report",
}


def configure_langsmith(
    *,
    api_key: str | None,
    project: str,
    endpoint: str,
    tracing_enabled: bool,
    hide_inputs: bool = False,
    hide_outputs: bool = False,
) -> bool:
    """
    Configure LangSmith environment and the local tracing runtime.

    Returns True when tracing is configured for LangSmith submission and False
    when observability is intentionally disabled/degraded.
    """
    _RUNTIME.configured = True
    _RUNTIME.project = project
    _RUNTIME.endpoint = endpoint
    _RUNTIME.api_key = api_key
    _RUNTIME.hide_inputs = hide_inputs
    _RUNTIME.hide_outputs = hide_outputs
    _RUNTIME.degraded_reason = None

    if not tracing_enabled or not api_key:
        os.environ["LANGSMITH_TRACING_V2"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        _RUNTIME.enabled = False
        _RUNTIME.status = ObservabilityStatus.DISABLED
        logger.info(
            "LangSmith tracing disabled",
            extra={"event": "tracing_disabled", "error_code": ErrorCode.OBSERVABILITY_DEGRADED},
        )
        return False

    os.environ["LANGSMITH_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGSMITH_ENDPOINT"] = endpoint
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    os.environ["LANGSMITH_HIDE_INPUTS"] = "true" if hide_inputs else "false"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true" if hide_outputs else "false"

    _RUNTIME.enabled = True
    _RUNTIME.status = ObservabilityStatus.CONFIGURED
    logger.info(
        "LangSmith tracing configured",
        extra={"event": "tracing_configured", "langsmith_project": project},
    )
    return True


def set_langsmith_client_for_tests(client: _LangSmithClient | None) -> None:
    """Inject a fake LangSmith client for local tests."""
    _RUNTIME.client_override = client


def reset_tracing_for_tests() -> None:
    """Clear global tracing state between tests."""
    _ACTIVE_TRACES.clear()
    _RUNTIME.client_override = None
    _RUNTIME.configured = False
    _RUNTIME.enabled = False
    _RUNTIME.status = ObservabilityStatus.DISABLED
    _RUNTIME.degraded_reason = None


def _client() -> _LangSmithClient:
    if _RUNTIME.client_override is not None:
        return _RUNTIME.client_override

    from langsmith import Client

    return cast(
        _LangSmithClient,
        Client(
            api_url=_RUNTIME.endpoint,
            api_key=_RUNTIME.api_key,
            timeout_ms=(1000, 2000),
            hide_inputs=_RUNTIME.hide_inputs,
            hide_outputs=_RUNTIME.hide_outputs,
            hide_metadata=False,
        ),
    )


def _run_tree_cls() -> _RunTreeConstructor:
    from langsmith import RunTree

    return cast(_RunTreeConstructor, RunTree)


def _request_data(state: Mapping[str, Any]) -> dict[str, Any]:
    request = state.get("request_data") or {}
    return cast(dict[str, Any], request)


def _snapshot_data(state: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = state.get("snapshot") or {}
    return cast(dict[str, Any], snapshot)


def _settings_metadata() -> dict[str, Any]:
    settings = get_settings()
    return {
        "application_version": settings.upgradepilot_version or __version__,
        "application_git_sha": settings.upgradepilot_git_sha,
        "environment": str(settings.upgradepilot_env),
        "model_provider": settings.llm_provider,
        "model": settings.llm_model,
    }


def _pack_metadata(pack_id: str) -> dict[str, Any]:
    if not pack_id:
        return {}
    try:
        from upgradepilot.migration.loader import load_all_packs

        pack = load_all_packs().get(pack_id)
        return pack.langsmith_metadata()
    except Exception as exc:
        logger.debug(
            "Could not load pack metadata for tracing: %s",
            type(exc).__name__,
            extra={"event": "trace_pack_metadata_unavailable"},
        )
        return {"pack_id": pack_id}


def build_trace_metadata(state: Mapping[str, Any]) -> dict[str, Any]:
    """Build required LangSmith metadata from typed graph state."""
    req = _request_data(state)
    snapshot = _snapshot_data(state)
    pack_id = str(state.get("pack_id") or req.get("migration_pack") or "")
    repo_owner = req.get("github_owner") or snapshot.get("owner") or ""
    repo_name = req.get("github_repo") or snapshot.get("repo") or ""
    analysis_mode = req.get("analysis_mode") or AnalysisMode.STANDARD
    report = state.get("final_report") or {}

    metadata: dict[str, Any] = {
        **_settings_metadata(),
        **_pack_metadata(pack_id),
        "analysis_id": state.get("analysis_id"),
        "request_id": req.get("request_id"),
        "repository_owner": repo_owner,
        "repository_name": repo_name,
        "repository": f"{repo_owner}/{repo_name}" if repo_owner and repo_name else None,
        "requested_ref": req.get("ref"),
        "resolved_commit_sha": snapshot.get("resolved_commit_sha"),
        "analysis_mode": str(analysis_mode),
        "report_status": state.get("report_status") or report.get("status") or "pending",
        "repair_count": state.get("repair_count", 0),
        "cache_hit": False,
        "cache_miss": False,
        "cache_status": "not_used",
        "finding_count": len(state.get("findings") or []),
        "evidence_count": len(state.get("documentation_evidence") or []),
        "validation_failure_count": len(state.get("validation_issues") or []),
        "unsupported_claim_count": sum(
            1
            for issue in state.get("validation_issues") or []
            if not cast(dict[str, Any], issue).get("repairable", True)
        ),
        "risk_level": (state.get("risk_assessment") or {}).get("level"),
        "final_status": state.get("status"),
    }
    return cast(dict[str, Any], sanitize_value(metadata, max_collection_items=100))


def build_trace_tags(state: Mapping[str, Any], *, status: str | None = None) -> list[str]:
    """Build stable LangSmith tags for the current state."""
    req = _request_data(state)
    pack_id = str(state.get("pack_id") or req.get("migration_pack") or "unknown")
    mode = str(req.get("analysis_mode") or "standard")
    source = "fixture" if mode == AnalysisMode.FIXTURE or mode == "fixture" else "live-github"
    final_status = status or str(state.get("report_status") or state.get("status") or "pending")
    repair_count = int(state.get("repair_count") or 0)
    env = _settings_metadata()["environment"]
    return [
        f"env:{env}",
        f"pack:{pack_id}",
        f"status:{final_status}",
        f"mode:{mode}",
        f"repair:{str(repair_count > 0).lower()}",
        f"source:{source}",
    ]


def _input_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    req = _request_data(state)
    return cast(
        dict[str, Any],
        sanitize_value(
            {
                "analysis_id": state.get("analysis_id"),
                "request_id": req.get("request_id"),
                "repository": req.get("repository_url"),
                "ref": req.get("ref"),
                "migration_pack": req.get("migration_pack"),
                "analysis_mode": str(req.get("analysis_mode") or ""),
            }
        ),
    )


def _output_summary(output: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in (
        "status",
        "report_status",
        "applicability_status",
        "validation_outcome",
        "repair_count",
    ):
        if key in output:
            summary[key] = output[key]
    for key in (
        "dependencies",
        "findings",
        "documentation_evidence",
        "validation_issues",
        "warnings",
        "errors",
    ):
        if key in output:
            values = output.get(key) or []
            summary[f"{key}_count"] = len(values)
            if values:
                summary[f"{key}_sample"] = sanitize_value(values[:3], max_string_chars=256)
    if "risk_assessment" in output and output["risk_assessment"]:
        risk = cast(dict[str, Any], output["risk_assessment"])
        summary["risk_level"] = risk.get("level")
        summary["risk_score"] = risk.get("total_score")
    if "final_report" in output and output["final_report"]:
        report = cast(dict[str, Any], output["final_report"])
        summary["final_report"] = {
            "status": report.get("status"),
            "finding_count": len(report.get("findings") or []),
            "validation_issue_count": len(report.get("validation_issues") or []),
        }
    return cast(dict[str, Any], sanitize_value(summary))


def _hidden(kind: str) -> dict[str, str]:
    return {kind: "hidden_by_configuration"}


def _mark_degraded(session: _TraceSession | None, reason: str) -> None:
    safe_reason = str(sanitize_value(reason, max_string_chars=256, max_lines=2))
    _RUNTIME.status = ObservabilityStatus.DEGRADED
    _RUNTIME.degraded_reason = safe_reason
    if session is not None:
        session.status = ObservabilityStatus.DEGRADED
        session.degraded_reason = safe_reason
    logger.warning(
        "LangSmith observability degraded",
        extra={
            "event": "OBSERVABILITY_DEGRADED",
            "error_code": ErrorCode.OBSERVABILITY_DEGRADED.value,
            "detail": safe_reason,
        },
    )


def start_analysis_trace(state: Mapping[str, Any]) -> dict[str, Any]:
    """Start the root analysis trace, returning state fields to merge."""
    analysis_id = str(state.get("analysis_id") or uuid.uuid4())
    existing = _ACTIVE_TRACES.get(analysis_id)
    if existing is not None:
        return _trace_state_fields(existing)

    req = _request_data(state)
    root_run_id = str(uuid.uuid4())
    trace_id = root_run_id
    metadata = build_trace_metadata(state)
    tags = build_trace_tags(state, status="running")
    status = _RUNTIME.status if _RUNTIME.configured else ObservabilityStatus.DISABLED
    session = _TraceSession(
        analysis_id=analysis_id,
        request_id=cast(str | None, req.get("request_id")),
        trace_id=trace_id,
        root_run_id=root_run_id,
        project=_RUNTIME.project,
        status=status,
        started_perf=time.perf_counter(),
        tags=tags,
        metadata=metadata,
    )
    _ACTIVE_TRACES[analysis_id] = session
    analyses_active.inc()

    if _RUNTIME.enabled:
        try:
            run_tree_cls = _run_tree_cls()
            run = run_tree_cls(
                id=uuid.UUID(root_run_id),
                name=ROOT_TRACE_NAME,
                run_type="chain",
                inputs=cast(
                    dict[str, object],
                    _hidden("inputs") if _RUNTIME.hide_inputs else _input_summary(state),
                ),
                tags=tags,
                extra=cast(dict[str, object], {"metadata": metadata}),
                project_name=_RUNTIME.project,
                ls_client=_client(),
            )
            run.post()
            session.root_run = run
            session.posted = True
            session.trace_id = str(run.trace_id)
            session.trace_url = run.get_url()
            session.status = ObservabilityStatus.CONFIGURED
        except Exception as exc:
            _mark_degraded(session, f"{type(exc).__name__}: {exc}")

    with log_context(
        request_id=session.request_id,
        analysis_id=session.analysis_id,
        trace_id=session.trace_id,
        run_id=session.root_run_id,
        repository=metadata.get("repository"),
        commit_sha=metadata.get("resolved_commit_sha"),
    ):
        logger.info(
            "Analysis trace started",
            extra={"event": "trace_started", "component": ROOT_TRACE_NAME},
        )

    return _trace_state_fields(session)


def _trace_state_fields(session: _TraceSession) -> dict[str, Any]:
    return {
        "trace_id": session.trace_id,
        "langsmith_root_run_id": session.root_run_id,
        "observability_status": session.status.value,
        "observability_degraded_reason": session.degraded_reason,
    }


def begin_child_run(
    state: Mapping[str, Any],
    *,
    name: str,
    category: str,
    run_type: str,
    inputs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    parent: _RunTree | None = None,
) -> ChildRunHandle:
    """Begin a child LangSmith run, degrading locally on SDK/API errors."""
    analysis_id = str(state.get("analysis_id") or "")
    session = _ACTIVE_TRACES.get(analysis_id)
    local_run_id = str(uuid.uuid4())
    handle = ChildRunHandle(
        run_id=local_run_id,
        name=name,
        category=category,
        started_perf=time.perf_counter(),
    )
    if session is None or not session.posted or session.root_run is None:
        return handle

    try:
        run_parent = parent or session.root_run
        run = run_parent.create_child(
            name=name,
            run_type=run_type,
            run_id=uuid.UUID(local_run_id),
            inputs=cast(
                dict[str, object],
                _hidden("inputs") if _RUNTIME.hide_inputs else sanitize_value(inputs or {}),
            ),
            tags=session.tags,
            extra=cast(
                dict[str, object],
                {"metadata": sanitize_value({**session.metadata, **(metadata or {})})},
            ),
        )
        run.post()
        handle.run = run
        handle.posted = True
        handle.run_id = str(run.id)
    except Exception as exc:
        _mark_degraded(session, f"{name}: {type(exc).__name__}: {exc}")
    return handle


def end_child_run(
    state: Mapping[str, Any],
    handle: ChildRunHandle,
    *,
    outputs: dict[str, Any] | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """End and patch a child run if LangSmith is available."""
    analysis_id = str(state.get("analysis_id") or "")
    session = _ACTIVE_TRACES.get(analysis_id)
    if session is None or handle.run is None or not handle.posted:
        return
    try:
        safe_outputs = (
            _hidden("outputs") if _RUNTIME.hide_outputs else sanitize_value(outputs or {})
        )
        safe_metadata = cast(dict[str, object], sanitize_value(metadata or {}))
        handle.run.end(
            outputs=cast(dict[str, object], safe_outputs),
            error=error,
            metadata=safe_metadata,
        )
        handle.run.patch(exclude_inputs=_RUNTIME.hide_inputs)
    except Exception as exc:
        _mark_degraded(session, f"{handle.name}: {type(exc).__name__}: {exc}")


def record_llm_trace(
    state: Mapping[str, Any],
    *,
    agent: str,
    status: str,
    usage: LLMUsage | None = None,
    metadata: dict[str, Any] | None = None,
    parent: _RunTree | None = None,
) -> None:
    """Record an LLM child run and associated Prometheus metrics."""
    usage = usage or LLMUsage()
    settings = get_settings()
    child = begin_child_run(
        state,
        name=f"llm.{agent}",
        category="llm",
        run_type="llm",
        inputs={"agent": agent},
        metadata={
            "llm_call_executed": status not in {"skipped", "not_called"},
            "status": status,
            "model_provider": settings.llm_provider,
            "model": settings.llm_model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "retry_count": usage.retry_count,
            **(metadata or {}),
        },
        parent=parent,
    )
    end_child_run(
        state,
        child,
        outputs={
            "status": status,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_cost_usd": usage.estimated_cost_usd,
        },
    )
    record_llm_usage(
        agent=agent,
        status=status,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )


def _node_status_from_result(result: dict[str, Any]) -> str:
    executions = result.get("node_executions") or []
    for execution in executions:
        if isinstance(execution, dict) and execution.get("status"):
            return str(execution["status"])
    if result.get("errors"):
        return "failed"
    return "completed"


def _node_metadata(
    state: Mapping[str, Any], node_name: str, result: dict[str, Any]
) -> dict[str, Any]:
    metadata = build_trace_metadata({**state, **result})
    metadata.update(
        {
            "node_name": node_name,
            "node_status": _node_status_from_result(result),
            "warning_count": len(result.get("warnings") or []),
            "error_count": len(result.get("errors") or []),
            "validation_issue_count": len(result.get("validation_issues") or []),
        }
    )
    return metadata


def _attach_run_id_to_node_records(result: dict[str, Any], node_name: str, run_id: str) -> None:
    records = result.get("node_executions") or []
    for record in records:
        if isinstance(record, dict) and record.get("node_name") == node_name:
            record["langsmith_run_id"] = run_id


def _inject_report_observability(result: dict[str, Any], observability: dict[str, Any]) -> None:
    report = result.get("final_report")
    if isinstance(report, dict):
        report["observability"] = observability


def _finish_report_if_needed(
    state: Mapping[str, Any],
    node_name: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    if _NODE_CATEGORIES.get(node_name) != "report":
        return {}
    merged = {**state, **result}
    observability = finish_analysis_trace(merged)
    _inject_report_observability(result, observability)
    return {
        "trace_id": observability.get("trace_id"),
        "langsmith_root_run_id": observability.get("langsmith_root_run_id"),
        "observability_status": observability.get("status"),
        "observability_degraded_reason": observability.get("degraded_reason"),
    }


def finish_analysis_trace(state: Mapping[str, Any]) -> dict[str, Any]:
    """Finish the root trace and return report-safe observability metadata."""
    analysis_id = str(state.get("analysis_id") or "")
    session = _ACTIVE_TRACES.get(analysis_id)
    if session is None:
        return {
            "trace_id": state.get("trace_id"),
            "langsmith_root_run_id": state.get("langsmith_root_run_id"),
            "langsmith_project": _RUNTIME.project,
            "langsmith_submitted": False,
            "status": ObservabilityStatus.DISABLED.value,
            "degraded_reason": "trace session was not active",
            "trace_url": None,
        }
    if session.completed:
        return _observability_report(session)

    duration = time.perf_counter() - session.started_perf
    final_status = str(state.get("report_status") or state.get("status") or "unknown")
    metadata = build_trace_metadata(state)
    metadata["graph_duration_seconds"] = round(duration, 6)
    tags = build_trace_tags(state, status=final_status)
    if session.root_run is not None and session.posted:
        try:
            session.root_run.add_metadata(metadata)
            session.root_run.add_tags(tags)
            outputs = _hidden("outputs") if _RUNTIME.hide_outputs else _output_summary(state)
            session.root_run.end(
                outputs=cast(dict[str, object], outputs),
                metadata=cast(dict[str, object], metadata),
            )
            session.root_run.patch(exclude_inputs=_RUNTIME.hide_inputs)
            session.trace_url = session.root_run.get_url()
        except Exception as exc:
            _mark_degraded(session, f"{type(exc).__name__}: {exc}")

    record_analysis_finished(status=final_status, duration_seconds=duration)
    try:
        analyses_active.dec()
    except ValueError:
        pass

    session.completed = True
    _ACTIVE_TRACES.pop(analysis_id, None)
    with log_context(
        request_id=session.request_id,
        analysis_id=session.analysis_id,
        trace_id=session.trace_id,
        run_id=session.root_run_id,
        repository=metadata.get("repository"),
        commit_sha=metadata.get("resolved_commit_sha"),
        duration_ms=round(duration * 1000, 3),
    ):
        logger.info(
            "Analysis trace finished",
            extra={"event": "trace_finished", "component": ROOT_TRACE_NAME},
        )
    return _observability_report(session)


def _observability_report(session: _TraceSession) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        sanitize_value(
            {
                "trace_id": session.trace_id,
                "langsmith_root_run_id": session.root_run_id,
                "langsmith_project": session.project,
                "langsmith_submitted": session.posted
                and session.status == ObservabilityStatus.CONFIGURED,
                "status": session.status.value,
                "degraded_reason": session.degraded_reason,
                "trace_url": session.trace_url,
            }
        ),
    )


def attach_user_feedback(feedback: UserFeedback) -> bool:
    """Attach user feedback to the root LangSmith run when it is available."""
    session = _ACTIVE_TRACES.get(feedback.analysis_id)
    run_id = (
        session.root_run_id
        if session is not None and session.posted
        else feedback.langsmith_root_run_id
    )
    trace_id = session.trace_id if session is not None and session.posted else feedback.trace_id
    if not run_id:
        logger.warning(
            "Feedback not attached because LangSmith trace is unavailable",
            extra={
                "event": "OBSERVABILITY_DEGRADED",
                "error_code": ErrorCode.OBSERVABILITY_DEGRADED.value,
                "analysis_id": feedback.analysis_id,
            },
        )
        return False
    try:
        client = _client()
        client.create_feedback(
            run_id=run_id,
            trace_id=trace_id,
            key=feedback.key,
            score=feedback.score,
            value=sanitize_value(feedback.value),
            comment=cast(str | None, sanitize_value(feedback.comment)),
            source_info=sanitize_value(
                {
                    "request_id": feedback.request_id,
                    "finding_id": feedback.finding_id,
                }
            ),
        )
        return True
    except Exception as exc:
        if session is not None:
            _mark_degraded(session, f"feedback: {type(exc).__name__}: {exc}")
        else:
            logger.warning(
                "Feedback attachment degraded",
                extra={
                    "event": "OBSERVABILITY_DEGRADED",
                    "error_code": ErrorCode.OBSERVABILITY_DEGRADED.value,
                    "analysis_id": feedback.analysis_id,
                },
            )
        return False


async def _call_node(func: NodeCallable, state: UpgradePilotState) -> dict[str, Any]:
    result = func(state)
    if inspect.isawaitable(result):
        awaited = await result
        return awaited
    return result


def instrument_graph_node(
    node_name: str,
    func: NodeCallable,
) -> Callable[[UpgradePilotState], Coroutine[Any, Any, dict[str, Any]]]:
    """Wrap a LangGraph node with LangSmith child traces, metrics, and log context."""
    category = _NODE_CATEGORIES.get(node_name, "node")
    run_name = f"{category}.{node_name}"
    run_type = "tool" if category == "tool" else "llm" if category == "llm" else "chain"

    async def wrapped(state: UpgradePilotState) -> dict[str, Any]:
        state_data: dict[str, Any] = dict(state)
        trace_update: dict[str, Any] = {}
        if node_name == "validate_request":
            trace_update = start_analysis_trace(state_data)
            state_data.update(trace_update)
        state_for_node = cast(UpgradePilotState, state_data)

        req = _request_data(state_for_node)
        snapshot = _snapshot_data(state_for_node)
        child = begin_child_run(
            state_for_node,
            name=run_name,
            category=category,
            run_type=run_type,
            inputs=_input_summary(state_for_node),
            metadata={"node_name": node_name, "category": category},
        )
        started = time.perf_counter()
        error_text: str | None = None
        result: dict[str, Any]
        with log_context(
            request_id=req.get("request_id"),
            analysis_id=state_for_node.get("analysis_id"),
            trace_id=state_for_node.get("trace_id"),
            run_id=child.run_id,
            repository=(
                f"{req.get('github_owner')}/{req.get('github_repo')}"
                if req.get("github_owner") and req.get("github_repo")
                else None
            ),
            commit_sha=snapshot.get("resolved_commit_sha"),
            node=node_name,
            component=run_name,
        ):
            logger.info("Graph node started", extra={"event": "node_started"})
            try:
                result = await _call_node(func, state_for_node)
            except Exception as exc:
                error_text = f"{type(exc).__name__}: {sanitize_value(str(exc))}"
                duration = time.perf_counter() - started
                end_child_run(
                    state_for_node,
                    child,
                    error=error_text,
                    metadata={"latency_seconds": duration, "node_status": "failed"},
                )
                record_graph_node_duration(
                    node=node_name,
                    category=category,
                    status="failed",
                    duration_seconds=duration,
                )
                logger.exception(
                    "Graph node failed",
                    extra={
                        "event": "node_failed",
                        "error_code": "UNHANDLED_NODE_ERROR",
                        "duration_ms": round(duration * 1000, 3),
                    },
                )
                raise

            duration = time.perf_counter() - started
            result.update(trace_update)
            _attach_run_id_to_node_records(result, node_name, child.run_id)
            if category == "agent" and node_name not in {
                "documentation_research",
                "compatibility_interpretation",
                "migration_planning",
                "evidence_critic",
            }:
                record_llm_trace(
                    state_for_node,
                    agent=node_name,
                    status="skipped",
                    metadata={"reason": "agent placeholder has no LLM call in Milestone 6"},
                    parent=child.run,
                )
            if category == "validator":
                record_validation_issues(
                    cast(list[dict[str, object]], result.get("validation_issues") or [])
                )

            node_status = _node_status_from_result(result)
            metadata = _node_metadata(state_for_node, node_name, result)
            metadata["latency_seconds"] = round(duration, 6)
            end_child_run(
                state_for_node,
                child,
                outputs=_output_summary(result),
                error=error_text,
                metadata=metadata,
            )
            record_graph_node_duration(
                node=node_name,
                category=category,
                status=node_status,
                duration_seconds=duration,
            )
            finish_update = _finish_report_if_needed(state_for_node, node_name, result)
            result.update(finish_update)
            logger.info(
                "Graph node completed",
                extra={
                    "event": "node_completed",
                    "duration_ms": round(duration * 1000, 3),
                    "node_status": node_status,
                },
            )
            return result

    return wrapped
