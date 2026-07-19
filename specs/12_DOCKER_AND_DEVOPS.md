# 12 — Docker and DevOps

## Requirement

The entire local application and operational stack must start with Docker Compose. LangSmith Cloud remains external and is configured by environment variables.

## Required services

```text
api          FastAPI + LangGraph
ui           Streamlit
postgres     LangGraph checkpoints and app metadata
redis        cache
prometheus   local metrics
grafana      dashboards
```

Optional development profile:

```text
mailhog or mock services are not required in V1
```

## Required files

- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `prometheus/prometheus.yml`
- `grafana/provisioning/`
- health checks
- startup scripts only when necessary

## Dockerfile

Use multi-stage build:

- dependency/build stage;
- minimal non-root runtime;
- pinned lockfile;
- no compilers in runtime when avoidable;
- health endpoint;
- read-only source image where practical;
- writable mounted analysis workspace only.

## Compose behavior

```bash
docker compose up --build
```

Must provide:

- UI on documented port;
- API docs and health endpoint;
- PostgreSQL health check;
- Redis health check;
- Prometheus target health;
- Grafana starter dashboard;
- persistent named volumes;
- isolated network;
- bounded resource guidance.

## Secrets

- `.env` is gitignored.
- `.env.example` contains names only.
- Compose reads LangSmith, GitHub, and model keys from environment.
- Never bake secrets into images.
- CI uses repository secrets.

## Health endpoints

- `/health/live`
- `/health/ready`
- `/metrics`

Readiness checks:

- application initialized;
- migration pack loaded;
- PostgreSQL reachable;
- degraded-but-ready status allowed for Redis/LangSmith with explicit details.

## Migrations/startup

Use explicit database initialization. Avoid destructive automatic schema changes.

## CI pipeline

Stages:

1. format/lint/type check;
2. unit tests;
3. build container;
4. smoke evaluation;
5. integration test with Compose services;
6. full evaluation on main/release;
7. security scan;
8. publish evaluation and container artifacts.

## Suggested security checks

- dependency audit;
- container image scan;
- secret scan;
- SBOM generation.

## Deployment boundary

V1 portfolio deployment can run on any container platform. LangSmith tracing/evaluation uses the configured Cloud workspace. Do not require LangSmith Deployment for V1.
