# syntax=docker/dockerfile:1.7
# ────────────────────────────────────────────────
# Stage 1: dependency builder
# ────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir uv==0.11.29

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ────────────────────────────────────────────────
# Stage 2: minimal runtime image
# ────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

COPY src/ ./src/
COPY migration_packs/ ./migration_packs/

# Writable workspace for analysis artifacts (mounted as volume in Compose)
RUN mkdir -p /workspace && chown appuser:appgroup /workspace

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

CMD ["python", "-m", "uvicorn", "upgradepilot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
