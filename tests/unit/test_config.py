"""Unit tests for application configuration."""

from __future__ import annotations

import pytest

from upgradepilot.config import Environment, Settings


def test_defaults_are_valid() -> None:
    s = Settings()
    assert s.upgradepilot_env == Environment.DEV
    assert s.langsmith_project == "upgradepilot-dev"
    assert s.api_port == 8000


def test_project_name_reflects_env() -> None:
    s = Settings(upgradepilot_env=Environment.PROD)
    assert s.langsmith_project_name == "upgradepilot-prod"


def test_tracing_disabled_without_api_key() -> None:
    s = Settings(langsmith_tracing=True, langsmith_api_key=None)
    assert s.tracing_enabled is False


def test_tracing_enabled_with_api_key() -> None:
    s = Settings(langsmith_tracing=True, langsmith_api_key="ls__fake_key_for_tests")  # noqa: S106
    assert s.tracing_enabled is True


def test_safety_limits_positive() -> None:
    s = Settings()
    assert s.max_archive_compressed_bytes > 0
    assert s.max_archive_extracted_bytes > 0
    assert s.max_archive_file_count > 0
    assert s.max_path_depth > 0
    assert s.max_single_file_bytes > 0
    assert s.analysis_timeout_seconds > 0


def test_safety_limit_must_be_positive() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        Settings(max_archive_file_count=-1)


def test_database_url_is_secret_not_leaked_in_repr() -> None:
    s = Settings()
    output = repr(s)
    # The password must not appear in plain text in the repr
    assert "upgradepilot:upgradepilot@" not in output


def test_database_url_accessible_via_get_secret_value() -> None:
    s = Settings()
    url = s.database_url.get_secret_value()
    assert url.startswith("postgresql+psycopg://")
    assert "upgradepilot" in url
