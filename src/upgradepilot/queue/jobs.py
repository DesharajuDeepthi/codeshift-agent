"""
Redis-backed job queue with per-user fairness.

Design:
  - Each user gets their own list: queue:user:{user_id}
  - A global round-robin index (queue:rr_index) cycles through active users
    so no single user can starve others.
  - Workers call claim_next_job() which finds the next non-empty user queue
    and atomically pops one job (LPOP).
  - One retry on transient failure; terminal failure sets state = "failed".

Job lifecycle:  queued → running → completed | failed
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class RedisClient(Protocol):
    """Structural type accepted by queue functions — satisfied by both
    redis.Redis and fakeredis.FakeRedis without an explicit import."""

    def pipeline(self) -> Any: ...  # noqa: ANN401
    def rpush(self, name: str, *values: str) -> Any: ...  # noqa: ANN401
    def lpush(self, name: str, *values: str) -> Any: ...  # noqa: ANN401
    def lpop(self, name: str) -> str | None: ...
    def llen(self, name: str) -> int: ...
    def zadd(self, name: str, mapping: dict[str, Any], **kwargs: Any) -> Any: ...  # noqa: ANN401
    def zrange(self, name: str, start: int, end: int) -> list[str]: ...
    def zrem(self, name: str, *values: str) -> Any: ...  # noqa: ANN401
    def zincrby(self, name: str, amount: float, value: str) -> Any: ...  # noqa: ANN401
    def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> Any: ...  # noqa: ANN401
    def hget(self, name: str, key: str) -> str | None: ...
    def hgetall(self, name: str) -> dict[str, str]: ...


# Redis key namespaces
_USER_QUEUE_KEY = "queue:user:{user_id}"
_ACTIVE_USERS_KEY = "queue:active_users"  # sorted set, score = enqueue time
_JOB_KEY = "queue:job:{job_id}"
_MAX_ATTEMPTS = 2


class AnalysisJob(BaseModel):
    job_id: uuid.UUID
    user_id: uuid.UUID
    analysis_id: uuid.UUID
    repository_url: str
    ref: str
    migration_pack: str
    analysis_mode: str
    thread_id: str
    extra: dict[str, Any] = {}


def enqueue(redis: RedisClient, job: AnalysisJob) -> None:
    """Push a job onto the user's queue and register the user as active."""
    user_key = _USER_QUEUE_KEY.format(user_id=job.user_id)
    job_key = _JOB_KEY.format(job_id=job.job_id)
    payload = job.model_dump_json()

    pipe = redis.pipeline()
    pipe.rpush(user_key, payload)
    # sorted set: score = 0 so ordering is stable FIFO across users
    pipe.zadd(_ACTIVE_USERS_KEY, {str(job.user_id): 0}, nx=True)
    pipe.hset(job_key, mapping={"state": "queued", "attempts": 0})
    pipe.execute()


def claim_next_job(redis: RedisClient) -> AnalysisJob | None:
    """
    Round-robin across active users and pop the next job.

    Returns None if all queues are empty.
    """
    active_users: list[str] = redis.zrange(_ACTIVE_USERS_KEY, 0, -1)
    if not active_users:
        return None

    for user_id_str in active_users:
        user_key = _USER_QUEUE_KEY.format(user_id=user_id_str)
        raw = redis.lpop(user_key)
        if raw is None:
            # Queue drained — remove user from active set
            redis.zrem(_ACTIVE_USERS_KEY, user_id_str)
            continue

        job = AnalysisJob.model_validate_json(raw)
        job_key = _JOB_KEY.format(job_id=job.job_id)
        attempts = int(redis.hget(job_key, "attempts") or 0) + 1
        redis.hset(job_key, mapping={"state": "running", "attempts": attempts})

        # Re-enqueue user at back of round-robin (bump score to current position)
        remaining = redis.llen(user_key)
        if remaining == 0:
            redis.zrem(_ACTIVE_USERS_KEY, user_id_str)
        else:
            # Give this user lower priority until others are served
            redis.zincrby(_ACTIVE_USERS_KEY, 1, user_id_str)

        return job

    return None


def complete_job(redis: RedisClient, job_id: uuid.UUID) -> None:
    """Mark a job as completed."""
    job_key = _JOB_KEY.format(job_id=job_id)
    redis.hset(job_key, "state", "completed")


def fail_job(redis: RedisClient, job: AnalysisJob, error_code: str) -> bool:
    """
    Record a failure. If attempts < MAX_ATTEMPTS, re-enqueue for retry
    and return True. Otherwise mark failed and return False.
    """
    job_key = _JOB_KEY.format(job_id=job.job_id)
    attempts = int(redis.hget(job_key, "attempts") or 1)

    if attempts < _MAX_ATTEMPTS:
        redis.hset(job_key, mapping={"state": "queued", "error_code": error_code})
        # Re-enqueue at front of the user's queue (priority retry)
        user_key = _USER_QUEUE_KEY.format(user_id=job.user_id)
        pipe = redis.pipeline()
        pipe.lpush(user_key, job.model_dump_json())
        pipe.zadd(_ACTIVE_USERS_KEY, {str(job.user_id): 0}, nx=True)
        pipe.execute()
        return True

    redis.hset(job_key, mapping={"state": "failed", "error_code": error_code})
    return False


def get_job_state(redis: RedisClient, job_id: uuid.UUID) -> dict[str, str]:
    """Return the current state dict for a job."""
    job_key = _JOB_KEY.format(job_id=job_id)
    return redis.hgetall(job_key)
