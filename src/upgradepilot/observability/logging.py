"""Structured JSON logging foundation."""

from __future__ import annotations

import contextvars
import logging
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from pythonjsonlogger.json import JsonFormatter

from upgradepilot.observability.redaction import redact, sanitize_value

_LOG_CONTEXT: contextvars.ContextVar[dict[str, object] | None] = contextvars.ContextVar(
    "upgradepilot_log_context",
    default=None,
)


class RedactingFilter(logging.Filter):
    """Masks secrets in log messages and structured extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                sanitize_value(arg, max_string_chars=256, max_lines=4) for arg in record.args
            )
        elif isinstance(record.args, Mapping):
            record.args = {
                str(key): sanitize_value(value, max_string_chars=256, max_lines=4)
                for key, value in record.args.items()
            }
        return True


class UpgradePilotFormatter(JsonFormatter):
    """Extends pythonjsonlogger to include required UpgradePilot fields."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        if "timestamp" not in log_record:
            log_record["timestamp"] = self.formatTime(record, self.datefmt)
        log_record.setdefault("service", "upgradepilot")
        log_record.setdefault("severity", record.levelname)
        context = _LOG_CONTEXT.get() or {}
        for field in (
            "request_id",
            "analysis_id",
            "trace_id",
            "run_id",
            "repository",
            "commit_sha",
            "node",
            "component",
            "error_code",
            "duration_ms",
        ):
            log_record.setdefault(field, context.get(field))

        for key, value in list(log_record.items()):
            log_record[key] = sanitize_value(value, max_string_chars=512, max_lines=8)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with structured JSON output."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        UpgradePilotFormatter(
            fmt="%(timestamp)s %(severity)s %(service)s %(event)s %(message)s",
            rename_fields={"levelname": "severity", "asctime": "timestamp"},
        )
    )
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def log_context(**fields: object) -> Iterator[None]:
    """Temporarily attach trace/request correlation fields to structured logs."""
    current = dict(_LOG_CONTEXT.get() or {})
    current.update({key: value for key, value in fields.items() if value is not None})
    token = _LOG_CONTEXT.set(current)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)
