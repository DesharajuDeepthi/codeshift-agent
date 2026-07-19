# ADR-0003 - Use Trusted Official Documentation Only

## Status

Accepted.

## Context

Migration guidance should not come from arbitrary web pages, repository text, blogs, or
forums.

## Decision

The documentation research agent can use only the migration pack source catalog,
approved official-source fetcher, curated cache, section search, and rule catalog.

## Consequences

- The agent cannot browse the open web.
- Source IDs and rule IDs must come from the pack.
- Cached fallback makes local fixture tests deterministic.
