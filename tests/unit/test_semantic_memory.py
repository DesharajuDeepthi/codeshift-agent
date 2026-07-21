"""Unit tests for upgradepilot.memory.semantic (no Postgres required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from upgradepilot.memory.semantic import _finding_text, _embed, store_findings_embeddings, retrieve_similar_findings


# ---------------------------------------------------------------------------
# _finding_text
# ---------------------------------------------------------------------------

def test_finding_text_basic() -> None:
    f = {"rule_id": "V1_MODEL", "file": "src/app.py", "severity": "high", "snippet": "class Foo(BaseModel):"}
    text = _finding_text(f)
    assert "rule: V1_MODEL" in text
    assert "file: src/app.py" in text
    assert "severity: high" in text
    assert "snippet: class Foo(BaseModel):" in text


def test_finding_text_empty_fields_excluded() -> None:
    f = {"rule_id": "V1_MODEL", "file": "", "severity": "", "snippet": ""}
    text = _finding_text(f)
    assert "file:" not in text
    assert "severity:" not in text
    assert "snippet:" not in text


def test_finding_text_uses_code_snippet_fallback() -> None:
    f = {"rule_id": "R1", "file": "a.py", "severity": "low", "code_snippet": "x = 1"}
    text = _finding_text(f)
    assert "snippet: x = 1" in text


# ---------------------------------------------------------------------------
# store_findings_embeddings — no-ops when env not set
# ---------------------------------------------------------------------------

def test_store_findings_noop_without_db() -> None:
    with patch.dict("os.environ", {"DATABASE_URL": "", "LLM_API_KEY": ""}):
        n = store_findings_embeddings(
            [{"finding_id": "f1", "rule_id": "R1", "file": "a.py", "severity": "low"}],
            analysis_id="a1",
            repository_url="https://github.com/example/repo",
        )
    assert n == 0


def test_store_findings_noop_when_empty() -> None:
    n = store_findings_embeddings([], analysis_id="a1", repository_url="u")
    assert n == 0


# ---------------------------------------------------------------------------
# retrieve_similar_findings — no-ops when env not set
# ---------------------------------------------------------------------------

def test_retrieve_noop_without_db() -> None:
    with patch.dict("os.environ", {"DATABASE_URL": "", "LLM_API_KEY": ""}):
        result = retrieve_similar_findings(
            {"rule_id": "R1", "file": "a.py"},
            exclude_analysis_id="a1",
        )
    assert result == []


# ---------------------------------------------------------------------------
# _embed — validates API call shape
# ---------------------------------------------------------------------------

def test_embed_calls_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "data": [{"index": 0, "embedding": [0.1] * 1536}]
    }

    import httpx
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    with patch("httpx.post", return_value=fake_resp) as mock_post:
        vectors = _embed(["hello world"])

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[1]["json"]["model"] == "text-embedding-3-small"
    assert call_kwargs[1]["json"]["input"] == ["hello world"]
    assert len(vectors) == 1
    assert len(vectors[0]) == 1536


def test_embed_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        _embed(["text"])
