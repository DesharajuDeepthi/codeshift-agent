"""Unit tests for thread_id derivation and previous-findings retrieval."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from upgradepilot.memory.store import get_previous_findings
from upgradepilot.memory.thread import make_thread_id

# ---------------------------------------------------------------------------
# make_thread_id — pure function, no I/O
# ---------------------------------------------------------------------------


def test_same_inputs_same_output():
    user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    url = "https://github.com/acme/repo"
    assert make_thread_id(user_id, url) == make_thread_id(user_id, url)


def test_different_users_different_thread():
    url = "https://github.com/acme/repo"
    a = make_thread_id(uuid.uuid4(), url)
    b = make_thread_id(uuid.uuid4(), url)
    assert a != b


def test_different_repos_different_thread():
    user_id = uuid.uuid4()
    a = make_thread_id(user_id, "https://github.com/acme/repo-a")
    b = make_thread_id(user_id, "https://github.com/acme/repo-b")
    assert a != b


def test_url_trailing_slash_normalised():
    user_id = uuid.uuid4()
    assert make_thread_id(user_id, "https://github.com/acme/repo/") == make_thread_id(
        user_id, "https://github.com/acme/repo"
    )


def test_url_case_normalised():
    user_id = uuid.uuid4()
    assert make_thread_id(user_id, "https://GitHub.com/ACME/Repo") == make_thread_id(
        user_id, "https://github.com/acme/repo"
    )


def test_output_is_hex_string():
    tid = make_thread_id(uuid.uuid4(), "https://github.com/acme/repo")
    assert len(tid) == 64
    assert all(c in "0123456789abcdef" for c in tid)


# ---------------------------------------------------------------------------
# get_previous_findings — mocked DB connection
# ---------------------------------------------------------------------------


def _mock_conn(row: dict | None) -> MagicMock:
    conn = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = (row,) if row is not None else None
    conn.execute.return_value = result
    return conn


def test_no_prior_run_returns_empty():
    conn = _mock_conn(None)
    assert get_previous_findings("some-thread-id", conn) == []


def test_returns_findings_from_report():
    findings = [{"rule_id": "PYD001", "file_path": "app/models.py"}]
    conn = _mock_conn({"findings": findings, "summary": "1 finding"})
    result = get_previous_findings("tid", conn)
    assert result == findings


def test_report_without_findings_key_returns_empty():
    conn = _mock_conn({"summary": "no findings key present"})
    assert get_previous_findings("tid", conn) == []


def test_report_with_empty_findings_returns_empty():
    conn = _mock_conn({"findings": []})
    assert get_previous_findings("tid", conn) == []
