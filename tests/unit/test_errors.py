"""Unit tests for typed error codes."""

from __future__ import annotations

from upgradepilot.errors import (
    ErrorCode,
    RepositoryInaccessibleError,
    SafetyLimitError,
    UpgradePilotError,
)


def test_error_code_enum_members() -> None:
    assert ErrorCode.REPOSITORY_INACCESSIBLE == "REPOSITORY_INACCESSIBLE"
    assert ErrorCode.SAFETY_LIMIT_EXCEEDED == "SAFETY_LIMIT_EXCEEDED"


def test_upgradepilot_error_carries_code() -> None:
    err = UpgradePilotError(ErrorCode.INTERNAL_ERROR, "something went wrong")
    assert err.code == ErrorCode.INTERNAL_ERROR
    assert "something went wrong" in str(err)


def test_typed_subclass_sets_code() -> None:
    err = RepositoryInaccessibleError("repo not found")
    assert err.code == ErrorCode.REPOSITORY_INACCESSIBLE

    err2 = SafetyLimitError("archive too large")
    assert err2.code == ErrorCode.SAFETY_LIMIT_EXCEEDED
