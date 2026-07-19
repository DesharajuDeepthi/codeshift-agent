"""Integration tests for the analysis API, progress stream, exports, and feedback."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import upgradepilot.api.analyses as analyses
from upgradepilot.api.main import create_app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    with TestClient(create_app(), raise_server_exceptions=True) as test_client:
        yield test_client


def _create_fixture_analysis(client: TestClient) -> str:
    response = client.post(
        "/analyses",
        json={
            "repository_url": "https://github.com/pydantic/pydantic",
            "ref": "main",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "fixture",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] in {"completed", "partial", "terminal"}
    return str(body["analysis_id"])


def test_fixture_analysis_status_report_and_exports(client: TestClient) -> None:
    analysis_id = _create_fixture_analysis(client)

    status_response = client.get(f"/analyses/{analysis_id}")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["progress"] == 1.0
    assert status_body["report_status"] == "validated"
    assert status_body["commit_sha"]
    assert status_body["migration_pack_version"]
    assert status_body["trace_id"]

    report_response = client.get(f"/analyses/{analysis_id}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["status"] == "validated"
    assert report["profile"]
    assert report["applicability_status"] == "SUPPORTED"
    assert report["migration_pack_version"]
    assert report["observability"]["status"] in {"disabled", "configured", "degraded"}

    json_response = client.get(f"/analyses/{analysis_id}/report.json")
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert b"authorization" not in json_response.content.lower()

    markdown_response = client.get(f"/analyses/{analysis_id}/report.md")
    assert markdown_response.status_code == 200
    markdown = markdown_response.text
    assert "## Facts" in markdown
    assert "## Interpretations" in markdown
    assert "## Recommendations" in markdown
    assert "## Trace Correlation" in markdown

    issue_response = client.get(f"/analyses/{analysis_id}/github-issue.md")
    assert issue_response.status_code == 200
    assert "## UpgradePilot Migration Plan" in issue_response.text
    assert "does not claim that code was changed or tests passed" in issue_response.text


def test_progress_stream_replays_graph_events(client: TestClient) -> None:
    analysis_id = _create_fixture_analysis(client)

    with client.stream("GET", f"/analyses/{analysis_id}/events") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: progress" in text
    assert "validate_request" in text
    assert "assemble_validated_report" in text
    assert "event: done" in text


def test_feedback_is_accepted_without_active_trace(client: TestClient) -> None:
    analysis_id = _create_fixture_analysis(client)

    response = client.post(
        f"/analyses/{analysis_id}/feedback",
        json={"key": "useful", "score": True, "comment": "Clear and useful."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"] == analysis_id
    assert body["status"] in {"attached", "accepted_without_trace"}


def test_invalid_analysis_request_has_no_stack_trace(client: TestClient) -> None:
    response = client.post(
        "/analyses",
        json={
            "repository_url": "file:///tmp/repo",
            "ref": "main",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "fixture",
        },
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text


def test_standard_analysis_graph_uses_postgres_checkpointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSaver:
        setup_called = False

        async def setup(self) -> None:
            self.setup_called = True

    class FakeGraph:
        pass

    saver = FakeSaver()
    graph = FakeGraph()
    calls: dict[str, object] = {}

    @asynccontextmanager
    async def fake_postgres_checkpointer(database_url: str) -> AsyncIterator[FakeSaver]:
        calls["database_url"] = database_url
        yield saver

    def fake_build_graph(*, checkpointer: object = None) -> FakeGraph:
        calls["checkpointer"] = checkpointer
        return graph

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@postgres:5432/upgradepilot")
    monkeypatch.setattr(analyses, "get_postgres_checkpointer", fake_postgres_checkpointer)
    monkeypatch.setattr(analyses, "build_graph", fake_build_graph)

    record = analyses._AnalysisRecord(
        analysis_id="analysis-postgres",
        request={
            "repository_url": "https://github.com/pydantic/pydantic",
            "ref": "main",
            "migration_pack": "pydantic-v1-to-v2",
            "analysis_mode": "standard",
        },
        status="running",
        report_status="pending",
        state={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def run() -> None:
        async with analyses._analysis_graph(record) as resolved:
            assert resolved is graph

    asyncio.run(run())

    assert saver.setup_called
    assert calls["checkpointer"] is saver
    assert calls["database_url"] == "postgresql://user:pass@postgres:5432/upgradepilot"


def test_report_is_complete_and_untruncated(client: TestClient) -> None:
    """The served report must keep every field; sanitization must never drop keys.

    Regression test: state merging previously applied trace-export sanitization
    (20-item dict cap) to the canonical report, silently dropping keys such as
    node_executions, warnings, and limitations.
    """
    analysis_id = _create_fixture_analysis(client)

    report = client.get(f"/analyses/{analysis_id}/report").json()

    assert "_truncated_items" not in report
    required_keys = {
        "analysis_id",
        "generated_at",
        "repository_url",
        "ref",
        "migration_pack",
        "commit_sha",
        "status",
        "findings",
        "dependencies",
        "documentation_evidence",
        "risk_assessment",
        "plan_draft",
        "validation_outcome",
        "validation_issues",
        "warnings",
        "limitations",
        "node_executions",
        "observability",
    }
    missing = required_keys - set(report)
    assert not missing, f"Report is missing required keys: {sorted(missing)}"
    assert report["node_executions"], "node_executions must be present and non-empty"
    assert "[TRUNCATED]" not in str(report), "report content must not be truncated"
