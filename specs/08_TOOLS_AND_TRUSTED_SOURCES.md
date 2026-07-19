# 08 — Tools and Trusted Sources

## Tool philosophy

Agents do not receive broad access. Each tool is typed, bounded, observable, and read-only.

## Required tools/services

### GitHub URL parser

- validates host and owner/repository form;
- rejects unsupported URLs;
- removes credentials and unsafe components.

### GitHub metadata client

- resolves refs to commit SHA;
- retrieves basic repository metadata;
- uses unauthenticated access when possible;
- supports optional read-only token;
- handles rate limits and retries.

### Safe archive downloader/extractor

- HTTPS only;
- size limits;
- archive hash;
- path-traversal prevention;
- symlink restrictions;
- file-count and extracted-size limits.

### Repository file index

- indexed file metadata;
- bounded line reads;
- exact snippet verification;
- symbol and import index;
- no writes.

### Manifest parsers

- `requirements.txt`;
- PEP 621 `pyproject.toml`;
- common Poetry dependency sections;
- typed parse errors.

### Python scanner

- AST parsing;
- syntax-error capture;
- migration-pack rules;
- exact locations;
- no execution.

### Test/CI detector

Detect:

- pytest/unittest configuration;
- test files;
- GitHub Actions workflows;
- tox/nox;
- lint/type-check commands where statically visible.

It reports detected commands but does not run them.

### Trusted-document service

- allowlisted domains and URLs;
- normalized source snapshots;
- content hashes;
- bounded excerpts;
- cache;
- refresh command;
- no arbitrary web search in V1.

### LLM client

- provider-neutral;
- structured output;
- timeouts/retries;
- token and cost capture;
- LangSmith trace integration;
- test fake implementation.

### Evidence lookup tools

Agents may query only evidence already collected and normalized.

## Trust hierarchy

1. Repository snapshot at resolved SHA
2. Official Pydantic migration documentation
3. Official Pydantic API documentation
4. Official Pydantic release notes/changelog
5. Curated migration-pack rules derived from official sources

No blogs, Q&A forums, or arbitrary search results in V1.

## Source retention

Store:

- canonical URL;
- title;
- retrieved time;
- content hash;
- normalized text artifact ID;
- pack version;
- source status.

## Rate-limit behavior

- Cache immutable GitHub responses by commit SHA.
- Respect GitHub rate-limit headers.
- Never turn rate-limit failure into “repository not found.”
- Disclose when live refresh is unavailable and a curated snapshot is used.
