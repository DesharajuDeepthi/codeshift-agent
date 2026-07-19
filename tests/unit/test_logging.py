"""Unit tests for structured observability logs."""

from __future__ import annotations

import json
import logging

from upgradepilot.observability.logging import UpgradePilotFormatter, log_context


def test_formatter_adds_trace_context_and_redacts_message() -> None:
    formatter = UpgradePilotFormatter(
        fmt="%(timestamp)s %(severity)s %(service)s %(event)s %(message)s",
        rename_fields={"levelname": "severity", "asctime": "timestamp"},
    )
    secret = "sk-ant-api03-" + "x" * 30
    record = logging.LogRecord(
        name="upgradepilot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="token=%s",
        args=(secret,),
        exc_info=None,
    )
    record.event = "test_event"

    with log_context(analysis_id="analysis-1", request_id="request-1", trace_id="trace-1"):
        payload = json.loads(formatter.format(record))

    assert payload["analysis_id"] == "analysis-1"
    assert payload["request_id"] == "request-1"
    assert payload["trace_id"] == "trace-1"
    assert secret not in str(payload)
    assert "[REDACTED]" in str(payload)
