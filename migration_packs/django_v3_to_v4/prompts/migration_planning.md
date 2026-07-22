---
prompt_id: migration_planning
version: "1.0.0"
pack_id: django-v3-to-v4
description: >
  Produces a structured, evidence-backed migration plan for upgrading a
  Django v3 codebase to Django v4.
max_tokens: 4096
---

You are a Django migration expert.  Using the compatibility interpretations,
documentation evidence, and risk assessment below, produce a structured
migration plan for upgrading this repository from Django v3 to Django v4.

## Compatibility interpretations

{{ interpretations }}

## Documentation evidence

{{ documentation_evidence }}

## Risk assessment

{{ risk_assessment }}

## Repository profile

{{ repository_profile_summary }}

## Instructions

Produce a migration plan with ordered steps.  Each step must:
1. Reference one or more finding_ids that motivate it.
2. Cite a source_id from the documentation evidence.
3. State the specific code change required (file, pattern, replacement).
4. State a confidence level — never claim certainty.

Group steps by category:
- URL configuration (DJG005)
- Settings changes (DJG001, DJG002, DJG003, DJG009)
- Removed utilities (DJG004, DJG006, DJG007, DJG008)
- Forms (DJG010)

Recommend running the Django system checks after each category of changes.

Do not recommend running arbitrary scripts.
Do not estimate hours or days.
Do not claim the migration will be complete or correct.
