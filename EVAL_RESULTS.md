# UpgradePilot V1 Evaluation Results

Generated during the final Definition of Done audit on 2026-07-18.

## Local Full Suite

- Command: `uv run python -m evals.run --suite all --backend local`
- Status: `completed`
- Passed: `True`
- Experiment: `upgradepilot-v1-all-0.1.0-1.0.0-20260718-1345`
- Cases: `40`
- Evaluated cases: `40`
- Passed cases: `40`
- Hard failures: `0`

Hard metrics:

| Metric | Value |
|---|---:|
| applicability_pass_rate | 1.0 |
| detection_pass_rate | 1.0 |
| planning_pass_rate | 1.0 |
| chaos_pass_rate | 1.0 |
| public_migrations_pass_rate | 1.0 |
| valid_file_references | 1.0 |
| valid_line_references | 1.0 |
| valid_source_references | 1.0 |
| prohibited_claim_count | 0 |
| unsupported_claim_count | 0 |
| call_budget_compliance | 1.0 |
| correct_graph_routing | 1.0 |
| graceful_chaos_handling | 1.0 |
| schema_valid_agent_outputs | 1.0 |

Semantic local metrics were not run as LLM judges in the deterministic local backend.

## LangSmith Regression Suite

- Command: `uv run python -m evals.run --suite regression --backend langsmith`
- Status: `completed`
- Passed: `True`
- Experiment: `upgradepilot-v1-regression-0.1.0-1.0.0-20260718-1345`
- LangSmith experiment: https://smith.langchain.com/o/b9b585f1-9466-4ed3-b037-3571dd5968b2/projects/p/00efe1d2-62e9-4360-994a-6cc5a50264ba
- Warning: Semantic LangSmith judges are advisory and cannot override deterministic failures.
- Cases: `40`
- Evaluated cases: `40`
- Passed cases: `40`
- Hard failures: `0`

Hard metrics matched the local full suite:

| Metric | Value |
|---|---:|
| hard_metrics_passed | True |
| valid_file_references | 1.0 |
| valid_line_references | 1.0 |
| valid_source_references | 1.0 |
| prohibited_claim_count | 0 |
| unsupported_claim_count | 0 |
| public_migrations_pass_rate | 1.0 |

## Baseline Comparison

- Command: `uv run python -m evals.compare --baseline upgradepilot-v1-all-0.1.0-1.0.0-20260718-1345 --candidate upgradepilot-v1-regression-0.1.0-1.0.0-20260718-1345`
- Passed: `true`
- Hard metric regressions: none

Tracked deltas were all zero for:

- `hard_failure_count`
- `valid_file_references`
- `valid_line_references`
- `valid_source_references`
- `prohibited_claim_count`
- `unsupported_claim_count`
- `call_budget_compliance`
- `correct_graph_routing`
- `graceful_chaos_handling`
- `schema_valid_agent_outputs`

## Public Migration Examples

The full and regression suites include two pinned public examples:

| Case | Repository | Ref | Pinned Commit SHA | Passed |
|---|---|---|---|---:|
| pydantic-v1.10.15-release | `https://github.com/pydantic/pydantic` | `v1.10.15` | `5476a758c8ac59887dbfa3aa1c3481d0a0e20837` | True |
| fastapi-0.95.2-release | `https://github.com/fastapi/fastapi` | `0.95.2` | `8cc967a7605d3883bd04ceb5d25cc94ae079612f` | True |

These cases verify pinned documentation/demo metadata in the local evaluator. They do not
claim code was modified, repository tests were executed, or migrations succeeded.
