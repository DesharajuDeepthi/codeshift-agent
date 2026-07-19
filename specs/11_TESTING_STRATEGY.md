# 11 — Testing Strategy

## Test layers

### Unit tests

Test:

- URL validation;
- archive safety;
- manifest parsing;
- AST matchers;
- exclusion rules;
- risk scoring;
- state reducers;
- evidence validators;
- report renderers;
- redaction;
- cache behavior.

### Contract tests

For every agent and tool:

- valid schema;
- malformed response;
- timeout;
- retryable failure;
- terminal failure;
- budget enforcement;
- LangSmith metadata attachment.

### Integration tests

- GitHub client with mocked HTTP;
- document service with cached fixtures;
- PostgreSQL checkpointer;
- Redis cache;
- graph branch behavior;
- API and Streamlit service interaction.

### End-to-end tests

Run the graph on local repository fixtures using a fake LLM and deterministic responses.

### Live smoke tests

Opt-in tests against one or two pinned public repositories and approved documentation sources.

### Security tests

- path traversal archives;
- zip bombs/size limits;
- symlinks;
- prompt injection text;
- secret redaction;
- malicious filenames;
- malformed Python;
- oversized files;
- authorization headers absent from logs/traces.

## Test design requirements

- Tests must not depend on execution order.
- Network tests are marked.
- Fixture tests require no API keys.
- Time and UUID dependencies are injectable.
- Golden reports are normalized to avoid volatile IDs/timestamps.
- Every migration rule has positive and negative fixtures.
- Every conditional graph edge has a test.
- Every error code has a test.

## Coverage

Coverage percentage is secondary to critical-path coverage. Required critical paths:

- supported analysis;
- not applicable;
- unsafe repository;
- LLM failure partial report;
- validation repair success;
- validation repair failure;
- LangSmith unavailable;
- Redis unavailable;
- PostgreSQL persistence/resume.

## Tooling

- pytest
- pytest-asyncio
- pytest-httpx or respx
- Hypothesis where useful for parsers/path safety
- coverage.py
- mypy
- Ruff
