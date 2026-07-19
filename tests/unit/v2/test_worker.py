"""Unit tests for the analysis worker."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import fakeredis

from upgradepilot.memory.thread import make_thread_id
from upgradepilot.queue.jobs import AnalysisJob, enqueue, get_job_state
from upgradepilot.worker import process_one

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _job(
    user_id: uuid.UUID | None = None,
    repo: str = "https://github.com/acme/repo",
) -> AnalysisJob:
    uid = user_id or uuid.uuid4()
    return AnalysisJob(
        job_id=uuid.uuid4(),
        user_id=uid,
        analysis_id=uuid.uuid4(),
        repository_url=repo,
        ref="main",
        migration_pack="pydantic-v2",
        analysis_mode="STANDARD",
        thread_id=make_thread_id(uid, repo),
    )


def _mock_conn(previous_findings: list[dict[str, Any]] | None = None) -> MagicMock:
    """DB connection mock: returns previous findings and accepts persist calls."""
    conn = MagicMock()
    result = MagicMock()
    # get_previous_findings returns a row with a report dict, or None
    if previous_findings is not None:
        result.fetchone.return_value = ({"findings": previous_findings},)
    else:
        result.fetchone.return_value = None
    conn.execute.return_value = result
    conn.commit = MagicMock()
    return conn


def _graph_result(findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "status": "completed",
        "findings": findings or [],
        "final_report": {"summary": "ok"},
    }


# ---------------------------------------------------------------------------
# process_one — happy path
# ---------------------------------------------------------------------------


def test_process_one_empty_queue_returns_false():
    r = _redis()
    conn = _mock_conn()
    assert process_one(r, conn) is False


def test_process_one_returns_true_when_job_claimed():
    r = _redis()
    job = _job()
    enqueue(r, job)
    conn = _mock_conn()

    with patch("upgradepilot.worker._run_analysis", return_value=_graph_result()):
        result = process_one(r, conn)

    assert result is True


def test_process_one_marks_job_completed():
    r = _redis()
    job = _job()
    enqueue(r, job)
    conn = _mock_conn()

    with patch("upgradepilot.worker._run_analysis", return_value=_graph_result()):
        process_one(r, conn)

    assert get_job_state(r, job.job_id)["state"] == "completed"


def test_process_one_persists_analysis():
    r = _redis()
    job = _job()
    enqueue(r, job)
    conn = _mock_conn()

    with patch("upgradepilot.worker._run_analysis", return_value=_graph_result()):
        process_one(r, conn)

    # _persist calls conn.execute + conn.commit
    assert conn.execute.called
    assert conn.commit.called


# ---------------------------------------------------------------------------
# Delta wiring
# ---------------------------------------------------------------------------


def _finding(rule_id: str, line: int = 1) -> dict[str, Any]:
    return {"rule_id": rule_id, "location": {"file_path": "app.py", "start_line": line}}


def test_delta_fixed_findings_detected():
    r = _redis()
    job = _job()
    enqueue(r, job)

    previous = [_finding("PYD001", 10), _finding("PYD003", 20)]
    current = [_finding("PYD003", 20)]  # PYD001 fixed

    conn = _mock_conn(previous_findings=previous)

    captured: dict[str, Any] = {}

    def _fake_persist(conn: Any, job: Any, result: Any, delta_json: Any) -> None:  # noqa: ANN401
        captured["delta"] = delta_json

    with (
        patch("upgradepilot.worker._run_analysis", return_value=_graph_result(current)),
        patch("upgradepilot.worker._persist", side_effect=_fake_persist),
    ):
        process_one(r, conn)

    assert len(captured["delta"]["fixed"]) == 1
    assert captured["delta"]["fixed"][0]["rule_id"] == "PYD001"
    assert len(captured["delta"]["still_open"]) == 1
    assert captured["delta"]["new"] == []


def test_delta_new_regression_detected():
    r = _redis()
    job = _job()
    enqueue(r, job)

    previous: list[dict[str, Any]] = []
    current = [_finding("PYD001", 10)]

    conn = _mock_conn(previous_findings=previous)
    captured: dict[str, Any] = {}

    def _fake_persist(conn: Any, job: Any, result: Any, delta_json: Any) -> None:  # noqa: ANN401
        captured["delta"] = delta_json

    with (
        patch("upgradepilot.worker._run_analysis", return_value=_graph_result(current)),
        patch("upgradepilot.worker._persist", side_effect=_fake_persist),
    ):
        process_one(r, conn)

    assert len(captured["delta"]["new"]) == 1
    assert captured["delta"]["fixed"] == []


# ---------------------------------------------------------------------------
# Failure / retry
# ---------------------------------------------------------------------------


def test_process_one_marks_job_retried_on_transient_error():
    r = _redis()
    job = _job()
    enqueue(r, job)
    conn = _mock_conn()

    with patch("upgradepilot.worker._run_analysis", side_effect=RuntimeError("timeout")):
        process_one(r, conn)

    # First failure → re-queued (state = queued again)
    state = get_job_state(r, job.job_id)
    assert state["state"] == "queued"
    assert state["error_code"] == "RuntimeError"


def test_process_one_marks_job_failed_after_max_attempts():
    r = _redis()
    job = _job()
    enqueue(r, job)
    conn = _mock_conn()

    with patch("upgradepilot.worker._run_analysis", side_effect=RuntimeError("crash")):
        process_one(r, conn)  # attempt 1 → requeue
        process_one(r, conn)  # attempt 2 → failed

    assert get_job_state(r, job.job_id)["state"] == "failed"
