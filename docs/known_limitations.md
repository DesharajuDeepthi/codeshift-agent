# Known Limitations

UpgradePilot V1 is intentionally narrow.

- Public GitHub repositories only.
- Pydantic v1-to-v2 migration pack only.
- Read-only recommendations only. V1 does not modify repositories, open PRs, or write to GitHub.
- Repository tests are never executed by UpgradePilot.
- Static findings may miss dynamic Pydantic usage, metaprogramming, generated code, or runtime-only behavior.
- LLM-produced interpretations and plans are constrained and validated, but usefulness outside evaluated datasets is not guaranteed.
- API analysis records are stored in process memory in the Milestone 11 UI/API implementation.
- Public migration examples are pinned and documented locally; the local evaluator does not perform live GitHub analysis for those cases.
- Container security scanning is local/static unless an external scanner such as Trivy or Docker Scout is run separately.
- The default Compose credentials are local development defaults and must not be used in shared or production environments.
