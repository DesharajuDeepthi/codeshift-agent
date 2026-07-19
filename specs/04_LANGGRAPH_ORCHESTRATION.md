# 04 — LangGraph Orchestration

## Required graph

Use `StateGraph[UpgradePilotState]`.

```text
START
  |
validate_request
  |
acquire_repository
  |
profile_repository
  |
select_migration_pack
  |
  +---- unsupported/not-applicable ---> assemble_terminal_report ---> END
  |
fan_out_analysis
  |  | +--> parse_dependencies
  | +--> scan_compatibility
  | +--> analyze_tests_and_ci
  | +--> documentation_research_agent
  |/
aggregate_analysis
  |
calculate_risk
  |
compatibility_interpretation_agent
  |
migration_planning_agent
  |
deterministic_evidence_validator
  |
  +---- pass --------------------------> assemble_validated_report --> END
  |
  +---- structural failure ------------> assemble_partial_report ----> END
  |
  +---- repairable and repair_count=0 --> evidence_critic_agent
                                           |
                                      repair_plan_node
                                           |
                                 deterministic_evidence_validator
                                           |
                                +----------+-----------+
                                |                      |
                               pass                   fail
                                |                      |
                    assemble_validated_report  assemble_partial_report
                                |                      |
                               END                    END
```

## Parallelism

After pack selection, run independent branches concurrently:

- dependency parsing;
- code scanning;
- test/CI analysis;
- documentation research.

Use explicit reducers for merged lists. Do not rely on mutation of shared objects.

## State rules

- Store typed facts and artifact references.
- Do not use chat history as the main state.
- Do not store full repository files in state or checkpoints.
- Nodes return only their owned partial state.
- Every node writes `NodeExecutionRecord`.
- Large artifacts live in an analysis workspace with retention limits.

## Persistence

Use `AsyncPostgresSaver` or the current supported PostgreSQL checkpointer.

- `thread_id = analysis_id`
- checkpoint after every graph super-step;
- support retry/resume after process interruption;
- purge by retention policy;
- no secrets or complete source files in checkpoints.

## Streaming

Expose graph progress to Streamlit/FastAPI using named events:

- repository acquired;
- repository profiled;
- findings detected;
- documentation ready;
- plan generated;
- validation completed;
- report assembled.

## LangSmith trace structure

Root run:

```text
upgradepilot.analysis
```

Child runs use stable names:

```text
node.validate_request
tool.github.resolve_ref
tool.github.download_archive
node.profile_repository
agent.documentation_research
tool.ast.scan
node.calculate_risk
agent.compatibility_interpretation
agent.migration_planning
node.evidence_validation
agent.evidence_critic
node.report_assembly
```

## Routing

- inaccessible/private repository → terminal error;
- extraction violation → safety-blocked report;
- non-Python → unsupported;
- Pydantic v2 only/no Pydantic → not applicable;
- probable v1 → continue with review flag;
- first repairable validation failure → one repair;
- second failure → partial report.

## Idempotency

Each node must produce the same output for the same immutable inputs, model/prompt version, and configuration where deterministic. Generated nodes record model and prompt version to make differences explainable.
