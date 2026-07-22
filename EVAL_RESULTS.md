# UpgradePilot V1 Evaluation Results

Most recent smoke suite: 2026-07-22. Full suite and LangSmith regression: 2026-07-18.

## Smoke Suite (2026-07-22)

- Command: `uv run python -m evals.run --suite smoke --backend local`
- Status: `completed`
- Passed: `True`
- Experiment: `upgradepilot-v1-smoke-0.1.0-1.0.0-20260722-0509`
- Cases: `51`
- Evaluated cases: `51`
- Passed cases: `51`
- Hard failures: `0`

Hard metrics:

| Metric | Value |
|---|---:|
| applicability_pass_rate | 1.0 |
| call_budget_compliance | 1.0 |
| chaos_pass_rate | 1.0 |
| correct_graph_routing | 1.0 |
| detection_pass_rate | 1.0 |
| graceful_chaos_handling | 1.0 |
| hard_metrics_passed | True |
| planning_pass_rate | 1.0 |
| prohibited_claim_count | 0 |
| schema_valid_agent_outputs | 1.0 |
| unsupported_claim_count | 0 |
| valid_file_references | 1.0 |
| valid_line_references | 1.0 |
| valid_source_references | 1.0 |

Semantic metrics were not run (local deterministic backend).

### Case breakdown

**Pydantic detection (26 cases)**

| Case | Group | Passed |
|---|---|---:|
| pyd001_pos | detection | True |
| pyd001_neg | detection | True |
| pyd002_pos | detection | True |
| pyd002_neg | detection | True |
| pyd003_008_pos | detection | True |
| pyd003_neg | detection | True |
| pyd004_neg | detection | True |
| pyd009_011_pos | detection | True |
| pyd009_neg | detection | True |
| pyd012_015_pos | detection | True |
| pyd014_pos | detection | True |
| pyd012_neg | detection | True |
| pyd016_017_pos | detection | True |
| pyd016_neg | detection | True |
| pyd018_pos | detection | True |
| pyd018_neg | detection | True |
| pyd019_pos | detection | True |
| pyd019_neg | detection | True |
| pyd020_pos | detection | True |
| pyd020_neg | detection | True |
| pyd021_pos | detection | True |
| pyd021_neg | detection | True |
| pyd022_pos | detection | True |
| pyd022_neg | detection | True |
| mixed_v1_pos | detection | True |
| mixed_v2_neg | detection | True |

**Django detection (11 cases)**

| Case | Group | Passed |
|---|---|---:|
| djg001-model-class | detection | True |
| djg002-use-l10n | detection | True |
| djg003-csrf-origins | detection | True |
| djg004-timezone-utc | detection | True |
| djg005-conf-url | detection | True |
| djg006-force-text | detection | True |
| djg007-smart-text | detection | True |
| djg008-ugettext | detection | True |
| djg009-conn-max-age | detection | True |
| djg010-formfield-callback | detection | True |
| django-v4-negative | detection | True |

**Applicability (6 cases)**

| Case | Group | Passed |
|---|---|---:|
| requirements-pydantic-v1 | applicability | True |
| pep621-pydantic-v2 | applicability | True |
| no-pydantic-python | applicability | True |
| unpinned-pydantic | applicability | True |
| malformed-manifests | applicability | True |
| requirements-django-v3 | applicability | True |

**Planning (2 cases)**

| Case | Group | Passed |
|---|---|---:|
| grounded-plan-single-finding | planning | True |
| repairable-wording | planning | True |

**Chaos (6 cases)**

| Case | Group | Passed |
|---|---|---:|
| github-acquisition-failure | chaos | True |
| unsupported-terminates-early | chaos | True |
| structural-validation-partial | chaos | True |
| single-repair-success | chaos | True |
| second-validation-failure | chaos | True |
| auto-detect-selects-best-pack | chaos | True |

---

## Local Full Suite (2026-07-18)

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

## LangSmith Regression Suite (2026-07-18)

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

## Baseline Comparison (2026-07-18)

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
