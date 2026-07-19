# ADR-0004 - Degrade Observability Without Failing Analysis

## Status

Accepted.

## Context

LangSmith is required for normal development observability but should not become business
truth or corrupt reports during an outage.

## Decision

Analysis continues when LangSmith submission fails. Reports include trace correlation
where available and a degraded-observability status otherwise.

## Consequences

- User-facing reports remain available during LangSmith failures.
- Local metrics and structured logs still include correlation IDs.
- Feedback attaches to the root run when a run ID is available and is otherwise accepted
  without trace attachment.
