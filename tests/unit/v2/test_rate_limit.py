"""Unit tests for the Redis token-bucket rate limiter."""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import fakeredis

from upgradepilot.queue.rate_limit import consume, remaining_tokens


def _redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _uid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Basic allow / deny
# ---------------------------------------------------------------------------


def test_first_request_allowed():
    r = _redis()
    assert consume(r, _uid()) is True


def test_requests_within_limit_allowed():
    r = _redis()
    uid = _uid()
    for _ in range(10):
        assert consume(r, uid, max_tokens=10) is True


def test_request_over_limit_denied():
    r = _redis()
    uid = _uid()
    for _ in range(10):
        consume(r, uid, max_tokens=10)
    assert consume(r, uid, max_tokens=10) is False


def test_different_users_independent_buckets():
    r = _redis()
    a, b = _uid(), _uid()
    for _ in range(10):
        consume(r, a, max_tokens=10)
    # user a is exhausted, user b still has tokens
    assert consume(r, a, max_tokens=10) is False
    assert consume(r, b, max_tokens=10) is True


# ---------------------------------------------------------------------------
# Refill
# ---------------------------------------------------------------------------


def test_tokens_refill_over_time():
    r = _redis()
    uid = _uid()
    # drain the bucket
    for _ in range(10):
        consume(r, uid, max_tokens=10, refill_rate=10 / 60)
    assert consume(r, uid, max_tokens=10, refill_rate=10 / 60) is False

    # advance clock by 7 seconds — should refill ~1 token (10/60 * 7 ≈ 1.17)
    future = time.time() + 7
    with patch("upgradepilot.queue.rate_limit.time.time", return_value=future):
        assert consume(r, uid, max_tokens=10, refill_rate=10 / 60) is True


# ---------------------------------------------------------------------------
# remaining_tokens
# ---------------------------------------------------------------------------


def test_remaining_tokens_full_bucket_for_new_user():
    r = _redis()
    uid = _uid()
    # No key set yet → defaults to max
    assert remaining_tokens(r, uid) == 10.0


def test_remaining_tokens_decreases_after_consume():
    r = _redis()
    uid = _uid()
    consume(r, uid, max_tokens=10)
    assert remaining_tokens(r, uid) < 10.0
