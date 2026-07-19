# 03 — Agentic AI Framework

## Architecture principle

UpgradePilot is a bounded agentic workflow, not a free-form multi-agent conversation. LangGraph coordinates specialists, deterministic tools, validation gates, recovery, and termination.

## Agent contract

Every agent defines:

- goal;
- typed input/output;
- allowlisted tools;
- prohibited actions;
- timeout;
- LLM-call and token budget;
- required evidence;
- trace name, tags, and metadata;
- success, partial, retryable, and terminal outcomes.

## Agents

### A1 Documentation Research Agent

**Goal:** Select and normalize official Pydantic evidence relevant to detected migration rules.

**Allowed tools:**

- approved source fetcher;
- curated document cache;
- document section search;
- migration-rule catalog.

**Forbidden:**

- general web search;
- blogs/forums;
- new source domains;
- repository modification.

**Output:** `DocumentationResearchResult`

**Maximum calls:** 1

### A2 Compatibility Interpretation Agent

**Goal:** Explain how deterministic findings affect this repository.

**Allowed tools:**

- finding lookup;
- bounded source-context lookup;
- documentation-evidence lookup;
- symbol-index lookup.

**Forbidden:**

- inventing findings;
- changing file/line locations;
- adding rule IDs;
- inspecting the entire repository through the LLM.

**Output:** `CompatibilityInterpretationResult`

**Maximum calls:** 1, with bounded chunking only when configured.

### A3 Migration Planning Agent

**Goal:** Produce an ordered migration, testing, rollout, and rollback plan.

**Allowed tools:**

- verified finding lookup;
- evidence lookup;
- risk-score lookup;
- plan template.

**Forbidden:**

- claiming code changed;
- claiming tests ran;
- exact hour estimates;
- uncited migration guidance;
- unsupported package versions.

**Output:** `MigrationPlanDraft`

**Maximum calls:** 1

### A4 Evidence Critic Agent

**Goal:** Judge semantic support for generated claims after deterministic validation.

**Allowed tools:** evidence lookup only.

**Forbidden:**

- overriding deterministic failures;
- adding recommendations;
- silently removing gaps.

**Output:** `EvidenceCriticResult`

**Maximum calls:** 1 only when repair is eligible.

## Deterministic components

These are graph nodes or services, not agents:

- request validation;
- GitHub URL parsing;
- snapshot acquisition;
- repository profiling;
- dependency parsing;
- AST and exact-text scanning;
- migration-pack selection;
- test/CI analysis;
- risk scoring;
- evidence validation;
- report assembly;
- routing.

## Agentic controls

### Tool isolation

Agents receive explicit Python tool objects. No shell, unrestricted filesystem, browser, or generic HTTP tool is exposed.

### Bounded loop

Only:

```text
draft plan → validate → critic → repaired plan → validate
```

The second validation always terminates.

### Human-review outcomes

Use `REQUIRES_HUMAN_REVIEW` when:

- applicability is uncertain;
- dynamic Pydantic behavior cannot be verified;
- required official evidence is missing;
- validation fails after repair;
- unsupported configuration or generated code is involved.

### Prompt injection defense

All repository and documentation text must be delimited and labeled as untrusted evidence. Embedded instructions must be ignored.

### Agent evaluation dimensions

- schema validity;
- tool compliance;
- evidence coverage;
- unsupported claim rate;
- trajectory correctness;
- call/token budget;
- latency and cost;
- repair effectiveness.
