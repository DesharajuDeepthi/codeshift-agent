# ADR-0005 - Keep V1 Read-Only

## Status

Accepted.

## Context

Automated repository modification would require stronger permissions, execution safety,
review workflows, and rollback guarantees.

## Decision

V1 analyzes public repositories and produces advisory reports only. It does not push
branches, open pull requests, execute tests, or modify analyzed code.

## Consequences

- GitHub access is public read-only in V1.
- Reports must distinguish facts, interpretations, and recommendations.
- Any future write capability requires a new ADR and Version 2 scope.
