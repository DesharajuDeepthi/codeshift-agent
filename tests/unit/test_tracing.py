"""Unit tests for LangSmith tracing bootstrap."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
from prometheus_client import generate_latest

from upgradepilot.graph.build import build_graph
from upgradepilot.graph.state import (
    FIXTURE_SUPPORTED,
    FIXTURE_VALIDATION_STRUCTURAL,
    AnalysisStatus,
    make_initial_state,
)
from upgradepilot.observability.metrics import REGISTRY
from upgradepilot.observability.tracing import (
    UserFeedback,
    attach_user_feedback,
    configure_langsmith,
    reset_tracing_for_tests,
    set_langsmith_client_for_tests,
)


class FakeLangSmithClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.feedback: list[dict[str, Any]] = []

    def create_run(self, **kwargs: Any) -> None:
        self.created.append(kwargs)

    def update_run(self, **kwargs: Any) -> None:
        self.updated.append(kwargs)

    def create_feedback(self, *args: Any, **kwargs: Any) -> None:
        self.feedback.append({"args": args, "kwargs": kwargs})

    def get_run_url(self, *, run: Any) -> str:
        return f"https://smith.test/runs/{run.id}"


class FailingLangSmithClient(FakeLangSmithClient):
    def create_run(self, **kwargs: Any) -> None:
        raise RuntimeError("langsmith down token=sk-ant-api03-supersecretvalue000000")


_FIXTURE_REQUEST = {
    "repository_url": "https://github.com/test-owner/test-repo",
    "ref": "main",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "fixture",
    "request_id": "trace-test-req",
    "github_owner": "test-owner",
    "github_repo": "test-repo",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    """Remove tracing env vars before each test to avoid cross-test pollution."""
    for key in (
        "LANGSMITH_TRACING_V2",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGSMITH_PROJECT",
        "LANGCHAIN_PROJECT",
        "LANGSMITH_ENDPOINT",
        "LANGCHAIN_ENDPOINT",
        "LANGSMITH_HIDE_INPUTS",
        "LANGSMITH_HIDE_OUTPUTS",
        "UPGRADEPILOT_ENV",
    ):
        monkeypatch.delenv(key, raising=False)
    reset_tracing_for_tests()
    yield
    reset_tracing_for_tests()


def _run_fixture_graph(scenario: str = FIXTURE_SUPPORTED) -> dict[str, Any]:
    graph = build_graph()
    state = make_initial_state(
        analysis_id=str(uuid.uuid4()),
        request_data=_FIXTURE_REQUEST,
        fixture_scenario=scenario,
    )
    return asyncio.run(graph.ainvoke(state))


def _disable_langgraph_auto_tracing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests on the fake manual client instead of LangGraph SDK auto-tracing."""
    monkeypatch.setenv("LANGSMITH_TRACING_V2", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


def test_returns_false_when_no_api_key() -> None:
    result = configure_langsmith(
        api_key=None,
        project="test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )
    assert result is False


def test_returns_false_when_tracing_disabled() -> None:
    result = configure_langsmith(
        api_key="ls__fake",
        project="test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=False,
    )
    assert result is False


def test_disabling_sets_both_namespace_env_vars_to_false() -> None:
    configure_langsmith(
        api_key=None,
        project="test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=False,
    )
    assert os.environ.get("LANGSMITH_TRACING_V2") == "false"
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "false"


def test_returns_true_when_configured() -> None:
    result = configure_langsmith(
        api_key="ls__fake_key_for_tests",
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )
    assert result is True


def test_enabling_sets_primary_and_legacy_env_vars() -> None:
    configure_langsmith(
        api_key="ls__fake_key_for_tests",
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )
    # Primary (LANGSMITH_*) must be set
    assert os.environ.get("LANGSMITH_TRACING_V2") == "true"
    assert os.environ.get("LANGSMITH_API_KEY") == "ls__fake_key_for_tests"
    assert os.environ.get("LANGSMITH_PROJECT") == "upgradepilot-test"
    # Legacy (LANGCHAIN_*) must also be set for langchain-core compat
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_API_KEY") == "ls__fake_key_for_tests"


def test_hide_inputs_flag_sets_env() -> None:
    configure_langsmith(
        api_key="ls__fake",
        project="test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
        hide_inputs=True,
    )
    assert os.environ.get("LANGSMITH_HIDE_INPUTS") == "true"


def test_graph_trace_attaches_metadata_tags_and_child_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPGRADEPILOT_ENV", "test")
    fake = FakeLangSmithClient()
    set_langsmith_client_for_tests(fake)
    configure_langsmith(
        api_key="ls__fake_key_for_tests",
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )
    _disable_langgraph_auto_tracing(monkeypatch)

    result = _run_fixture_graph()

    assert result["status"] == AnalysisStatus.COMPLETED
    assert result["final_report"]["observability"]["status"] == "configured"
    assert result["final_report"]["observability"]["langsmith_submitted"] is True

    created_names = [run["name"] for run in fake.created]
    assert "upgradepilot.analysis" in created_names
    assert any(name.startswith("node.") for name in created_names)
    assert any(name.startswith("agent.") for name in created_names)
    assert any(name.startswith("tool.") for name in created_names)
    assert any(name.startswith("validator.") for name in created_names)
    assert any(name.startswith("report.") for name in created_names)
    assert any(name.startswith("llm.") for name in created_names)

    root = next(run for run in fake.created if run["name"] == "upgradepilot.analysis")
    metadata = root["extra"]["metadata"]
    assert metadata["analysis_id"] == result["analysis_id"]
    assert metadata["request_id"] == "trace-test-req"
    assert metadata["repository"] == "test-owner/test-repo"
    assert metadata["requested_ref"] == "main"
    assert metadata["pack_id"] == "pydantic-v1-to-v2"
    assert "pack_version" in metadata
    assert "detector_version" in metadata
    assert "scoring_version" in metadata

    tags = set(root["tags"])
    assert "env:test" in tags
    assert "pack:pydantic-v1-to-v2" in tags
    assert "mode:fixture" in tags
    assert "source:fixture" in tags

    node_records = result.get("node_executions") or []
    assert all(record.get("langsmith_run_id") for record in node_records)


def test_langsmith_outage_does_not_fail_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    set_langsmith_client_for_tests(FailingLangSmithClient())
    configure_langsmith(
        api_key="ls__fake_key_for_tests",
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )
    _disable_langgraph_auto_tracing(monkeypatch)

    result = _run_fixture_graph()

    assert result["status"] == AnalysisStatus.COMPLETED
    observability = result["final_report"]["observability"]
    assert observability["status"] == "degraded"
    assert observability["langsmith_submitted"] is False
    assert "sk-ant-api03" not in str(observability)
    assert "[REDACTED]" in str(observability)


def test_analysis_continues_when_tracing_disabled() -> None:
    configure_langsmith(
        api_key=None,
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )

    result = _run_fixture_graph()

    assert result["status"] == AnalysisStatus.COMPLETED
    observability = result["final_report"]["observability"]
    assert observability["status"] == "disabled"
    assert observability["langsmith_submitted"] is False
    assert observability["trace_id"]


def test_prometheus_metrics_are_emitted_for_graph_and_validation() -> None:
    configure_langsmith(
        api_key=None,
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=False,
    )

    _run_fixture_graph(FIXTURE_VALIDATION_STRUCTURAL)

    metrics = generate_latest(REGISTRY).decode()
    assert "upgradepilot_graph_node_duration_seconds_bucket" in metrics
    assert "upgradepilot_graph_node_runs_total" in metrics
    assert 'upgradepilot_analyses_total{status="partial"}' in metrics
    assert (
        'upgradepilot_llm_calls_total{agent="documentation_research",status="completed"}' in metrics
    )
    assert 'upgradepilot_validation_issues_total{severity="error"}' in metrics


def test_user_feedback_attaches_to_root_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPGRADEPILOT_ENV", "test")
    fake = FakeLangSmithClient()
    set_langsmith_client_for_tests(fake)
    configure_langsmith(
        api_key="ls__fake_key_for_tests",
        project="upgradepilot-test",
        endpoint="https://api.smith.langchain.com",
        tracing_enabled=True,
    )
    _disable_langgraph_auto_tracing(monkeypatch)
    state = make_initial_state(
        analysis_id=str(uuid.uuid4()),
        request_data=_FIXTURE_REQUEST,
        fixture_scenario=FIXTURE_SUPPORTED,
    )
    from upgradepilot.observability.tracing import start_analysis_trace

    start_analysis_trace(state)
    attached = attach_user_feedback(
        UserFeedback(
            analysis_id=state["analysis_id"],
            request_id="trace-test-req",
            key="useful",
            score=True,
            comment="Looks useful; api_key=sk-ant-api03-supersecretvalue000000",
        )
    )

    assert attached is True
    assert fake.feedback
    payload = fake.feedback[0]["kwargs"]
    assert payload["key"] == "useful"
    assert "sk-ant-api03" not in str(payload)
