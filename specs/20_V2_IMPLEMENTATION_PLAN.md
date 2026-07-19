# 20 — V2 Implementation Plan (Build Order + Prompts)

Work happens on branch `v2/multi-user-memory`, merged to `main` via PR when the
V2 Definition of Done in spec 19 is met. Each phase is a separate commit (or
small commit series) so the history reads as a real engineering progression.

Rule for every phase: **`src/upgradepilot/graph/` is frozen.** If a phase seems
to need a graph change, stop and revisit the design — the extension points are
the API layer, the worker entrypoint, and the checkpointer thread_id.

---

## Phase 0 — Schema & Migrations

Add Alembic. Create migrations for `users`, `jobs`, and the new
`analyses.user_id / thread_id / delta` columns. Include a data migration that
assigns existing V1 rows to a sentinel "legacy" user.

Prompt:
> Add Alembic to the project wired to DATABASE_URL. Create migration 0001
> (users table), 0002 (jobs table), 0003 (analyses: user_id FK not null with
> legacy-user backfill, thread_id text, delta jsonb null). `alembic upgrade
> head` must succeed on both an empty database and a V1 database with rows.

Done when: upgrade/downgrade round-trips cleanly on both databases.

## Phase 1 — Delta Detector (pure logic first)

`delta/detector.py` + exhaustive unit tests. No I/O, no framework — the most
testable piece lands first and everything else composes around it.

Prompt:
> Implement compute_delta(previous_findings, current_findings) comparing
> (rule_id, file_path, start_line) tuples, returning fixed/new/still_open plus
> commit SHAs and a summary string. Cover: normal mixed case, first run,
> all fixed, all new, duplicate rule on different lines, same rule+file moved
> lines (counts as fixed+new, document why).

Done when: unit tests pass; behavior for moved lines documented in docstring.

## Phase 2 — Thread Identity + Memory

`memory/thread.py` (stable thread_id) and a small `memory/store.py` that reads
the previous completed run's findings for a thread_id from Postgres.

Prompt:
> make_thread_id(user_id, repo_url) — sha256 of user_id + canonicalized URL
> (lowercase, strip trailing slash and .git). load_previous_findings(thread_id)
> returns the most recent completed analysis findings + commit_sha or None.
> Property test: URL variants (trailing slash, case, .git suffix) map to the
> same thread_id; different users never collide.

Done when: property tests pass.

## Phase 3 — Auth (GitHub OAuth + JWT)

`auth/` package: OAuth callback endpoints, JWT issue/verify, FastAPI
dependency `get_current_user`, user upsert on first login.

Prompt:
> GET /auth/github/login (redirect with state) and /auth/github/callback
> (server-side code exchange, upsert users row, return JWT). HS256, 8h expiry,
> secret from env. get_current_user dependency returns user_id or 401.
> The GitHub token is used once for identity and discarded — assert it is
> never persisted or logged. Mock GitHub in all tests.

Done when: auth tests pass including expired/garbage tokens and the
cross-tenant access test (user A cannot read user B's analysis) fails closed.

## Phase 4 — Queue + Workers

`queue/` package and `worker.py` entrypoint. API enqueues; workers execute the
unchanged graph. Round-robin fairness across users.

Prompt:
> Redis-backed queue: per-user list `queue:user:{user_id}` plus a rotation of
> active users; workers pop round-robin so users interleave. Job lifecycle
> queued→running→completed|failed persisted to the jobs table; one retry on
> transient errors only. `python -m upgradepilot.worker` runs a worker loop;
> docker-compose adds a worker service with `--scale worker=N` support.
> Fairness test: user A enqueues 10, user B enqueues 2; B's jobs both finish
> within the first 4 completions.

Done when: fairness and lifecycle tests pass; API no longer executes graphs.

## Phase 5 — Wire Delta into Reports

After a worker completes an analysis: load previous findings by thread_id,
compute delta, store in `analyses.delta`, render into JSON/Markdown exports.

Prompt:
> On analysis completion, if a previous completed run exists for the
> thread_id, compute and persist the delta. Add a "Delta Since Last Run"
> section to the Markdown report and a `delta` block to the JSON report.
> First run stores null and renders "baseline run". The graph itself is not
> modified — this happens in the worker's post-completion step.

Done when: e2e fixture test shows correct delta across two runs; V1 report
schema remains backward-compatible (delta is additive).

## Phase 6 — Rate Limiting

Redis token bucket per user on POST /analyses. 10/hour default, env-tunable,
429 + Retry-After on excess.

## Phase 7 — UI

Streamlit: login-with-GitHub entry screen, history sidebar (past runs,
click to re-open stored report), delta badge on reports
("✅ 2 fixed · ⚠ 0 new since last run").

## Phase 8 — Observability + Evals + Docs

- Prometheus: queue depth, job wait p95, jobs by state, delta computations.
- Grafana: add Queue row to the dashboard.
- Eval suites: `v2-delta` (pinned two-commit fixture) and queue fairness;
  re-run all V1 suites — must stay 40/40.
- Update EVAL_RESULTS.md, README (move V2 section from "planned" to "shipped"),
  architecture doc, and ADR-0006 (queue-based execution) + ADR-0007
  (thread-scoped memory and deterministic delta).

---

## Commit / PR Etiquette

- Conventional commits (`feat:`, `test:`, `docs:`, `chore:`), one phase per
  commit series.
- Open a draft PR after Phase 1 so the branch shows review-ready progression;
  mark ready and merge after Phase 8.
- PR description: before/after architecture diagram, eval table, and the
  "zero lines changed in graph/" proof (`git diff main -- src/upgradepilot/graph/`).
