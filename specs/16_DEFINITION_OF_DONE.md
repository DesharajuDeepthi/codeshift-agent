# 16 — Definition of Done

UpgradePilot V1 is complete only when all are true.

## Product

- Public GitHub URL can be analyzed end-to-end.
- Repository is resolved to a commit SHA.
- Supported Pydantic v1 repository returns findings with valid files/lines.
- Risk score is deterministic and explainable.
- Migration/test/rollout/rollback plan is generated.
- Markdown, JSON, and issue-body exports work.
- Unsupported/not-applicable/partial outcomes are clear.

## Agentic architecture

- LangGraph topology matches the specification.
- Four agents have bounded contracts and allowlisted tools.
- Parallel branches work.
- One repair path is enforced.
- Every path terminates.
- PostgreSQL checkpointing and resume are tested.

## Evidence and safety

- 100% valid file references.
- 100% valid line references.
- 100% valid documentation references.
- Zero unsupported factual claims in release eval.
- Zero claims that code or tests were executed.
- Repository code is never executed.
- Unsafe archives and prompt injection fixtures pass.
- Secrets are not present in logs or traces.

## LangSmith observability

- Complete root and child traces exist.
- Required tags/metadata are present.
- Tokens, cost, latency, retries, errors, and validation outcomes are visible.
- Trace masking/redaction is verified.
- User feedback attaches to root runs.
- LangSmith outage produces degraded-observability warning without breaking analysis.

## Evaluation

- Local full suite passes.
- LangSmith regression experiment runs.
- Hard metric targets pass.
- Baseline comparison is documented.
- `EVAL_RESULTS.md` contains real results, not placeholders.
- Chaos and trajectory suites pass.

## Docker and operations

- `docker compose up --build` starts all local services.
- API, UI, PostgreSQL, Redis, Prometheus, and Grafana are healthy.
- `.env.example` is complete.
- containers run as non-root where practical.
- health/readiness/metrics endpoints work.
- CI executes required gates.

## Portfolio quality

- README has problem, architecture, screenshots/demo, usage, results, decisions, limitations, and roadmap.
- Architecture diagram reflects implementation.
- At least two public pinned migration cases are demonstrated.
- No exaggerated claims.
- Repository is understandable to a hiring manager in five minutes.
