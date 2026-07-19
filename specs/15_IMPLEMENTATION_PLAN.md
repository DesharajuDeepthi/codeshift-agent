# 15 — Implementation Plan

## Milestone 0 — Repository foundation

Deliver:

- project skeleton;
- `uv` configuration;
- quality tooling;
- configuration model;
- Dockerfile and Compose placeholders;
- FastAPI/Streamlit health screens;
- LangSmith environment setup;
- CI skeleton.

Acceptance:

- containers build;
- lint/type/test commands run;
- no business logic yet.

## Milestone 1 — Safe repository ingestion

Deliver:

- request model;
- GitHub URL parser;
- ref-to-SHA resolution;
- safe archive download/extraction;
- workspace lifecycle;
- repository index;
- security tests.

Acceptance:

- pinned fixture repository can be acquired;
- unsafe archives rejected;
- no code execution.

## Milestone 2 — Repository profiling and dependencies

Deliver:

- Python repository profile;
- `requirements.txt` parser;
- `pyproject.toml` parser;
- test/CI detection;
- applicability signals.

Acceptance:

- expected manifests, tests, CI, runtime, and Pydantic evidence detected in fixtures.

## Milestone 3 — Migration-pack framework

Deliver:

- pack loader and contracts;
- Pydantic pack metadata;
- applicability rules;
- versioned detection/risk/source files;
- pack validation at startup.

Acceptance:

- invalid packs fail startup clearly;
- pack can be loaded without graph-specific code.

## Milestone 4 — Deterministic compatibility scanner

Deliver:

- AST engine;
- initial Pydantic rules;
- exact findings and lines;
- negative fixtures;
- exclusions.

Acceptance:

- precision/recall targets pass fixture evaluation;
- every rule has tests.

## Milestone 5 — LangGraph orchestration and persistence

Deliver:

- typed state;
- reducers;
- nodes and edges;
- parallel analysis branches;
- PostgreSQL checkpointer;
- streaming progress;
- terminal reports.

Acceptance:

- full deterministic graph executes;
- resume/checkpoint integration test passes;
- routes are tested.

## Milestone 6 — LangSmith observability

Deliver:

- root/child trace naming;
- metadata/tags;
- LLM/tool/node tracing;
- redaction;
- user feedback hook;
- degraded behavior;
- Prometheus metrics and Grafana dashboard.

Acceptance:

- one analysis appears as a complete LangSmith trace;
- tokens/cost/latency visible;
- no secrets/full files in traces;
- local metrics visible.

## Milestone 7 — Trusted documentation agent

Deliver:

- approved source catalog;
- cached curated snapshots;
- source refresh;
- documentation research agent;
- typed evidence.

Acceptance:

- only allowlisted sources used;
- rules map to valid evidence;
- source failure behavior tested.

## Milestone 8 — Compatibility and planning agents

Deliver:

- provider-neutral LLM client;
- prompts and schema outputs;
- compatibility interpretation;
- deterministic risk score;
- migration planning;
- token/call budgets.

Acceptance:

- plan references only known findings/evidence;
- no test-execution or code-change claims;
- fake-LLM E2E passes.

## Milestone 9 — Validation and repair

Deliver:

- deterministic validators;
- semantic evidence critic;
- one repair path;
- validated/partial report assembly.

Acceptance:

- unsupported claims are blocked;
- repair succeeds for repairable fixture;
- second failure terminates partial.

## Milestone 10 — Evaluation harness

Deliver:

- local datasets;
- LangSmith dataset sync;
- deterministic, semantic, and trajectory evaluators;
- experiments and baseline comparison;
- Markdown/JSON/JUnit results.

Acceptance:

- all hard release gates pass;
- experiment visible in LangSmith;
- baseline comparison works.

## Milestone 11 — UI, API, exports

Deliver:

- analysis form;
- progress stream;
- evidence/finding/risk/report views;
- Markdown/JSON/issue-body export;
- feedback submission.

Acceptance:

- user completes supported analysis from UI;
- trace correlation and report metadata shown safely.

## Milestone 12 — Hardening and portfolio release

Deliver:

- chaos tests;
- security checks;
- docs/diagram;
- demo GIF/video plan;
- real evaluation results;
- known limitations;
- ADRs;
- final Compose validation.

Acceptance:

- Definition of Done is fully checked with evidence.

## Rule

Claude Code must complete milestones sequentially. It may create interfaces needed by the next milestone, but it must not implement Version 2 features early.
