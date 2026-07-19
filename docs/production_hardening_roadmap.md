# Production Hardening Roadmap

These are not V1 claims. They are the next hardening steps before any production service.

1. Replace process-local analysis storage with durable PostgreSQL analysis records.
2. Add authenticated API access, tenant isolation, request quotas, and abuse controls.
3. Use managed secrets and remove local `.env` use outside development.
4. Add external dependency and container scanners in CI, such as pip-audit, Trivy, Grype, or Docker Scout.
5. Pin base images by digest and define an image rebuild cadence.
6. Add artifact retention and workspace cleanup jobs with operational alerts.
7. Add private repository support only with least-privilege read tokens and explicit user consent.
8. Add more migration packs behind ADRs and pack-level evaluations.
9. Expand durable LangGraph checkpoint resume coverage to include multi-process interruption
   scenarios in CI.
10. Add browser-based UI tests and accessibility checks.
