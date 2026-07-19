# Operations

## Local Startup

```bash
cp .env.example .env
docker compose up --build
```

Expected services:

- API: http://localhost:8000
- UI: http://localhost:8501
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- PostgreSQL and Redis internal to Compose

## Health and Readiness

- `/health/live` returns process liveness.
- `/health/ready` returns 503 when required dependencies are down.
- PostgreSQL is required.
- Redis is optional and reports degraded readiness when unavailable.
- LangSmith is optional for analysis continuity and reports degraded/disabled when unavailable.

## Metrics

Prometheus scrapes the API `/metrics` endpoint. Metrics include HTTP volume/latency,
active analyses, graph duration, node duration, external API errors, cache events, LLM
calls/tokens, and validation issues.

## LangSmith

Set `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true` to enable cloud traces. If LangSmith
is unavailable, analysis should continue with degraded-observability metadata in reports.

## Evaluation

```bash
uv run python -m evals.run --suite smoke --backend local
uv run python -m evals.run --suite all --backend local
uv run python -m evals.run --suite regression --backend langsmith
```

Missing LangSmith credentials should skip only the cloud experiment.

## Security Artifacts

```bash
uv run python scripts/security_scan.py --markdown-output docs/security/SECURITY_SCAN_RESULTS.md
uv run python scripts/generate_sbom.py --output docs/security/sbom.cdx.json
```

The local scan excludes `.env`, caches, virtualenvs, and tests containing synthetic keys.
