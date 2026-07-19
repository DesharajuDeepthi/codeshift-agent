"""Secret redaction before logging and LangSmith trace submission."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

_REDACTED = "[REDACTED]"
_TRUNCATED = "[TRUNCATED]"
DEFAULT_MAX_STRING_CHARS = 512
DEFAULT_MAX_LINES = 8
DEFAULT_MAX_COLLECTION_ITEMS = 20
DEFAULT_MAX_DEPTH = 6

# Two-part patterns: group 1 = prefix to keep, group 2 = secret value to redact.
# The replacement keeps group 1 and replaces group 2 with [REDACTED].
_PREFIX_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(Authorization:\s*Bearer\s+)([^\s\"']+)", re.IGNORECASE),
    re.compile(r"(Authorization\s*[=:]\s*Bearer\s+)([^\s\"']+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[=:]\s*)([^\s\"',]+)", re.IGNORECASE),
    re.compile(r"(token\s*[=:]\s*)([^\s\"',]+)", re.IGNORECASE),
    re.compile(r"(secret\s*[=:]\s*)([^\s\"',]+)", re.IGNORECASE),
    re.compile(r"(password\s*[=:]\s*)([^\s\"',]+)", re.IGNORECASE),
    re.compile(r"(cookie\s*[=:]\s*)([^\n\r]+)", re.IGNORECASE),
    re.compile(r"(set-cookie\s*[=:]\s*)([^\n\r]+)", re.IGNORECASE),
]

# Bare secret patterns: the entire match is redacted (no prefix to keep).
# sk- keys include Anthropic-style tokens like sk-ant-api03-<payload>.
_BARE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9]{36}", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"ls__[A-Za-z0-9]{40,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]

_SENSITIVE_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
    "api_key",
    "apikey",
)


def redact(text: str) -> str:
    """Replace known secret patterns with [REDACTED]."""
    for pattern in _PREFIX_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + _REDACTED, text)
    for pattern in _BARE_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def bounded_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_STRING_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Redact and bound source/prompt snippets before observability export."""
    redacted = redact(text)
    lines = redacted.splitlines()
    line_limited = False
    if len(lines) > max_lines:
        redacted = "\n".join(lines[:max_lines])
        line_limited = True

    char_limited = False
    if len(redacted) > max_chars:
        redacted = redacted[:max_chars]
        char_limited = True

    if line_limited or char_limited:
        original_hash = _digest(text)
        redacted = (
            f"{redacted}\n{_TRUNCATED} "
            f"sha256:{original_hash} chars:{len(text)} lines:{len(lines) or 1}"
        )
    return redacted


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_value(
    value: object,
    *,
    max_string_chars: int = DEFAULT_MAX_STRING_CHARS,
    max_lines: int = DEFAULT_MAX_LINES,
    max_collection_items: int = DEFAULT_MAX_COLLECTION_ITEMS,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> object:
    """
    Recursively redact and bound values before logs, traces, or feedback payloads.

    Large source snippets are represented by a bounded prefix plus a short hash,
    not by full content.
    """
    if max_depth < 0:
        return f"{_TRUNCATED} depth"

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        return bounded_text(value, max_chars=max_string_chars, max_lines=max_lines)

    if isinstance(value, bytes):
        digest = hashlib.sha256(value).hexdigest()[:16]
        return f"[BYTES sha256:{digest} bytes:{len(value)}]"

    if isinstance(value, Path):
        return bounded_text(str(value), max_chars=max_string_chars, max_lines=max_lines)

    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            return bounded_text(str(value), max_chars=max_string_chars, max_lines=max_lines)

    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        items = list(value.items())
        for raw_key, raw_item in items[:max_collection_items]:
            key = str(raw_key)
            if _is_sensitive_key(key):
                sanitized[key] = _REDACTED
            else:
                sanitized[key] = sanitize_value(
                    raw_item,
                    max_string_chars=max_string_chars,
                    max_lines=max_lines,
                    max_collection_items=max_collection_items,
                    max_depth=max_depth - 1,
                )
        if len(items) > max_collection_items:
            sanitized["_truncated_items"] = len(items) - max_collection_items
        return sanitized

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        values = list(value)
        sanitized_items = [
            sanitize_value(
                item,
                max_string_chars=max_string_chars,
                max_lines=max_lines,
                max_collection_items=max_collection_items,
                max_depth=max_depth - 1,
            )
            for item in values[:max_collection_items]
        ]
        if len(values) > max_collection_items:
            sanitized_items.append({"_truncated_items": len(values) - max_collection_items})
        return sanitized_items

    return bounded_text(str(value), max_chars=max_string_chars, max_lines=max_lines)
