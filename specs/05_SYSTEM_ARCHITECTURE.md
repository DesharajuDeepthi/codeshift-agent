# 05 — System Architecture

## Containers

```text
browser
  |
streamlit-ui
  |
fastapi-api
  |
LangGraph application
  |------ PostgreSQL: checkpoints, analysis metadata
  |------ Redis: repository/document/API cache
  |------ GitHub and approved official sources
  |------ LLM provider
  |------ LangSmith Cloud: traces, datasets, experiments, evaluations
  |
prometheus <--- /metrics from API/UI
  |
grafana
```

## Application layers

### Interfaces

- Streamlit UI
- FastAPI REST API
- CLI for analysis and evaluation

### Orchestration

- LangGraph graph builder
- routing
- node wrappers
- graph state
- checkpoint configuration

### Agents

- documentation research
- compatibility interpretation
- migration planning
- evidence critic

### Deterministic domain services

- repository acquisition
- manifest parsing
- repository profiling
- AST scanning
- migration-pack rule engine
- risk scoring
- validation
- report assembly

### Integrations

- GitHub client
- trusted-document client
- LLM client
- LangSmith client/instrumentation
- Redis cache
- PostgreSQL checkpointing

## Architectural boundaries

- API models are not domain models.
- Agent schemas are not reused as persistence schemas without an adapter.
- Graph state stores references to large artifacts.
- Migration packs contain package-specific rules; core orchestration is package-neutral.
- LLM provider is replaceable.
- LangSmith is required for normal observability but not a source of business truth.
- Evaluation results are exportable to local JSON/Markdown even when LangSmith is used.

## Availability behavior

- Redis unavailable: continue without cache and emit warning.
- LangSmith unavailable: continue analysis, buffer/log trace failure, mark observability degraded.
- optional document refresh unavailable: use versioned curated snapshot and disclose retrieval age.
- PostgreSQL unavailable: reject new production analyses clearly; local unit tests may use in-memory checkpointer.
- LLM unavailable: return deterministic scan report with planning section unavailable.
