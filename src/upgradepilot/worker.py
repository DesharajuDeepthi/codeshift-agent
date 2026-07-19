"""
Analysis worker — claims jobs from the Redis queue and runs them.

Flow per job:
  1. claim_next_job()  →  AnalysisJob
  2. Resolve previous findings via get_previous_findings(thread_id)
  3. Invoke the LangGraph with the job's thread_id as checkpointer key
  4. compute_delta(previous, current) → DeltaReport
  5. Persist analysis row + delta to Postgres
  6. complete_job() or fail_job() on the Redis envelope

The core graph (src/upgradepilot/graph/) is never modified here — the
worker composes around it exactly as the V2 spec requires.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from upgradepilot.delta.detector import compute_delta
from upgradepilot.graph.build import build_graph
from upgradepilot.graph.checkpointer import get_checkpointer
from upgradepilot.graph.state import make_initial_state
from upgradepilot.memory.store import get_previous_findings
from upgradepilot.observability.metrics import (
    record_job_completed,
    record_job_failed,
    record_job_retried,
)
from upgradepilot.queue.jobs import AnalysisJob, RedisClient, claim_next_job, complete_job, fail_job

log = logging.getLogger(__name__)

_POLL_INTERVAL_S = 2
_ANALYSIS_MODE_KEY = "analysis_mode"

_INSERT_ANALYSIS = sa.text(
    """
    INSERT INTO analyses
        (analysis_id, user_id, thread_id, repository_url, ref,
         commit_sha, status, finding_count, report, delta, created_at, completed_at)
    VALUES
        (:analysis_id, :user_id, :thread_id, :repository_url, :ref,
         :commit_sha, :status, :finding_count, :report, :delta,
         now(), now())
    ON CONFLICT (analysis_id) DO UPDATE SET
        status        = EXCLUDED.status,
        finding_count = EXCLUDED.finding_count,
        report        = EXCLUDED.report,
        delta         = EXCLUDED.delta,
        completed_at  = now()
    """
)


def _run_analysis(job: AnalysisJob, checkpointer: Any) -> dict[str, Any]:  # noqa: ANN401
    """Invoke the LangGraph and return the final state dict."""
    graph = build_graph(checkpointer=checkpointer)
    state = make_initial_state(
        analysis_id=str(job.analysis_id),
        request_data={
            "repository_url": job.repository_url,
            "ref": job.ref,
            "migration_pack": job.migration_pack,
            "analysis_mode": job.analysis_mode,
        },
    )
    config = {"configurable": {"thread_id": job.thread_id}}
    result: dict[str, Any] = graph.invoke(state, config=config)  # type: ignore[attr-defined]
    return result


def _persist(conn: Connection, job: AnalysisJob, result: dict[str, Any], delta_json: Any) -> None:  # noqa: ANN401
    report = result.get("final_report") or {}
    findings = result.get("findings") or []
    conn.execute(
        _INSERT_ANALYSIS,
        {
            "analysis_id": str(job.analysis_id),
            "user_id": str(job.user_id),
            "thread_id": job.thread_id,
            "repository_url": job.repository_url,
            "ref": job.ref,
            "commit_sha": report.get("commit_sha"),
            "status": result.get("status", "completed"),
            "finding_count": len(findings),
            "report": sa.cast(report, sa.JSON) if report else None,
            "delta": sa.cast(delta_json, sa.JSON) if delta_json else None,
        },
    )
    conn.commit()


def process_one(redis: RedisClient, conn: Connection) -> bool:
    """
    Claim and process one job.

    Returns True if a job was processed, False if the queue was empty.
    """
    job = claim_next_job(redis)
    if job is None:
        return False

    log.info("claimed job %s for user %s", job.job_id, job.user_id)

    try:
        previous_findings = get_previous_findings(job.thread_id, conn)

        database_url = os.environ.get("DATABASE_URL", "")
        checkpointer = get_checkpointer(postgres_url=database_url or None)

        result = _run_analysis(job, checkpointer)

        current_findings: list[dict[str, Any]] = result.get("findings") or []
        delta = compute_delta(previous_findings, current_findings)
        delta_json = {
            "fixed": delta.fixed,
            "new": delta.new,
            "still_open": delta.still_open,
            "summary": delta.summary,
        }

        _persist(conn, job, result, delta_json)
        complete_job(redis, job.job_id)
        record_job_completed(fixed=len(delta.fixed), new=len(delta.new))
        log.info("completed job %s — %s", job.job_id, delta.summary)

    except Exception as exc:  # noqa: BLE001
        error_code = type(exc).__name__
        retried = fail_job(redis, job, error_code=error_code)
        if retried:
            record_job_retried()
        else:
            record_job_failed(error_code=error_code)
        log.warning("job %s failed (%s) retry=%s", job.job_id, error_code, retried)

    return True


def run_worker(redis: RedisClient, conn: Connection, *, max_jobs: int | None = None) -> None:
    """
    Poll the queue and process jobs until stopped.

    max_jobs: if set, stop after processing this many jobs (useful in tests).
    """
    processed = 0
    log.info("worker started")
    while True:
        did_work = process_one(redis, conn)
        if did_work:
            processed += 1
            if max_jobs is not None and processed >= max_jobs:
                break
        else:
            time.sleep(_POLL_INTERVAL_S)
