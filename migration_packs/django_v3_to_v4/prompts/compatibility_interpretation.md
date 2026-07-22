---
prompt_id: compatibility_interpretation
version: "1.0.0"
pack_id: django-v3-to-v4
description: >
  Interprets Django v3 scan findings in the context of official documentation
  evidence and risk assessment to produce a structured compatibility analysis.
max_tokens: 3072
---

You are a Django migration expert.  Given the scan findings, documentation
evidence, and risk assessment below, produce a structured compatibility
interpretation for the Django v3 → v4 upgrade.

## Scan findings

{{ findings }}

## Documentation evidence

{{ documentation_evidence }}

## Risk assessment

{{ risk_assessment }}

## Repository profile

{{ repository_profile_summary }}

## Instructions

For each finding, state:
1. What Django v3 API or behaviour is being used
2. What changed in Django v4 (cite the source_id from documentation evidence)
3. What the developer needs to do (be specific; do not be vague)
4. The confidence level of your interpretation

Return a JSON object matching the CompatibilityInterpretationResult schema.
Each interpretation must cite at least one finding_id and one source_id.
Do not invent source_ids.  Do not claim certainty about runtime behaviour.
