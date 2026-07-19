"""Typed errors for the migration-pack framework."""

from __future__ import annotations

from upgradepilot.errors import ErrorCode, UpgradePilotError


class PackLoadError(UpgradePilotError):
    """Raised when a pack cannot be loaded or fails schema validation."""

    def __init__(self, pack_id: str, reason: str) -> None:
        super().__init__(ErrorCode.PACK_UNSUPPORTED, f"Pack {pack_id!r}: {reason}")
        self.pack_id = pack_id
        self.reason = reason


class PackNotFoundError(PackLoadError):
    """Raised when a requested pack ID is not registered."""

    def __init__(self, pack_id: str) -> None:
        super().__init__(pack_id, f"no pack with id {pack_id!r} is registered")


class PackSchemaError(PackLoadError):
    """Raised when a pack YAML file fails schema validation."""

    def __init__(self, pack_id: str, file: str, detail: str) -> None:
        super().__init__(pack_id, f"schema validation failed for {file!r}: {detail}")
        self.file = file
        self.detail = detail


class PackMissingFileError(PackLoadError):
    """Raised when a required file is absent from the pack directory."""

    def __init__(self, pack_id: str, missing_file: str) -> None:
        super().__init__(pack_id, f"required file missing: {missing_file!r}")
        self.missing_file = missing_file


class PackPromptError(PackLoadError):
    """Raised when a prompt template cannot be loaded or is malformed."""

    def __init__(self, pack_id: str, prompt_id: str, detail: str) -> None:
        super().__init__(pack_id, f"prompt {prompt_id!r}: {detail}")
        self.prompt_id = prompt_id
