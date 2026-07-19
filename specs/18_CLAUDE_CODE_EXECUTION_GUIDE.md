# 18 — Claude Code Execution Guide

## How to give this project to Claude Code

Place the entire specification pack in the repository before asking Claude Code to implement anything.

Do not paste all implementation requirements into one chat. Use milestone prompts.

## Initial prompt

```text
Read 00_START_HERE.md, CLAUDE.md, and every numbered file in specs/ in the required order.

Do not write implementation code yet.

Produce:
1. a concise architecture summary;
2. a list of assumptions and specification conflicts;
3. the proposed repository tree;
4. the Milestone 0 implementation plan;
5. the exact acceptance checks for Milestone 0.

Respect the V1 scope. LangGraph, LangSmith, Docker Compose, PostgreSQL checkpointing, Redis, Prometheus/Grafana, and the evaluation harness are mandatory.
```

Review its response. Correct only genuine misunderstandings.

## Milestone prompt pattern

```text
Implement Milestone <N> from specs/15_IMPLEMENTATION_PLAN.md.

Before editing:
- read the relevant specs;
- inspect existing code;
- restate acceptance criteria.

During implementation:
- stay within V1 scope;
- add tests;
- preserve typed contracts;
- add LangSmith instrumentation where the milestone requires it;
- update documentation only when behavior changes.

After editing:
- run the required quality gates;
- report changed files;
- report passed/failed checks;
- identify remaining acceptance gaps;
- do not start the next milestone.
```

## Review prompt

```text
Audit Milestone <N> against its specification and acceptance criteria.

Look specifically for:
- hidden scope expansion;
- missing tests;
- unsafe repository handling;
- untyped boundaries;
- LLM use where deterministic logic should be used;
- missing LangSmith traces/metadata/redaction;
- unbounded retries or agent loops;
- unsupported claims;
- Docker or evaluation gaps.

Fix confirmed issues, rerun checks, and stop.
```

## Release-candidate prompt

```text
Perform the Version 1 Definition of Done audit using specs/16_DEFINITION_OF_DONE.md.

Do not rely on documentation claims. Verify implementation and run commands.
Produce a pass/fail matrix with evidence.
Fix only V1 blockers.
Run the full local evaluation and LangSmith regression experiment.
Update EVAL_RESULTS.md with real outputs.
Do not implement Version 2.
```

## Interaction rules

- One milestone at a time.
- Commit after a milestone passes.
- Use separate sessions when context becomes large.
- Let `CLAUDE.md` and specs remain the source of truth.
- Require evidence for “done.”
- Never accept a reduced test/evaluation target merely to make the build green.
