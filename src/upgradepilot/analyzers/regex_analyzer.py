"""
Language-agnostic regex-based analyzer.

Strategy
--------
For each detection rule whose matcher kind is one of the regex-compatible kinds
(ast_import, ast_attribute_access, or any kind the rule declares a `pattern`
for), scan source files line by line using compiled regular expressions.

This analyzer works for any text-based language.  It is the fallback for packs
that do not have (or do not need) a language-specific AST analyzer.

Limitations compared to PythonASTAnalyzer:
- No import-scope narrowing — patterns are applied to all files.
- Confidence values are taken from the rule's confidence_text field.
- No AST-level false-positive suppression.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from upgradepilot.analyzers.base import ANALYZER_KIND_REGEX
from upgradepilot.models.finding import MatchKind, MigrationFinding, ScanResult

if TYPE_CHECKING:
    from upgradepilot.migration.models import DetectionRule, LoadedMigrationPack

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_EVIDENCE_LINES = 8

_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", "env",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "node_modules", "dist", "build", ".next", ".nuxt", "target",
        "vendor", "third_party", "generated", "gen",
    }
)


class RegexAnalyzer:
    """Language-agnostic regex-based LanguageAnalyzer implementation."""

    @property
    def analyzer_kind(self) -> str:
        return ANALYZER_KIND_REGEX

    def scan(self, workspace: Path, pack: LoadedMigrationPack) -> ScanResult:
        findings: list[MigrationFinding] = []
        files_scanned = 0
        files_skipped = 0
        errors: list[dict[str, Any]] = []

        # Determine which file extensions to scan from pack metadata.
        # Falls back to scanning all text files if the pack doesn't declare extensions.
        target_extensions = _extensions_for_language(pack.metadata.language)

        compiled: list[tuple[DetectionRule, re.Pattern[str]]] = []
        for rule in pack.detection_rules.rules:
            pattern_str = _pattern_from_rule(rule)
            if not pattern_str:
                continue
            try:
                compiled.append((rule, re.compile(pattern_str, re.MULTILINE | re.IGNORECASE)))
            except re.error as exc:
                logger.warning("Rule %s: invalid regex %r — %s", rule.rule_id, pattern_str, exc)

        for file_path in _iter_source_files(workspace, target_extensions):
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    files_skipped += 1
                    continue
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append({"file": str(file_path), "error": str(exc)})
                files_skipped += 1
                continue

            rel = file_path.relative_to(workspace).as_posix()
            lines = content.splitlines()
            files_scanned += 1

            for rule, pattern in compiled:
                for match in pattern.finditer(content):
                    line_no = content[: match.start()].count("\n") + 1
                    evidence_start = max(0, line_no - 2)
                    evidence_end = min(len(lines), line_no + MAX_EVIDENCE_LINES - 1)
                    snippet = "\n".join(lines[evidence_start:evidence_end])

                    findings.append(
                        MigrationFinding(
                            rule_id=rule.rule_id,
                            pack_id=pack.metadata.pack_id,
                            pack_version=pack.metadata.version,
                            category=str(rule.category),
                            severity=str(rule.severity),
                            file=rel,
                            line_start=line_no,
                            line_end=line_no,
                            evidence=snippet,
                            symbol=match.group(0)[:120],
                            migration_concept=rule.migration_concept,
                            source_ids=list(rule.source_ids),
                            detector=ANALYZER_KIND_REGEX,
                            detector_version="1.0.0",
                            confidence=rule.confidence_text,
                            match_kind=MatchKind.TEXT,
                        )
                    )

        return ScanResult(
            findings=findings,
            scanned_files=files_scanned,
            files_with_findings=len({f.file for f in findings}),
            syntax_error_files=[str(e.get("file", "")) for e in errors],
            detector=ANALYZER_KIND_REGEX,
            detector_version="1.0.0",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pattern_from_rule(rule: DetectionRule) -> str | None:
    """Extract a regex pattern string from a detection rule's matcher spec."""
    matcher = rule.matcher
    extra = matcher.model_extra or {}

    if hasattr(matcher, "pattern") or "pattern" in extra:
        return extra.get("pattern") or getattr(matcher, "pattern", None)

    kind = matcher.kind
    if kind == "ast_import":
        module = extra.get("module", "")
        symbols = extra.get("symbols", [])
        if symbols:
            sym_re = "|".join(re.escape(s) for s in symbols)
            return rf"(?:from\s+{re.escape(module)}\s+import\s+(?:[^;]*?\b(?:{sym_re})\b))"
        return rf"\b{re.escape(module)}\b"

    if kind in ("ast_attribute_access", "ast_attribute_assign"):
        obj = extra.get("object", "")
        attr = extra.get("attribute", "")
        if obj and attr:
            return rf"\b{re.escape(obj)}\.{re.escape(attr)}\b"

    return None


def _extensions_for_language(language: str) -> frozenset[str]:
    """Return the file extensions to scan for a given language."""
    _MAP: dict[str, frozenset[str]] = {
        "python": frozenset({".py", ".pyi"}),
        "typescript": frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}),
        "javascript": frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}),
        "go": frozenset({".go"}),
        "rust": frozenset({".rs"}),
        "java": frozenset({".java"}),
        "kotlin": frozenset({".kt", ".kts"}),
        "ruby": frozenset({".rb"}),
        "php": frozenset({".php"}),
        "csharp": frozenset({".cs"}),
    }
    return _MAP.get(language.lower(), frozenset())


def _iter_source_files(workspace: Path, extensions: frozenset[str]) -> list[Path]:
    """Yield source files in workspace matching the given extensions."""
    results: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        # Skip excluded directories
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if not extensions or path.suffix in extensions:
            results.append(path)
    return results
