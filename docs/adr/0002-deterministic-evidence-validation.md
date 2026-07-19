# ADR-0002 - Deterministic Evidence Validation Before Report Assembly

## Status

Accepted.

## Context

Generated migration plans can overstate certainty, alter references, or cite unavailable
evidence.

## Decision

Validate file references, line ranges, snippets, finding IDs, rule IDs, docs, package
claims, risk components, prohibited claims, and output length before producing a validated
report.

## Consequences

- Structural evidence failures are terminal or partial, not repairable by an LLM.
- Generated-language grounding failures may use one repair attempt.
- V1 can report partial output without fabricating unsupported evidence.
