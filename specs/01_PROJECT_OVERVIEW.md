# 01 — Project Overview

## Name

**UpgradePilot**

## Product statement

UpgradePilot is an agentic software-migration intelligence platform. V1 analyzes a public Python GitHub repository and generates a source-backed plan for migrating Pydantic v1 code to Pydantic v2.

## Problem

Framework migration documentation is generic, while the impact is repository-specific. Engineers currently combine dependency files, source usages, release guidance, tests, CI configuration, and rollback planning manually. Generic LLM answers often invent affected files, unsupported replacements, or test outcomes.

UpgradePilot combines deterministic source inspection with bounded AI reasoning and strict evidence validation.

## User

Software engineers, platform engineers, technical leads, and engineering managers planning a Python framework migration.

## Main workflow

1. User submits a public GitHub URL.
2. System resolves an immutable commit SHA.
3. System safely downloads and profiles the repository.
4. System confirms Pydantic v1 applicability.
5. Deterministic analyzers detect migration patterns.
6. Approved official Pydantic sources are retrieved or loaded from a curated cache.
7. Specialist agents interpret impact and create a phased plan.
8. Deterministic and semantic validators verify all claims.
9. The system returns Markdown and JSON reports with evidence.
10. LangSmith records the complete graph trajectory, agent behavior, latency, tokens, cost, feedback, and evaluation scores.

## Why this is agentic

The system has multiple goal-directed specialists coordinated through LangGraph. Agents use bounded tools and validated shared state. The graph makes decisions, runs independent work in parallel, handles partial failures, performs one evidence-driven repair, and terminates deterministically.

## V1 scope

- Public GitHub repositories
- Python repositories
- Pydantic v1 to v2
- `requirements.txt`
- PEP 621 and common Poetry `pyproject.toml`
- Detection of tests, CI workflows, Dockerfiles, and runtime declarations
- Read-only analysis
- Streamlit and FastAPI
- Docker Compose
- LangSmith observability and evaluations
- Prometheus/Grafana service metrics
- Local fixture and selected live-repository evaluations

## Out of scope

- Code edits or commits
- Running repository code or tests
- Pull requests
- Private repositories
- Arbitrary migration targets
- Other languages
- Vulnerability scanning
- Full package resolver
- Exact effort estimates
- Guarantees of successful migration
- Fine-tuning
- Multi-tenant authentication
