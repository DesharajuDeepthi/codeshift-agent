# UpgradePilot — Agentic Migration Intelligence

> **Production-grade multi-tenant AI system** · LangGraph · pgvector · GitHub OAuth · Prometheus/Grafana · 327 tests · CI eval gate

[![Tests](https://img.shields.io/badge/tests-327%20passing-3FB950?style=flat-square&logo=pytest&logoColor=white)](https://github.com/DesharajuDeepthi/codeshift-agent/actions)
[![Eval Score](https://img.shields.io/badge/eval%20score-1.00%20%2F%201.00-3FB950?style=flat-square)](evals/)
[![CI Gate](https://img.shields.io/badge/CI%20gate-0.70%20threshold-2DD4BF?style=flat-square)](evals/run_evals.py)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-FF6B35?style=flat-square)](src/upgradepilot/graph/)

---

**[→ Interactive Showcase (live data)](https://claude.ai/code/artifact/d53579bb-eb37-4cdd-a36d-6a6c3b7d831c)**

---

UpgradePilot analyzes public GitHub repositories and generates evidence-validated
Pydantic v1→v2 migration plans. It treats the repository as **attacker-controlled input**,
never executes it, and backs every finding with bounded AST evidence and official documentation.

The V2 architecture adds **multi-tenant auth**, a **Redis job queue**, **cross-run delta detection**,
and **semantic long-term memory** via pgvector — all without touching the core LangGraph graph.

---

## Screenshots

### Streamlit UI — GitHub OAuth login + live analysis
![Streamlit UI showing 7 findings across PYD001/003/005/008/009/011](docs/screenshots/streamlit_ui.png)

### Grafana Observability Dashboard — 11 real-time panels
![Grafana dashboard showing HTTP requests, p95 latency, analyses by status, node durations](docs/screenshots/grafana_dashboard.png)

---

## LLM Eval Gate — CI Enforced

6 deterministic scorers run on every push. No LLM judge. Fails CI if average drops below 0.70.

```
$ uv run python evals/run_evals.py --fail-under 0.7

Running: fastapi-realworld-example-app...
  Applicability: SUPPORTED | Status: completed | 0.7s
  Scorer                        Score   Detail
  ──────────────────────────────────────────────────────────────
  applicability                 1.000  [██████████] PASS
  finding_count                 1.000  [██████████] PASS
  risk_score                    1.000  [██████████] PASS
  plan_keywords                 1.000  [██████████] PASS
  interpretation_coverage       1.000  [██████████] PASS
  no_hallucination              1.000  [██████████] PASS

Running: pydantic...
  Applicability: UNSUPPORTED | Status: terminal | 0.2s
  [all 6 scorers: 1.000 PASS]

================================================================
OVERALL AVERAGE SCORE:  1.000
CI THRESHOLD (0.70):    PASS
================================================================
```

---

## System Architecture

```
┌──────────────┐    ┌───────────┐    ┌─────────────────┐    ┌─────────────┐
│  GitHub User │───▶│   nginx   │───▶│  FastAPI + JWT  │───▶│ Redis Queue │
│  OAuth 2.0   │    │  :8080    │    │  auth + REST    │    │  job FIFO   │
└──────────────┘    └─────┬─────┘    └────────┬────────┘    └──────┬──────┘
                          │                   │                     │
                          ▼                   ▼                     ▼
                   ┌─────────────┐   ┌────────────────┐   ┌───────────────────┐
                   │  Streamlit  │   │   Prometheus   │   │  LangGraph Worker │
                   │     UI      │   │  + Grafana 11  │   │  5 agents · delta │
                   │  ngrok URL  │   │    panels      │   │  checkpointer     │
                   └─────────────┘   └────────────────┘   └────────┬──────────┘
                                                                    │
                                              ┌─────────────────────┼─────────────────┐
                                              ▼                     ▼                 ▼
                                     ┌──────────────┐    ┌──────────────────┐  ┌──────────┐
                                     │  PostgreSQL  │    │   pgvector       │  │LangSmith │
                                     │  analyses    │    │   semantic mem   │  │  traces  │
                                     │  users · ckp │    │   1536-dim emb   │  │  evals   │
                                     └──────────────┘    └──────────────────┘  └──────────┘
```

---

## V2 Capability at a Glance

| | V1 | V2 |
|---|---|---|
| Users | Anonymous | GitHub OAuth · JWT · multi-tenant |
| Analysis history | Lost on refresh | Persistent per-user in Postgres |
| Concurrency | Single-process | Redis queue + N workers |
| Cross-run memory | None | LangGraph checkpointer (thread_id) |
| Delta detection | None | Deterministic set-diff across runs |
| Long-term memory | None | pgvector · cosine similarity · injected into LLM prompts |
| Observability | Basic | Prometheus + Grafana 11-panel dashboard |
| Eval CI gate | None | LangSmith scorers · 0.70 threshold |
| Public access | localhost only | ngrok static domain · multi-user tested |

---

## Delta Detection — Continuous Migration Tracking

Most static analysis tools are **stateless scanners**: run once, get a report.
UpgradePilot turns into a **continuous migration tracker**: each re-analysis shows
exactly what was fixed, what's still open, and what's new.

```
Run 1  (2026-07-18, commit 029eb77):  7 findings
Run 2  (2026-07-25, commit a3f9c12):  5 findings

Delta:
  ✅ FIXED       PYD001  app/models.py:18       (.dict() → .model_dump())
  ✅ FIXED       PYD011  app/schemas.py:89      (Field alias removed)
  📌 STILL OPEN  5 findings remain
  ⚠️  NEW         (none introduced)
```

Implementation: pure set-diff on `(rule_id, file_path, start_line)` tuples — deterministic, fast, zero LLM.

---

## Semantic Long-Term Memory

After each analysis the worker embeds all findings with **OpenAI text-embedding-3-small**
(1536 dims) and stores them in a **pgvector IVFFlat index**. On the next analysis, the
compatibility interpretation agent retrieves the top-3 most similar past findings by
cosine similarity (threshold 0.75) and injects them as context into the LLM prompt.

The system literally learns from every past analysis run.

---

## 8-Phase V2 Build

| Phase | What landed | Tests |
|---|---|---|
| 0 | Alembic migrations — `users`, `jobs`, `analyses` tables | — |
| 1 | Delta detector — deterministic `(rule_id, file_path, line)` set-diff | 8 |
| 2 | Thread ID memory — `sha256(user_id + repo_url)` LangGraph scoping | 10 |
| 3 | GitHub OAuth + JWT — `/auth/login`, `/auth/callback`, HS256 8h tokens | 9 |
| 4 | Redis work queue — per-user lists, round-robin fairness, FIFO | 9 |
| 5 | Analysis worker — claim → run graph → delta → persist → ack | 8 |
| 6 | Rate limiting — Redis token bucket, 10 req/60s, WATCH/MULTI/EXEC | 7 |
| 7 | Streamlit UI — GitHub login, history sidebar, delta badge | 6 |
| 8 | Prometheus + Grafana + LangSmith eval gate + pgvector semantic memory | — |
| **Total** | **85 modules · 12,693 lines** | **327 tests · 0 failures** |

> **Zero graph changes across all 8 phases.** `git diff main -- src/upgradepilot/graph/` is empty.
> All V2 capability composes *around* the existing LangGraph, not *into* it.

---

## Tech Stack

**AI / Agents**
`LangGraph` · `LangSmith` · `OpenAI text-embedding-3-small` · `pgvector IVFFlat` · `httpx LLM client`

**Backend**
`FastAPI` · `SQLAlchemy` · `psycopg3` · `Redis` · `PostgreSQL 16` · `Alembic`

**Auth & Security**
`GitHub OAuth 2.0` · `JWT HS256` · `rate limiting` · `SSRF protection` · `archive safety`

**Observability**
`Prometheus` · `Grafana 11` · `LangSmith traces` · `structured logging`

**Infrastructure**
`Docker Compose` · `nginx reverse proxy` · `ngrok static domain` · `Python 3.12` · `uv`

**Quality**
`ruff` · `mypy` · `pytest 327 tests` · `deterministic CI eval gate`

---

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/DesharajuDeepthi/codeshift-agent.git
cd codeshift-agent
cp .env.example .env
# Set LLM_API_KEY, LANGSMITH_API_KEY, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET

# 2. Start everything
docker compose up --build

# 3. Open the UI
open http://localhost:8080   # nginx proxy (API + UI on one port)
```

| Service | URL |
|---|---|
| UI (via nginx) | http://localhost:8080 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health/ready |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

```bash
# Run full quality gate
uv run ruff check . && uv run mypy src && uv run pytest && uv run python evals/run_evals.py --fail-under 0.7
```

---

## Security Posture

The repository under analysis is treated as **attacker-controlled input**. UpgradePilot:
- Never executes repository code
- Rejects unsafe archives (symlink traversal, hardlink escape)
- Blocks SSRF to private network ranges
- Bounds source snippets before LLM calls
- Masks secrets before logging/tracing
- Validates every generated claim against known files, lines, findings, and rules

See [docs/security/SECURITY.md](docs/security/SECURITY.md).

---

## Repository

Branch: [`v2/multi-user-memory`](https://github.com/DesharajuDeepthi/codeshift-agent/tree/v2/multi-user-memory)
Interactive showcase: [claude.ai/code/artifact/d53579bb-eb37-4cdd-a36d-6a6c3b7d831c](https://claude.ai/code/artifact/d53579bb-eb37-4cdd-a36d-6a6c3b7d831c)
