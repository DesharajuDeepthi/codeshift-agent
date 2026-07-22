"""Prometheus metrics registry for UpgradePilot."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

# HTTP
http_requests_total = Counter(
    "upgradepilot_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)
http_request_duration_seconds = Histogram(
    "upgradepilot_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    registry=REGISTRY,
)

# Analyses
analyses_active = Gauge(
    "upgradepilot_analyses_active",
    "Currently running analyses",
    registry=REGISTRY,
)
analyses_total = Counter(
    "upgradepilot_analyses_total",
    "Total analyses by status",
    ["status"],
    registry=REGISTRY,
)
analysis_duration_seconds = Histogram(
    "upgradepilot_analysis_duration_seconds",
    "End-to-end analysis duration",
    ["status"],
    registry=REGISTRY,
)
graph_duration_seconds = Histogram(
    "upgradepilot_graph_duration_seconds",
    "LangGraph execution duration",
    ["status"],
    registry=REGISTRY,
)
graph_node_duration_seconds = Histogram(
    "upgradepilot_graph_node_duration_seconds",
    "LangGraph node duration",
    ["node", "category", "status"],
    registry=REGISTRY,
)
graph_node_runs_total = Counter(
    "upgradepilot_graph_node_runs_total",
    "LangGraph node executions",
    ["node", "category", "status"],
    registry=REGISTRY,
)

# LLM
llm_calls_total = Counter(
    "upgradepilot_llm_calls_total",
    "Total LLM calls by agent and status",
    ["agent", "status"],
    registry=REGISTRY,
)
llm_tokens_total = Counter(
    "upgradepilot_llm_tokens_total",
    "Total LLM tokens by direction",
    ["direction"],  # input / output
    registry=REGISTRY,
)

# External APIs
external_api_errors_total = Counter(
    "upgradepilot_external_api_errors_total",
    "External API errors by service",
    ["service"],
    registry=REGISTRY,
)

# Cache
cache_hits_total = Counter(
    "upgradepilot_cache_hits_total",
    "Cache hits by key type",
    ["key_type"],
    registry=REGISTRY,
)
cache_misses_total = Counter(
    "upgradepilot_cache_misses_total",
    "Cache misses by key type",
    ["key_type"],
    registry=REGISTRY,
)

# Validation
validation_issues_total = Counter(
    "upgradepilot_validation_issues_total",
    "Validation issues by severity",
    ["severity"],
    registry=REGISTRY,
)


def record_graph_node_duration(
    *,
    node: str,
    category: str,
    status: str,
    duration_seconds: float,
) -> None:
    """Emit graph node duration and execution count metrics."""
    graph_node_runs_total.labels(node=node, category=category, status=status).inc()
    graph_node_duration_seconds.labels(node=node, category=category, status=status).observe(
        duration_seconds
    )


def record_analysis_finished(*, status: str, duration_seconds: float) -> None:
    """Emit end-to-end analysis completion metrics."""
    analyses_total.labels(status=status).inc()
    analysis_duration_seconds.labels(status=status).observe(duration_seconds)
    graph_duration_seconds.labels(status=status).observe(duration_seconds)


def record_llm_usage(
    *,
    agent: str,
    status: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Emit LLM call and token counters."""
    llm_calls_total.labels(agent=agent, status=status).inc()
    if input_tokens:
        llm_tokens_total.labels(direction="input").inc(input_tokens)
    if output_tokens:
        llm_tokens_total.labels(direction="output").inc(output_tokens)


def record_external_api_error(*, service: str) -> None:
    """Emit an external API error counter."""
    external_api_errors_total.labels(service=service).inc()


def record_cache_event(*, key_type: str, hit: bool) -> None:
    """Emit cache hit or miss counters."""
    if hit:
        cache_hits_total.labels(key_type=key_type).inc()
    else:
        cache_misses_total.labels(key_type=key_type).inc()


def record_validation_issues(issues: list[dict[str, object]]) -> None:
    """Emit validation issue counters by severity."""
    for issue in issues:
        severity = str(issue.get("severity") or "unknown")
        validation_issues_total.labels(severity=severity).inc()


# Findings / cross-analysis memory
findings_persisted_total = Counter(
    "upgradepilot_findings_persisted_total",
    "Total findings persisted by pack",
    ["pack_id"],
    registry=REGISTRY,
)
delta_new_findings_total = Counter(
    "upgradepilot_delta_new_findings_total",
    "New findings introduced vs previous analysis by pack",
    ["pack_id"],
    registry=REGISTRY,
)
delta_resolved_findings_total = Counter(
    "upgradepilot_delta_resolved_findings_total",
    "Findings resolved vs previous analysis by pack",
    ["pack_id"],
    registry=REGISTRY,
)


def record_findings_persisted(*, pack_id: str, count: int) -> None:
    """Emit findings persistence counter for a pack."""
    findings_persisted_total.labels(pack_id=pack_id).inc(count)


def record_delta(*, pack_id: str, new_count: int, resolved_count: int) -> None:
    """Emit delta counters after cross-analysis comparison."""
    if new_count:
        delta_new_findings_total.labels(pack_id=pack_id).inc(new_count)
    if resolved_count:
        delta_resolved_findings_total.labels(pack_id=pack_id).inc(resolved_count)
