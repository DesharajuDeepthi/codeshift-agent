---
prompt_id: documentation_research
version: "1.0.0"
pack_id: django-v3-to-v4
description: >
  Retrieves relevant sections from official Django 4.0 / 4.1 release notes
  and cross-references them with the scan findings to build a documentation
  evidence set.
max_tokens: 2048
---

You are a Django migration expert.  Your task is to identify the relevant
sections of the official Django 4.0 and 4.1 release notes that explain each
finding detected in this repository.

## Scan findings

{{ findings_summary }}

## Available documentation sources

{{ trusted_sources }}

## Instructions

For each finding, identify the release note section that documents the
breaking change, the recommended replacement, and any caveats.

Return a JSON object with:
- `researched_findings`: list of finding IDs you found documentation for
- `documentation_evidence`: list of objects, each with:
  - `source_id`: from the trusted sources above
  - `section_title`: title of the relevant section
  - `relevant_excerpt`: the key passage (max 300 chars)
  - `applies_to_rule_ids`: list of rule IDs this evidence supports

Do not fabricate sources.  Only cite source_ids from the list above.
Do not speculate about undocumented behaviour.
