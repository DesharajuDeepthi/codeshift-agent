"""Typed error codes for UpgradePilot."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    REPOSITORY_INACCESSIBLE = "REPOSITORY_INACCESSIBLE"
    UNSUPPORTED_REPOSITORY = "UNSUPPORTED_REPOSITORY"
    SAFETY_LIMIT_EXCEEDED = "SAFETY_LIMIT_EXCEEDED"
    MIGRATION_NOT_APPLICABLE = "MIGRATION_NOT_APPLICABLE"
    DOCUMENTATION_UNAVAILABLE = "DOCUMENTATION_UNAVAILABLE"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    OBSERVABILITY_DEGRADED = "OBSERVABILITY_DEGRADED"
    CACHE_DEGRADED = "CACHE_DEGRADED"
    REQUEST_INVALID = "REQUEST_INVALID"
    PACK_UNSUPPORTED = "PACK_UNSUPPORTED"
    CHECKPOINT_UNAVAILABLE = "CHECKPOINT_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class UpgradePilotError(Exception):
    """Base exception for UpgradePilot."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class RepositoryInaccessibleError(UpgradePilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.REPOSITORY_INACCESSIBLE, message)


class SafetyLimitError(UpgradePilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.SAFETY_LIMIT_EXCEEDED, message)


class MigrationNotApplicableError(UpgradePilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.MIGRATION_NOT_APPLICABLE, message)


class LLMUnavailableError(UpgradePilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.LLM_UNAVAILABLE, message)


class ValidationFailedError(UpgradePilotError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.VALIDATION_FAILED, message)
