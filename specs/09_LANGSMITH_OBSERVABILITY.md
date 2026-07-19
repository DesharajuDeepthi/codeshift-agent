# 09 — LangSmith Observability

## Requirement

LangSmith Cloud is the primary observability and evaluation platform for the agentic workflow. Integration is mandatory for development, staging, evaluation, and production-like demos.

Prometheus and Grafana provide local service-level metrics. Structured JSON logs provide operational diagnostics.

## Environment variables

Provide `.env.example` entries:

```text
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=upgradepilot-dev
LANGSMITH_ENDPOINT=
UPGRADEPILOT_ENV=dev
UPGRADEPILOT_VERSION=
LANGSMITH_HIDE_INPUTS=false
LANGSMITH_HIDE_OUTPUTS=false
```

Do not commit keys.

## Project naming

- `upgradepilot-dev`
- `upgradepilot-test`
- `upgradepilot-eval`
- `upgradepilot-prod`

## Trace hierarchy

Root:

```text
upgradepilot.analysis
```

Required child categories:

- `node.*`
- `agent.*`
- `tool.*`
- `llm.*`
- `validator.*`
- `report.*`

## Required trace metadata

- analysis ID;
- request ID;
- repository owner/name;
- requested ref;
- resolved commit SHA;
- migration pack ID/version;
- application version and git SHA;
- environment;
- analysis mode;
- model/provider;
- prompt versions;
- detector/scoring versions;
- report status;
- repair count;
- cache hit/miss indicators.

## Required tags

Examples:

```text
env:dev
pack:pydantic-v1-to-v2
status:validated
mode:standard
repair:false
source:live-github
```

## Captured measurements

- graph duration;
- node/agent/tool latency;
- LLM input/output tokens;
- estimated cost;
- retry counts;
- cache hits;
- finding count;
- evidence count;
- validation failures;
- unsupported-claim count;
- risk level;
- final status;
- partial-degradation reasons.

## Privacy and masking

Before sending traces:

- redact API keys, tokens, credentials, cookies, and authorization headers;
- do not send full repository archives;
- do not send complete large files;
- send only bounded findings/snippets needed for debugging;
- mask likely secrets found in source excerpts;
- allow inputs/outputs to be hidden by environment configuration;
- record hashes and artifact IDs instead of sensitive content.

## Trace sampling

- Development/evaluation: 100%
- Portfolio demo: 100%
- Future production: configurable sampling, with 100% for errors and validation failures

## Feedback

Allow UI feedback:

- useful/not useful;
- finding correct/incorrect;
- plan actionable/not actionable;
- free-text comment.

Attach feedback to the root LangSmith run.

## Dashboards and monitoring

Create LangSmith views/monitors for:

- validation-pass rate;
- unsupported-claim rate;
- p50/p95 latency;
- average tokens/cost;
- partial-report rate;
- agent/tool error rate;
- repair-trigger and repair-success rate;
- finding volume and risk distribution.

## Online evaluators

For demo/production-like traces, define sampled evaluators for:

- report schema validity;
- evidence coverage;
- prohibited-claim detection;
- report completeness;
- semantic groundedness.

Deterministic evaluators remain authoritative where possible.

## Failure behavior

If LangSmith cannot be reached:

- analysis continues;
- emit structured warning `OBSERVABILITY_DEGRADED`;
- do not expose the API key;
- record local trace correlation data;
- make the missing trace visible in the report metadata;
- retry only in the background SDK/batching behavior, not with an unbounded application loop.

## Local operational metrics

Expose Prometheus metrics:

- HTTP request count/latency/status;
- active analyses;
- graph/node duration;
- analysis status;
- external API error count;
- cache hit rate;
- LLM call count/token totals;
- validation issue count.

Grafana ships with a starter dashboard.

## Structured logs

Every log includes:

- timestamp;
- severity;
- service;
- event;
- request ID;
- analysis ID;
- trace ID/run ID when available;
- repository and commit SHA when available;
- node/agent/tool;
- error code;
- duration.

Never log complete prompts, complete model outputs, archives, or secrets.
