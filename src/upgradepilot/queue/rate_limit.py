"""
Redis token-bucket rate limiter — one bucket per user.

Algorithm:
  - Each user has a bucket with capacity MAX_TOKENS.
  - Tokens refill at REFILL_RATE tokens/second based on wall time.
  - consume() uses a Redis pipeline with WATCH for optimistic locking,
    retrying on concurrent modification (rare — one bucket per user).

Default: 10 requests / 60 seconds per user.
"""

from __future__ import annotations

import time
import uuid

from redis.exceptions import WatchError

from upgradepilot.queue.jobs import RedisClient

_BUCKET_KEY = "ratelimit:{user_id}"
_MAX_TOKENS = 10
_REFILL_RATE = 10 / 60  # tokens per second
_BUCKET_TTL_S = 3600
_MAX_RETRIES = 3


def consume(
    redis: RedisClient,
    user_id: uuid.UUID,
    *,
    max_tokens: int = _MAX_TOKENS,
    refill_rate: float = _REFILL_RATE,
) -> bool:
    """
    Attempt to consume one token for this user.

    Returns True if the request is allowed, False if rate-limited.
    Uses optimistic locking (WATCH/MULTI/EXEC) so concurrent workers
    don't double-spend tokens.
    """
    key = _BUCKET_KEY.format(user_id=user_id)

    for _ in range(_MAX_RETRIES):
        try:
            with redis.pipeline() as pipe:  # type: ignore[attr-defined]
                pipe.watch(key)
                now = time.time()

                raw_tokens = pipe.hget(key, "tokens")
                raw_last = pipe.hget(key, "last_refill")

                tokens = float(raw_tokens) if raw_tokens else float(max_tokens)
                last_refill = float(raw_last) if raw_last else now

                elapsed = max(0.0, now - last_refill)
                tokens = min(float(max_tokens), tokens + elapsed * refill_rate)

                if tokens < 1:
                    pipe.unwatch()
                    pipe.hset(key, mapping={"tokens": tokens, "last_refill": now})
                    pipe.expire(key, _BUCKET_TTL_S)
                    pipe.execute()
                    return False

                new_tokens = tokens - 1
                pipe.multi()
                pipe.hset(key, mapping={"tokens": new_tokens, "last_refill": now})
                pipe.expire(key, _BUCKET_TTL_S)
                pipe.execute()
                return True

        except WatchError:
            continue

    return False


def remaining_tokens(redis: RedisClient, user_id: uuid.UUID) -> float:
    """Return the current token count for a user (for observability)."""
    key = _BUCKET_KEY.format(user_id=user_id)
    raw = redis.hget(key, "tokens")  # type: ignore[attr-defined]
    return float(raw) if raw is not None else float(_MAX_TOKENS)


def consume_or_reject(
    redis: RedisClient,
    user_id: uuid.UUID,
    *,
    max_tokens: int = _MAX_TOKENS,
    refill_rate: float = _REFILL_RATE,
) -> bool:
    """
    consume() + Prometheus instrumentation.

    Emits record_rate_limited when the request is denied.
    Returns True if allowed, False if rate-limited.
    """
    from upgradepilot.observability.metrics import record_rate_limited  # local import avoids cycle

    allowed = consume(redis, user_id, max_tokens=max_tokens, refill_rate=refill_rate)
    if not allowed:
        record_rate_limited(user_id=str(user_id))
    return allowed
