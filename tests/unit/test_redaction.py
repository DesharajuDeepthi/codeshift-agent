"""Unit tests for secret redaction."""

from __future__ import annotations

from upgradepilot.observability.redaction import bounded_text, redact, sanitize_value


def test_api_key_value_redacted_but_prefix_kept() -> None:
    result = redact("api_key=sk-supersecretvalue123")
    assert "sk-supersecretvalue123" not in result
    assert result.startswith("api_key=")
    assert "[REDACTED]" in result


def test_password_value_redacted_but_prefix_kept() -> None:
    result = redact("password=hunter2")
    assert "hunter2" not in result
    assert result.startswith("password=")
    assert "[REDACTED]" in result


def test_authorization_bearer_redacted_but_header_kept() -> None:
    result = redact("Authorization: Bearer ghp_abc123def456ghi789jkl012mno345pqr678")
    assert "ghp_abc123def456ghi789jkl012mno345pqr678" not in result
    assert "Authorization: Bearer" in result
    assert "[REDACTED]" in result


def test_bare_anthropic_key_redacted() -> None:
    result = redact("key is sk-ant-api03-supersecretkeyvalue12345")
    assert "sk-ant-api03-supersecretkeyvalue12345" not in result
    assert "[REDACTED]" in result


def test_bare_langsmith_key_redacted() -> None:
    long_key = "ls__" + "a" * 40
    result = redact(f"using key={long_key}")
    assert long_key not in result


def test_non_secret_text_unchanged() -> None:
    safe = "This is a normal log message with no secrets"
    assert redact(safe) == safe


def test_empty_string_unchanged() -> None:
    assert redact("") == ""


def test_sensitive_mapping_values_are_redacted_recursively() -> None:
    secret = "sk-ant-api03-" + "x" * 30
    payload = {
        "headers": {"Authorization": f"Bearer {secret}"},
        "nested": [{"github_token": "ghp_" + "a" * 36}],
    }
    result = sanitize_value(payload)
    rendered = str(result)
    assert secret not in rendered
    assert "ghp_" not in rendered
    assert "[REDACTED]" in rendered


def test_bounded_text_limits_source_snippets_and_preserves_hash_marker() -> None:
    secret = "password=hunter2"
    snippet = "\n".join([f"line {idx} {secret}" for idx in range(20)])
    result = bounded_text(snippet, max_chars=80, max_lines=4)
    assert "hunter2" not in result
    assert "[REDACTED]" in result
    assert "[TRUNCATED]" in result
    assert "sha256:" in result
