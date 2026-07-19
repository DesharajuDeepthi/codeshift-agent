# 19 — V2 Requirements: Multi-Tenant, Memory, Delta Detection

V2 extends UpgradePilot from a single-user demo to a multi-tenant production
architecture. The core LangGraph analysis graph is **not modified** — every V2
capability is added around it. Extension-without-rewrite is an explicit goal
and an explicit acceptance criterion.

## Goals

1. Multiple users can register (GitHub OAuth), log in, and run analyses
   concurrently without interfering with each other.
2. Every analysis is persisted per user; past reports re-open without re-running.
3. Re-analyzing a repository automatically produces a delta report
   (fixed / new / still-open findings) against that user's previous run.
4. Analysis execution moves to a Redis work queue with horizontally scalable
   workers and per-user fairness.
5. All V1 guarantees (read-only, deterministic findings, evidence validation,
   observability, eval harness) continue to hold.

## Non-Goals (explicitly deferred to V3+)

- Teams / organizations / shared workspaces
- Private repository analysis
- Webhooks or scheduled re-scans
- React or other SPA frontend (Streamlit is extended, not replaced)
- SSO (SAML/OIDC enterprise)
- Cross-repo user-preference memory

## Functional Requirements

### FR-1 Authentication (GitHub OAuth + JWT)

- FR-1.1 Users authenticate via GitHub OAuth (authorization-code flow).
- FR-1.2 On first login a `users` row is created (github_id, login, email,
  avatar_url, created_at).
- FR-1.3 Sessions use a short-lived JWT access token (≤ 8h) signed with
  `JWT_SECRET_KEY`; the UI stores it in Streamlit session state.
- FR-1.4 No passwords are ever stored. There is no password login path.
- FR-1.5 All `/analyses*` endpoints require a valid JWT; requests without one
  return 401 with `WWW-Authenticate: Bearer`.

### FR-2 Per-User Analysis History

- FR-2.1 `analyses` gains a non-null `user_id` FK; all queries are scoped by it.
- FR-2.2 `GET /users/me/analyses` lists the caller's runs: analysis_id,
  repository_url, ref, commit_sha, status, finding_count, created_at.
- FR-2.3 Stored reports (JSON/Markdown/issue drafts) re-open from Postgres
  without re-running the graph.
- FR-2.4 A user can never read, list, or delete another user's analyses
  (enforced in queries, not just UI).

### FR-3 Cross-Run Memory (LangGraph checkpointer)

- FR-3.1 `thread_id = sha256(f"{user_id}:{canonical_repo_url}")` — stable per
  user+repo, computed in one place (`memory/thread.py`).
- FR-3.2 The Postgres checkpointer already wired in V1 is keyed by this
  thread_id, so a re-analysis can read the prior run's findings and commit SHA.
- FR-3.3 Checkpoint reads are read-only with respect to the new run: prior
  state informs delta detection but never alters new findings.

### FR-4 Delta Detection

- FR-4.1 Automatically computed on every completed analysis where a prior
  completed run exists for the same thread_id.
- FR-4.2 Findings are compared as `(rule_id, file_path, start_line)` tuples —
  pure set difference, no LLM involvement, fully deterministic.
- FR-4.3 The delta report contains: fixed[], new[], still_open[],
  previous_commit_sha, current_commit_sha, and a one-line summary.
- FR-4.4 Delta appears in the report JSON, the Markdown export, and as a badge
  in the Streamlit UI ("2 fixed, 0 new since last run").
- FR-4.5 First-ever run for a repo shows "baseline run — no previous analysis".

### FR-5 Work Queue and Workers

- FR-5.1 `POST /analyses` enqueues an `AnalysisJob` to Redis and returns 202
  with the analysis_id; the API process never executes the graph.
- FR-5.2 Worker processes (`python -m upgradepilot.worker`) pull jobs and run
  the unchanged LangGraph graph; `docker compose up --scale worker=3` works.
- FR-5.3 Per-user fairness: jobs are drained round-robin across users so one
  user's burst cannot starve others.
- FR-5.4 Job lifecycle: queued → running → completed | failed. One retry on
  transient failure (network, GitHub 5xx); no retry on safety-limit errors.
- FR-5.5 Job state transitions are persisted and visible via the existing
  status endpoint.

### FR-6 Rate Limiting

- FR-6.1 Redis token bucket per user: default 10 analysis submissions/hour.
- FR-6.2 Exceeding the limit returns 429 with Retry-After.

## Data Model Changes (Alembic-managed)

```
users(user_id PK, github_id UNIQUE, login, email, avatar_url, created_at, is_active)
analyses(+ user_id FK NOT NULL, + thread_id, + delta JSONB NULL)
jobs(job_id PK, analysis_id FK, user_id FK, state, attempts, enqueued_at, started_at, finished_at)
```

- All schema changes ship as Alembic migrations. No hand-edited schemas.

## Security Requirements

- SR-1 OAuth state parameter validated; tokens exchanged server-side only.
- SR-2 The GitHub OAuth token is used for identity only, discarded after
  login, never stored, never used to access repositories.
- SR-3 JWT secret from environment; HS256; no secrets in code or logs.
- SR-4 Every Postgres query touching analyses/jobs filters by authenticated
  user_id (tested by cross-tenant access tests).
- SR-5 All V1 guardrails unchanged: read-only analysis, no shell=True, no
  execution of repository code, archive safety limits, SSRF blocks.

## Observability Requirements

- OR-1 New Prometheus metrics: queue depth, job wait time, jobs by state,
  per-user submission rate, delta computations.
- OR-2 Grafana dashboard gains a "Queue" row (depth, wait p95, worker count).
- OR-3 LangSmith traces tagged with user_id (hashed) and thread_id.

## Evaluation Requirements

- ER-1 Delta detector: unit-tested against fixture pairs (fixed / new /
  unchanged / first-run / all-fixed cases).
- ER-2 New eval suite `v2-delta`: given two pinned commits of a fixture repo,
  the delta report exactly matches the expected fixed/new/still-open sets.
- ER-3 Queue fairness test: two users submit 10 jobs each; completion
  interleaving must alternate users (no starvation).
- ER-4 All V1 eval suites still pass unchanged (40/40, zero hard failures).

## Definition of Done (V2)

- Two users in two browser sessions run concurrent analyses; each sees only
  their own history.
- Re-running a repo after a fix commit shows correct fixed/new counts.
- `docker compose up --scale worker=3` distributes jobs across workers.
- Rate limit returns 429 on the 11th submission in an hour.
- Alembic migrates a V1 database to V2 schema without data loss.
- Core graph diff between V1 and V2: zero lines changed in `graph/`.
- EVAL_RESULTS.md updated with V2 suite results alongside V1.
