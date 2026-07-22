"""
Analyzer registry — maps analyzer_kind strings to LanguageAnalyzer implementations.

Usage
-----
    from upgradepilot.analyzers.registry import get_analyzer

    analyzer = get_analyzer("python-ast")
    result = analyzer.scan(workspace, pack)

Registration
------------
Built-in analyzers are registered at import time.  Third-party analyzers can
call register_analyzer() before graph startup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from upgradepilot.analyzers.base import (
    ANALYZER_KIND_PYTHON_AST,
    ANALYZER_KIND_REGEX,
    LanguageAnalyzer,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type[LanguageAnalyzer]] = {}


def register_analyzer(kind: str, impl: type[LanguageAnalyzer]) -> None:
    """Register a LanguageAnalyzer implementation for a given kind string."""
    if kind in _REGISTRY:
        logger.warning("Overwriting existing analyzer for kind %r", kind)
    _REGISTRY[kind] = impl
    logger.debug("Registered analyzer %r → %s", kind, impl.__name__)


def get_analyzer(analyzer_kind: str) -> LanguageAnalyzer:
    """
    Return an instance of the registered analyzer for analyzer_kind.

    Raises
    ------
    KeyError
        If no analyzer has been registered for that kind.
    """
    if analyzer_kind not in _REGISTRY:
        available = sorted(_REGISTRY.keys())
        raise KeyError(
            f"No analyzer registered for kind {analyzer_kind!r}. Available kinds: {available}"
        )
    return _REGISTRY[analyzer_kind]()


def list_registered_kinds() -> list[str]:
    """Return all currently registered analyzer kind strings."""
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Built-in registration (deferred to avoid circular imports)
# ---------------------------------------------------------------------------


def _register_defaults() -> None:
    from upgradepilot.analyzers.ast_scanner import PythonASTAnalyzer
    from upgradepilot.analyzers.regex_analyzer import RegexAnalyzer

    register_analyzer(ANALYZER_KIND_PYTHON_AST, PythonASTAnalyzer)
    register_analyzer(ANALYZER_KIND_REGEX, RegexAnalyzer)


_register_defaults()
