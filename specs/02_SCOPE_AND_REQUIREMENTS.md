# 02 — Scope and Requirements

## Functional requirements

### FR-01 Request

Accept:

```json
{
  "repository_url": "https://github.com/owner/repository",
  "ref": "main",
  "migration_pack": "pydantic-v1-to-v2",
  "analysis_mode": "standard"
}
```

### FR-02 Immutable snapshot

Resolve branch/tag/ref to a commit SHA. Reports and traces must identify that SHA.

### FR-03 Safe repository acquisition

Download a GitHub archive or use an approved read-only GitHub client. Enforce configurable limits:

- compressed archive size;
- extracted size;
- file count;
- path depth;
- single-file size;
- analysis duration;
- symlink and path-traversal protection.

### FR-04 Repository profile

Detect:

- Python file count and source roots;
- dependency manifests;
- Pydantic constraints and usage evidence;
- Python runtime declarations;
- tests and test framework;
- CI workflows;
- Dockerfiles and packaging metadata.

### FR-05 Applicability

Return one of:

- `SUPPORTED`
- `PROBABLE_NEEDS_REVIEW`
- `NOT_APPLICABLE`
- `UNSUPPORTED`
- `ERROR`

Do not assume Pydantic v1 from a package name alone when constraints are ambiguous.

### FR-06 Findings

Each static finding contains:

- stable rule ID;
- category;
- severity;
- file and line range;
- exact bounded snippet;
- detected symbol/pattern;
- recommended migration concept;
- documentation source ID;
- confidence;
- detector version.

### FR-07 Trusted documentation

Only use sources allowlisted in the migration pack. Store source URL, title, retrieval time, content hash, and normalized evidence sections.

### FR-08 Risk score

Calculate a deterministic score from versioned rules. The LLM may explain the score but cannot set or modify it.

### FR-09 Plan

Generate:

- executive summary;
- repository impact;
- ordered migration phases;
- file worklist;
- dependency changes;
- repository-specific test checklist;
- rollout and rollback checklist;
- assumptions, gaps, and human-review points.

### FR-10 Validation

Verify all:

- file references;
- line ranges;
- snippets;
- rule IDs;
- documentation IDs;
- package/version claims;
- migration recommendations;
- risk-score components;
- prohibited claims.

### FR-11 Single repair

A validation failure caused only by generated language can trigger one repair pass. Structural evidence failure cannot be repaired by an LLM.

### FR-12 Outputs

- Markdown report
- JSON report
- GitHub issue-body draft
- trace and experiment references when available

### FR-13 Partial degradation

A failed optional source or agent must produce a disclosed gap. “Unavailable” is different from “none found.”

## Non-functional requirements

### Reliability

- Bounded retries with jitter
- Per-call and per-node timeouts
- End-to-end standard-mode target: 90 seconds
- Idempotent nodes
- Typed errors
- No stack traces in UI

### Cost

- Maximum four normal LLM calls plus one repair
- Configurable model and token budgets
- Cost and tokens traced in LangSmith
- Deterministic fixture mode for tests

### Performance

- Parallelize independent analyses
- Cache immutable repository snapshots and official documents
- Never send the full repository to an LLM
- Limit code context to findings and bounded surrounding lines

### User experience

- Show stage progress
- Separate facts, interpretations, and recommendations
- Explain risk-score components
- Display evidence per finding
- Mark assumptions and missing evidence clearly
