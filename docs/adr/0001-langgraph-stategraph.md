# ADR-0001 - Use LangGraph StateGraph

## Status

Accepted.

## Context

UpgradePilot needs deterministic routing, parallel branches, bounded agent nodes, a single
repair path, streaming progress, and checkpoint support.

## Decision

Use LangGraph `StateGraph` with typed state. Nodes return partial updates and routing
functions decide terminal, partial, repair, and validated outcomes.

## Consequences

- Graph topology is explicit and testable.
- Parallel scanner branches can merge via reducers.
- Progress streaming can follow named node updates.
- Domain logic must stay outside graph nodes to keep nodes thin.
