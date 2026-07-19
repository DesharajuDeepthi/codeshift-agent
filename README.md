# UpgradePilot

UpgradePilot is an agentic, evidence-validated migration intelligence system for
public Python repositories moving from Pydantic v1 to Pydantic v2.

It does not edit code, open pull requests, run repository tests, or claim a migration
will succeed. V1 produces read-only findings, risk scoring, official-documentation
evidence, and a reviewed migration plan that maintainers can use as a starting point.

## Why It Exists

Pydantic migrations are easy to underestimate: a repository can mix validators,
serialization methods, config classes, compatibility shims, dependency constraints,
and untested runtime behavior. UpgradePilot turns that repo-specific surface area into
an auditable report with exact files, exact lines, bounded snippets, official evidence,
and deterministic validation before anything is shown as a recommendation.

## What V1 Does

- Accepts a public GitHub repository URL and requested ref.
- Resolves the repository to a commit SHA.
- Profiles Python files, manifests, tests, CI, and Pydantic dependency signals.
- Scans source with deterministic AST rules from the Pydantic v1-to-v2 migration pack.
- Retrieves allowlisted official Pydantic documentation evidence with cached fallback.
- Calculates deterministic risk before planning.
- Uses bounded LLM agents for interpretation, planning, and one repair path.
- Validates every PlanClaim against known files, lines, findings, docs, packages, and rules.
- Exports JSON, Markdown, and GitHub issue-body drafts.
- Emits LangSmith traces, Prometheus metrics, and degraded-observability warnings.

## Architecture

```mermaid
flowchart LR
    U["Streamlit UI"] --> A["FastAPI API"]
    A --> G["LangGraph StateGraph"]
    G --> GH["GitHub public read-only API"]
    G --> P["Pydantic migration pack"]
    G --> D["Trusted docs cache/fetcher"]
    G --> L["Provider-neutral LLMClient"]
    G --> V["Deterministic validators"]
    G --> R["Report/export renderer"]
    G --> LS["LangSmith traces/evals"]
    G --> M["Prometheus metrics"]
    A --> PG["PostgreSQL readiness/checkpoints"]
    A --> RD["Redis optional cache"]
    M --> GF["Grafana dashboard"]
```

More detail: [docs/architecture.md](docs/architecture.md).

## Quick Start

Prerequisites:

- Python 3.12
- `uv`
- Docker and Docker Compose

Configure local environment:

```bash
cp .env.example .env
# Fill LLM_API_KEY for live LLM-backed analyses.
# Fill LANGSMITH_API_KEY to enable cloud traces and regression experiments.
```

Start the local stack:

```bash
docker compose up --build
```

Services:

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| API docs | http://localhost:8000/docs |
| API readiness | http://localhost:8000/health/ready |
| Metrics | http://localhost:8000/metrics |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

Run local development gates:

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv run python -m evals.run --suite smoke --backend local
```

## Demonstration

1. Start the stack with `docker compose up --build`.
2. Open http://localhost:8501.
3. Enter a public repository URL and ref.
4. Use `fixture` mode for a deterministic no-network demo, or `standard` mode for live
   public GitHub analysis.
5. Review the Facts, Evidence, Interpretations, Recommendations, Validation, and Exports tabs.
6. Download JSON, Markdown, or GitHub issue-body drafts.
7. Submit useful/not-useful feedback. If LangSmith is configured, feedback attaches to the root run.

Pinned public examples are documented in [docs/public_examples.md](docs/public_examples.md).

## API

Important endpoints:

- `POST /analyses`
- `GET /analyses/{analysis_id}`
- `GET /analyses/{analysis_id}/events`
- `GET /analyses/{analysis_id}/report`
- `GET /analyses/{analysis_id}/report.json`
- `GET /analyses/{analysis_id}/report.md`
- `GET /analyses/{analysis_id}/github-issue.md`
- `POST /analyses/{analysis_id}/feedback`

## Evaluation Results

Release evaluation results are recorded in [EVAL_RESULTS.md](EVAL_RESULTS.md). The local
evaluation harness writes machine-readable outputs under `eval_results/` during a run.

Commands:

```bash
uv run python -m evals.run --suite all --backend local
uv run python -m evals.run --suite regression --backend langsmith
uv run python -m evals.compare --baseline <name> --candidate <name>
```

## Security Posture

The repository under analysis is treated as attacker-controlled input. UpgradePilot does
not execute repository code. It rejects unsafe archives, blocks private-network SSRF
targets, bounds source snippets, masks secrets before logging/tracing, uses allowlisted
documentation sources, and validates generated claims deterministically.

Security notes:

- [docs/security/SECURITY.md](docs/security/SECURITY.md)
- [docs/security/SECURITY_SCAN_RESULTS.md](docs/security/SECURITY_SCAN_RESULTS.md)
- [docs/security/sbom.cdx.json](docs/security/sbom.cdx.json)

## Major Decisions

ADRs are in [docs/adr/](docs/adr/):

- LangGraph StateGraph orchestration
- deterministic evidence validation before reports
- trusted official documentation only
- degraded observability without analysis failure
- read-only V1 scope

## Known Limitations

See [docs/known_limitations.md](docs/known_limitations.md). In short: V1 supports public
repositories only, only the Pydantic v1-to-v2 pack, read-only recommendations, in-process
API analysis storage, and fixture-backed local public migration examples.

## Production Hardening Roadmap

See [docs/production_hardening_roadmap.md](docs/production_hardening_roadmap.md). Items
include durable analysis storage, stronger auth/rate limiting, managed secrets, external
container scanners, private repository support, and broader migration packs.
