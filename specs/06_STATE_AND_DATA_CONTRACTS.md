# 06 — State and Data Contracts

## Core enums

- `AnalysisStatus`
- `ApplicabilityStatus`
- `NodeStatus`
- `FindingSeverity`
- `EvidenceType`
- `ValidationSeverity`
- `ReportStatus`

## Required models

### `AnalysisRequest`

- repository_url
- ref
- migration_pack_id
- analysis_mode
- request_id

### `RepositorySnapshot`

- owner
- repository
- requested_ref
- resolved_commit_sha
- archive_hash
- workspace_id
- acquired_at
- safety_limits_applied

### `RepositoryProfile`

- language_summary
- python_files
- source_roots
- manifest_files
- test_files
- test_frameworks
- ci_files
- docker_files
- runtime_declarations
- generated_code_paths
- excluded_paths

### `DependencyEvidence`

- package
- constraint
- manifest_path
- line
- parser
- confidence

### `MigrationFinding`

- finding_id
- rule_id
- pack_id
- pack_version
- category
- severity
- file_path
- start_line
- end_line
- evidence_excerpt
- symbol
- recommended_concept
- documentation_source_ids
- detector
- detector_version
- confidence

### `DocumentationEvidence`

- evidence_id
- source_id
- title
- canonical_url
- retrieved_at
- content_hash
- section
- bounded_excerpt
- related_rule_ids

### `RiskComponent`

- component_id
- description
- points
- supporting_finding_ids

### `RiskAssessment`

- total_score
- level
- components
- scoring_model_version

### `PlanClaim`

- claim_id
- text
- claim_type
- finding_ids
- documentation_evidence_ids
- repository_evidence_ids
- confidence

### `MigrationPlanDraft`

- executive_summary
- impact_summary
- phases
- file_worklist
- dependency_actions
- testing_checklist
- rollout_checklist
- rollback_checklist
- assumptions
- gaps
- claims

### `ValidationIssue`

- validator_id
- severity
- message
- claim_id
- evidence_id
- repairable

### `ValidatedReport`

- analysis metadata
- repository snapshot
- applicability
- findings
- risk
- plan
- validation summary
- limitations
- observability metadata
- exports

### `NodeExecutionRecord`

- node_name
- status
- started_at
- completed_at
- attempt
- latency_ms
- error_code
- warning_codes
- langsmith_run_id when available

## `UpgradePilotState`

The state should contain separate sections:

- request
- execution_context
- repository_snapshot
- repository_profile
- migration_pack
- dependencies
- findings
- documentation
- test_ci_profile
- risk
- interpretations
- plan_draft
- validation
- repair_count
- final_report
- errors
- warnings
- node_executions

## Contract rules

- All paths are normalized repository-relative POSIX paths.
- All timestamps are UTC.
- IDs are UUIDs or deterministic hashes where appropriate.
- Confidence is `[0.0, 1.0]`.
- Source excerpts are bounded.
- Validation fails closed for unsupported file/version/source claims.
