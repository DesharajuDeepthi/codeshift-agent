# 10 — Evaluation Harness

## Goals

The harness must measure both deterministic software correctness and agent quality. It must support:

1. local reproducible fixture evaluation;
2. LangSmith dataset experiments;
3. component-level evaluation;
4. end-to-end graph evaluation;
5. trajectory evaluation;
6. regression comparison across versions.

## Commands

```bash
python -m evals.run --suite smoke --backend local
python -m evals.run --suite all --backend local
python -m evals.run --suite regression --backend langsmith
python -m evals.sync_dataset
python -m evals.compare --baseline <name> --candidate <name>
```

## Dataset groups

### D1 Applicability

- clear Pydantic v1;
- clear Pydantic v2;
- no Pydantic;
- ambiguous/unpinned;
- compatibility namespace;
- malformed manifests.

### D2 Detection

Small repository fixtures with exact expected:

- rule IDs;
- files;
- line ranges;
- severity;
- exclusions.

### D3 Planning

Fixtures with expected plan requirements, prohibited claims, evidence mappings, and required review flags.

### D4 Chaos and resilience

Inject:

- GitHub timeout;
- rate limit;
- unsafe archive;
- corrupt archive;
- syntax-error file;
- document-source failure;
- Redis outage;
- LangSmith outage;
- malformed LLM output;
- LLM timeout;
- invalid evidence reference;
- second validation failure.

### D5 Public migration cases

Selected public repositories at a commit before a known Pydantic migration. Compare system predictions with the actual migration diff or merged PR. Pin commit SHAs to keep cases reproducible.

## Evaluators

### Deterministic evaluators

- request/schema validity;
- applicability accuracy;
- dependency detection accuracy;
- finding precision;
- finding recall;
- exact file-reference validity;
- line-range validity;
- rule-ID validity;
- documentation-source validity;
- risk-score reproducibility;
- evidence coverage;
- prohibited-claim count;
- graceful failure;
- graph termination;
- call-budget compliance.

### Semantic evaluators

Use LangSmith LLM-as-judge only for:

- usefulness of impact explanation;
- plan coherence;
- ordering quality;
- clarity;
- sufficiency of human-review warnings.

Semantic scores cannot override hard deterministic failures.

### Trajectory evaluators

Check:

- expected nodes executed;
- correct branches selected;
- no forbidden tools;
- no unnecessary repair;
- at most one repair;
- report assembly occurs after validation;
- unsupported cases terminate early.

## Core metrics and release targets

| Metric | Target |
|---|---:|
| Valid file references | 100% |
| Valid line references | 100% |
| Valid source references | 100% |
| Unsupported factual claims | 0 |
| Prohibited test/code-change claims | 0 |
| Rule precision | >= 95% |
| Rule recall on supported fixtures | >= 90% |
| Applicability accuracy | >= 95% |
| Correct graph routing | 100% |
| Graceful chaos-case handling | 100% |
| Schema-valid agent outputs | 100% |
| Call-budget compliance | 100% |
| p50 standard fixture latency | tracked |
| Cost per live analysis | tracked |

## LangSmith datasets

Create versioned datasets:

- `upgradepilot-v1-applicability`
- `upgradepilot-v1-detection`
- `upgradepilot-v1-planning`
- `upgradepilot-v1-chaos`
- `upgradepilot-v1-public-migrations`

Each example contains:

- inputs;
- reference outputs or assertions;
- fixture/archive reference;
- split;
- tags;
- dataset version;
- expected trajectory when applicable.

## Experiment naming

```text
upgradepilot-v1-<suite>-<app_version>-<prompt_version>-<YYYYMMDD-HHMM>
```

## Baselines

- Mark the first passing release candidate as baseline.
- Compare prompt/model/rule changes against baseline.
- Fail CI on hard-metric regression.
- Track semantic changes but require human review before treating them as release blockers.

## Output

Every run writes:

```text
eval_results/
├── latest.json
├── latest.md
├── junit.xml
├── cases/
└── comparisons/
```

When using LangSmith, include experiment URL/ID in local output without placing credentials in files.

## CI behavior

Pull requests:

- unit tests;
- smoke fixture eval;
- changed-pack detection eval.

Main/release:

- full fixture eval;
- LangSmith regression experiment when secrets are available;
- baseline comparison;
- publish `EVAL_RESULTS.md` artifact;
- block release on hard-gate failure.
