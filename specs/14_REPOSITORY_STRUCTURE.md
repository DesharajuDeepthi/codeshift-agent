# 14 — Repository Structure

```text
upgradepilot/
├── CLAUDE.md
├── README.md
├── EVAL_RESULTS.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .dockerignore
├── langgraph.json
├── specs/
├── docs/
│   ├── architecture.md
│   ├── adr/
│   └── diagrams/
├── migration_packs/
│   └── pydantic_v1_to_v2/
├── src/upgradepilot/
│   ├── api/
│   ├── ui/
│   ├── cli/
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── edges.py
│   │   ├── reducers.py
│   │   └── build.py
│   ├── agents/
│   │   ├── documentation_research.py
│   │   ├── compatibility_interpretation.py
│   │   ├── migration_planning.py
│   │   └── evidence_critic.py
│   ├── analyzers/
│   │   ├── repository_profile.py
│   │   ├── dependency_parser.py
│   │   ├── python_ast.py
│   │   └── test_ci.py
│   ├── migration/
│   │   ├── loader.py
│   │   ├── contracts.py
│   │   ├── rule_engine.py
│   │   └── risk.py
│   ├── tools/
│   │   ├── github.py
│   │   ├── safe_archive.py
│   │   ├── repository_index.py
│   │   ├── documents.py
│   │   └── evidence.py
│   ├── validators/
│   │   ├── files.py
│   │   ├── lines.py
│   │   ├── citations.py
│   │   ├── claims.py
│   │   └── report.py
│   ├── reports/
│   │   ├── assembler.py
│   │   ├── markdown.py
│   │   └── issue_body.py
│   ├── integrations/
│   │   ├── llm.py
│   │   ├── langsmith.py
│   │   ├── cache.py
│   │   └── checkpoint.py
│   ├── observability/
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   ├── tracing.py
│   │   └── redaction.py
│   ├── models/
│   ├── config.py
│   └── errors.py
├── evals/
│   ├── run.py
│   ├── sync_dataset.py
│   ├── compare.py
│   ├── evaluators/
│   ├── datasets/
│   ├── fixtures/
│   └── results/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   └── security/
├── prometheus/
├── grafana/
└── .github/workflows/
```

## Structure rules

- No agent business logic in API routes.
- No LLM calls outside `integrations/llm.py`.
- No LangSmith-specific business decisions.
- Migration-pack-specific rules do not leak into core graph modules.
- Tests mirror source areas.
- Evaluation code remains distinct from unit tests.
