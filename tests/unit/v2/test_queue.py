"""Unit tests for the Redis work queue."""

from __future__ import annotations

import uuid

import fakeredis

from upgradepilot.memory.thread import make_thread_id
from upgradepilot.queue.jobs import (
    AnalysisJob,
    claim_next_job,
    complete_job,
    enqueue,
    fail_job,
    get_job_state,
)


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


# ---------------------------------------------------------------------------
# enqueue / claim basics
# ---------------------------------------------------------------------------


def test_enqueue_then_claim():
    r = _redis()
    job = _job()
    enqueue(r, job)
    claimed = claim_next_job(r)
    assert claimed is not None
    assert claimed.job_id == job.job_id


def test_empty_queue_returns_none():
    r = _redis()
    assert claim_next_job(r) is None


def test_claimed_job_state_is_running():
    r = _redis()
    job = _job()
    enqueue(r, job)
    claim_next_job(r)
    state = get_job_state(r, job.job_id)
    assert state["state"] == "running"


def test_enqueued_job_state_is_queued():
    r = _redis()
    job = _job()
    enqueue(r, job)
    state = get_job_state(r, job.job_id)
    assert state["state"] == "queued"


# ---------------------------------------------------------------------------
# complete / fail
# ---------------------------------------------------------------------------


def test_complete_job():
    r = _redis()
    job = _job()
    enqueue(r, job)
    claim_next_job(r)
    complete_job(r, job.job_id)
    assert get_job_state(r, job.job_id)["state"] == "completed"


def test_fail_job_first_attempt_requeues():
    r = _redis()
    job = _job()
    enqueue(r, job)
    claim_next_job(r)
    retried = fail_job(r, job, error_code="TRANSIENT")
    assert retried is True
    # Job must be claimable again
    retry = claim_next_job(r)
    assert retry is not None
    assert retry.job_id == job.job_id


def test_fail_job_second_attempt_marks_failed():
    r = _redis()
    job = _job()
    enqueue(r, job)
    claim_next_job(r)
    fail_job(r, job, error_code="TRANSIENT")  # attempt 1 → requeue
    claim_next_job(r)  # attempt 2
    retried = fail_job(r, job, error_code="TERMINAL")
    assert retried is False
    assert get_job_state(r, job.job_id)["state"] == "failed"


# ---------------------------------------------------------------------------
# Round-robin fairness
# ---------------------------------------------------------------------------


def test_round_robin_alternates_between_users():
    r = _redis()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    job_a1 = _job(user_a)
    job_a2 = _job(user_a)
    job_b1 = _job(user_b)

    enqueue(r, job_a1)
    enqueue(r, job_a2)
    enqueue(r, job_b1)

    claimed_ids = []
    for _ in range(3):
        j = claim_next_job(r)
        if j:
            claimed_ids.append(j.job_id)

    # Both users must have been served
    user_ids_served = {
        job_a1.user_id
        if j == job_a1.job_id
        else job_a2.user_id
        if j == job_a2.job_id
        else job_b1.user_id
        for j in claimed_ids
    }
    assert user_a in user_ids_served
    assert user_b in user_ids_served


def test_single_user_drains_fully():
    r = _redis()
    uid = uuid.uuid4()
    jobs = [_job(uid) for _ in range(3)]
    for j in jobs:
        enqueue(r, j)

    claimed = []
    while (j := claim_next_job(r)) is not None:
        claimed.append(j.job_id)
        complete_job(r, j.job_id)

    assert len(claimed) == 3
    assert claim_next_job(r) is None
