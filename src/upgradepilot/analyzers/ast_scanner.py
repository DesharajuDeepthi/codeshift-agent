"""
Deterministic Pydantic v1 compatibility scanner.

Strategy
--------
1. Parse the file with ast.parse (AST-first).
2. Collect import information in a single pre-pass.
3. Apply each rule's matcher kind via a dispatch table.
4. If ast.parse fails, fall back to bounded regex scanning at lower confidence.

Never executes analyzed code.
Never reads more than MAX_EVIDENCE_LINES of context per finding.
LangSmith tracing attaches only version metadata — no source code.
"""

from __future__ import annotations

import ast
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from upgradepilot.models.finding import MatchKind, MigrationFinding, ScanResult

if TYPE_CHECKING:
    from upgradepilot.migration.models import DetectionRule, LoadedMigrationPack

logger = logging.getLogger(__name__)

DETECTOR_NAME = "ast_scanner"
MAX_EVIDENCE_LINES = 8
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Import-tracking dataclass (populated in a single pre-pass)
# ---------------------------------------------------------------------------


@dataclass
class ImportInfo:
    """What pydantic names are in scope for a module."""

    # Names imported directly: `from pydantic import BaseModel, validator`
    pydantic_names: set[str] = field(default_factory=set)
    # `import pydantic` — the module is accessible as "pydantic"
    pydantic_module_imported: bool = False
    # `from pydantic.v1 import ...` — compat shim in use
    pydantic_v1_imported: bool = False
    # `from pydantic.dataclasses import ...` or `import pydantic.dataclasses`
    pydantic_dataclasses_imported: bool = False
    # `from pydantic import GenericModel`
    generic_model_imported: bool = False
    # `from pydantic.utils import GetterDict`
    getter_dict_imported: bool = False

    @property
    def any_pydantic(self) -> bool:
        return (
            bool(self.pydantic_names)
            or self.pydantic_module_imported
            or self.pydantic_v1_imported
            or self.pydantic_dataclasses_imported
            or self.generic_model_imported
            or self.getter_dict_imported
        )


def _collect_imports(tree: ast.Module) -> ImportInfo:
    info = ImportInfo()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "pydantic" or mod.startswith("pydantic."):
                for alias in node.names:
                    name = alias.asname or alias.name
                    info.pydantic_names.add(name)
                if mod.startswith("pydantic.v1"):
                    info.pydantic_v1_imported = True
                if mod == "pydantic.dataclasses" or mod.startswith("pydantic.dataclasses."):
                    info.pydantic_dataclasses_imported = True
                for alias in node.names:
                    if alias.name == "GenericModel":
                        info.generic_model_imported = True
                    if alias.name == "GetterDict":
                        info.getter_dict_imported = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pydantic":
                    info.pydantic_module_imported = True
                if alias.name == "pydantic.dataclasses" or alias.name.startswith(
                    "pydantic.dataclasses."
                ):
                    info.pydantic_dataclasses_imported = True
                if alias.name == "pydantic.v1" or alias.name.startswith("pydantic.v1."):
                    info.pydantic_v1_imported = True
    return info


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------


def _evidence(source_lines: list[str], lineno: int, end_lineno: int | None = None) -> str:
    """Return a bounded source excerpt around a line (1-based)."""
    start = lineno - 1
    stop = (end_lineno or lineno) - 1
    # Expand context slightly: up to MAX_EVIDENCE_LINES total
    extra = max(0, MAX_EVIDENCE_LINES - (stop - start + 1))
    ctx_before = min(extra // 2, 2)
    ctx_after = extra - ctx_before
    lo = max(0, start - ctx_before)
    hi = min(len(source_lines), stop + ctx_after + 1)
    return "".join(source_lines[lo:hi]).rstrip()


def _node_end_lineno(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    if isinstance(end, int):
        return end
    start = getattr(node, "lineno", 1)
    return int(start) if isinstance(start, int) else 1


# ---------------------------------------------------------------------------
# Finding factory
# ---------------------------------------------------------------------------


def _make_finding(
    rule: DetectionRule,
    pack: LoadedMigrationPack,
    file: str,
    line_start: int,
    line_end: int,
    evidence: str,
    symbol: str,
    confidence: float,
    match_kind: MatchKind,
) -> MigrationFinding:
    return MigrationFinding(
        finding_id=str(uuid.uuid4()),
        rule_id=rule.rule_id,
        pack_id=pack.metadata.pack_id,
        pack_version=pack.metadata.version,
        category=rule.category,
        severity=rule.severity,
        file=file,
        line_start=line_start,
        line_end=line_end,
        evidence=evidence,
        symbol=symbol,
        migration_concept=rule.migration_concept,
        source_ids=list(rule.source_ids),
        detector=DETECTOR_NAME,
        detector_version=pack.metadata.detector_version,
        confidence=confidence,
        match_kind=match_kind,
    )


# ---------------------------------------------------------------------------
# False-positive exclusion check
# ---------------------------------------------------------------------------


def _extra(rule: DetectionRule) -> dict[str, Any]:
    """Return matcher extra fields safely (model_extra may be None when no extras)."""
    return rule.matcher.model_extra or {}


def _is_excluded(rule: DetectionRule, evidence: str) -> bool:
    """Return True if any exclusion pattern matches the evidence snippet."""
    for excl in rule.false_positive_exclusions:
        pattern = excl.get("pattern", "")
        if pattern and pattern in evidence:
            return True
    return False


# ---------------------------------------------------------------------------
# Matcher-kind implementations
# ---------------------------------------------------------------------------


def _decorator_name(dec: ast.expr) -> str:
    """Extract the unqualified decorator name from a decorator node."""
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return ""


def _check_ast_decorator(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    extra = _extra(rule)
    names = set(extra.get("decorator_names", []))
    findings: list[MigrationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            dname = _decorator_name(dec)
            if dname not in names:
                continue
            # Verify the name was imported from pydantic
            if dname not in imports.pydantic_names and not imports.pydantic_module_imported:
                continue
            ev = _evidence(source_lines, dec.lineno, _node_end_lineno(dec))
            if _is_excluded(rule, ev):
                continue
            findings.append(
                _make_finding(
                    rule,
                    pack,
                    file,
                    dec.lineno,
                    _node_end_lineno(dec),
                    ev,
                    dname,
                    rule.confidence_ast,
                    MatchKind.AST,
                )
            )
    return findings


def _check_ast_classdef(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    """Find inner class Config inside a BaseModel subclass."""
    if not imports.any_pydantic:
        return []
    extra = _extra(rule)
    target_name: str = extra.get("name", "Config")
    parent_base: str = extra.get("parent_base", "BaseModel")

    findings: list[MigrationFinding] = []
    # Walk top-level and nested class definitions
    for outer in ast.walk(tree):
        if not isinstance(outer, ast.ClassDef):
            continue
        # Check if outer inherits from BaseModel (directly or via alias)
        base_names = {
            b.id if isinstance(b, ast.Name) else (b.attr if isinstance(b, ast.Attribute) else "")
            for b in outer.bases
        }
        if parent_base not in base_names and not (imports.pydantic_names & base_names):
            # Also accept if any imported pydantic name is a base
            # (handles `from pydantic import BaseModel as BM`)
            is_basemodel_sub = False
            for base in outer.bases:
                if isinstance(base, ast.Name) and base.id in imports.pydantic_names:
                    is_basemodel_sub = True
                    break
                if isinstance(base, ast.Attribute) and base.attr == parent_base:
                    is_basemodel_sub = True
                    break
            if not is_basemodel_sub:
                continue

        for inner in outer.body:
            if isinstance(inner, ast.ClassDef) and inner.name == target_name:
                ev = _evidence(source_lines, inner.lineno, _node_end_lineno(inner))
                if _is_excluded(rule, ev):
                    continue
                findings.append(
                    _make_finding(
                        rule,
                        pack,
                        file,
                        inner.lineno,
                        _node_end_lineno(inner),
                        ev,
                        f"class {target_name}",
                        rule.confidence_ast,
                        MatchKind.AST,
                    )
                )
    return findings


def _check_ast_attribute_assign(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    """Find attribute assignments like `orm_mode = True` inside a Config class."""
    if not imports.any_pydantic:
        return []
    extra = _extra(rule)
    attr_name: str = extra.get("attribute_name", "")
    context: str = extra.get("context", "Config")

    findings: list[MigrationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != context:
            continue
        for stmt in node.body:
            targets = []
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
            elif isinstance(stmt, ast.AnnAssign) and stmt.target is not None:
                targets = [stmt.target]
            for t in targets:
                tname = t.id if isinstance(t, ast.Name) else ""
                if tname == attr_name:
                    ev = _evidence(source_lines, stmt.lineno, _node_end_lineno(stmt))
                    if _is_excluded(rule, ev):
                        continue
                    findings.append(
                        _make_finding(
                            rule,
                            pack,
                            file,
                            stmt.lineno,
                            _node_end_lineno(stmt),
                            ev,
                            attr_name,
                            rule.confidence_ast,
                            MatchKind.AST,
                        )
                    )
    return findings


def _check_ast_method_call(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    """
    Find method-call patterns like `expr.dict()`, `expr.parse_obj(...)`, etc.

    Without type inference we cannot always confirm the receiver is a pydantic model.
    We only report findings when pydantic is present in the file, using the rule's
    confidence_ast value (which already accounts for this uncertainty).
    """
    if not imports.any_pydantic:
        return []
    extra = _extra(rule)
    method_name: str = extra.get("method_name", "")

    findings: list[MigrationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != method_name:
            continue
        # Exclude bare `dict()` calls (no receiver)
        ev = _evidence(source_lines, node.lineno, _node_end_lineno(node))
        if _is_excluded(rule, ev):
            continue
        findings.append(
            _make_finding(
                rule,
                pack,
                file,
                node.lineno,
                _node_end_lineno(node),
                ev,
                f".{method_name}()",
                rule.confidence_ast,
                MatchKind.AST,
            )
        )
    return findings


def _check_ast_call(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    """Find standalone function calls like `parse_obj_as(...)`."""
    extra = _extra(rule)
    function_name: str = extra.get("function_name", "")
    import_module: str = extra.get("import_module", "")

    findings: list[MigrationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        matched = False
        if isinstance(func, ast.Name) and func.id == function_name:
            # Direct name call — check it was imported from the right module
            if function_name in imports.pydantic_names or import_module == "pydantic":
                matched = True
        elif isinstance(func, ast.Attribute) and func.attr == function_name:
            matched = True
        if not matched:
            continue
        ev = _evidence(source_lines, node.lineno, _node_end_lineno(node))
        if _is_excluded(rule, ev):
            continue
        findings.append(
            _make_finding(
                rule,
                pack,
                file,
                node.lineno,
                _node_end_lineno(node),
                ev,
                function_name,
                rule.confidence_ast,
                MatchKind.AST,
            )
        )
    return findings


def _check_ast_attribute_access(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    """Find attribute access like `model.__fields__`."""
    if not imports.any_pydantic:
        return []
    extra = _extra(rule)
    attr_name: str = extra.get("attribute_name", "")

    findings: list[MigrationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr != attr_name:
            continue
        # Skip if the access is already an ast.Store (assignment target)
        if isinstance(node.ctx, ast.Store):
            continue
        ev = _evidence(source_lines, node.lineno, _node_end_lineno(node))
        if _is_excluded(rule, ev):
            continue
        findings.append(
            _make_finding(
                rule,
                pack,
                file,
                node.lineno,
                _node_end_lineno(node),
                ev,
                attr_name,
                rule.confidence_ast,
                MatchKind.AST,
            )
        )
    return findings


def _check_ast_import(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,  # noqa: ARG001 — unused but kept for uniform signature
) -> list[MigrationFinding]:
    """
    Find import patterns:
    - `from pydantic import GenericModel`
    - `import pydantic.dataclasses`
    - `from pydantic.v1 import ...`
    - `from pydantic.utils import GetterDict`
    """
    extra = _extra(rule)
    module: str = extra.get("module", "")
    name: str = extra.get("name", "")
    module_prefix: str = extra.get("module_prefix", "")

    findings: list[MigrationFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ImportFrom, ast.Import)):
            continue
        symbol = ""
        lineno: int = node.lineno
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            # module_prefix match (e.g. pydantic.v1)
            if module_prefix and (mod == module_prefix or mod.startswith(module_prefix + ".")):
                symbol = f"from {mod} import ..."
            # exact module + optional name match
            elif module and mod == module:
                if name:
                    for alias in node.names:
                        if alias.name == name:
                            symbol = f"from {mod} import {name}"
                            break
                else:
                    symbol = f"from {mod} import ..."
        elif isinstance(node, ast.Import):
            for alias in node.names:
                n = alias.name
                if module_prefix and (n == module_prefix or n.startswith(module_prefix + ".")):
                    symbol = f"import {n}"
                    break
                if module and n == module:
                    symbol = f"import {n}"
                    break
        if not symbol:
            continue
        ev = _evidence(source_lines, lineno)
        if _is_excluded(rule, ev):
            continue
        findings.append(
            _make_finding(
                rule,
                pack,
                file,
                lineno,
                lineno,
                ev,
                symbol,
                rule.confidence_ast,
                MatchKind.AST,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_MATCHER_DISPATCH = {
    "ast_decorator": _check_ast_decorator,
    "ast_classdef": _check_ast_classdef,
    "ast_attribute_assign": _check_ast_attribute_assign,
    "ast_method_call": _check_ast_method_call,
    "ast_call": _check_ast_call,
    "ast_attribute_access": _check_ast_attribute_access,
    "ast_import": _check_ast_import,
}


def _apply_rule_ast(
    rule: DetectionRule,
    tree: ast.Module,
    source_lines: list[str],
    file: str,
    pack: LoadedMigrationPack,
    imports: ImportInfo,
) -> list[MigrationFinding]:
    handler = _MATCHER_DISPATCH.get(rule.matcher.kind)
    if handler is None:
        logger.debug("No handler for matcher kind %r (rule %s)", rule.matcher.kind, rule.rule_id)
        return []
    return handler(rule, tree, source_lines, file, pack, imports)


# ---------------------------------------------------------------------------
# Text fallback (used when AST parse fails)
# ---------------------------------------------------------------------------

_TEXT_PATTERNS: dict[str, re.Pattern[str]] = {
    "PYD001": re.compile(r"@\s*validator\b"),
    "PYD002": re.compile(r"@\s*root_validator\b"),
    "PYD003": re.compile(r"class\s+Config\s*[:(]"),
    "PYD004": re.compile(r"\borm_mode\s*="),
    "PYD005": re.compile(r"\ballow_population_by_field_name\s*="),
    "PYD006": re.compile(r"\bvalidate_all\s*="),
    "PYD007": re.compile(r"\bsmart_union\s*="),
    "PYD008": re.compile(r"\bjson_encoders\s*="),
    "PYD009": re.compile(r"\.\s*dict\s*\("),
    "PYD010": re.compile(r"\.\s*json\s*\("),
    "PYD011": re.compile(r"\.\s*copy\s*\("),
    "PYD012": re.compile(r"\.\s*parse_obj\s*\("),
    "PYD013": re.compile(r"\.\s*parse_raw\s*\("),
    "PYD014": re.compile(r"\bparse_obj_as\s*\("),
    "PYD015": re.compile(r"\.\s*from_orm\s*\("),
    "PYD016": re.compile(r"\.\s*schema\s*\("),
    "PYD017": re.compile(r"\.\s*schema_json\s*\("),
    "PYD018": re.compile(r"\.__fields__\b"),
    "PYD019": re.compile(r"\bGenericModel\b"),
    "PYD020": re.compile(r"pydantic\.dataclasses"),
    "PYD021": re.compile(r"pydantic\.v1"),
    "PYD022": re.compile(r"\bGetterDict\b"),
}

_PYDANTIC_IMPORT_RE = re.compile(r"^\s*(import pydantic|from pydantic)")


def _scan_file_text(
    source: str,
    file: str,
    pack: LoadedMigrationPack,
) -> list[MigrationFinding]:
    """Regex-based fallback scanner for files that fail AST parsing."""
    lines = source.splitlines(keepends=True)
    has_pydantic = any(_PYDANTIC_IMPORT_RE.match(ln) for ln in lines)
    if not has_pydantic:
        return []

    findings: list[MigrationFinding] = []
    for rule in pack.detection_rules.rules:
        pat = _TEXT_PATTERNS.get(rule.rule_id)
        if pat is None:
            continue
        for i, line in enumerate(lines, start=1):
            if pat.search(line):
                ev = _evidence(lines, i)
                if _is_excluded(rule, ev):
                    continue
                findings.append(
                    _make_finding(
                        rule,
                        pack,
                        file,
                        i,
                        i,
                        ev,
                        pat.pattern,
                        rule.confidence_text,
                        MatchKind.TEXT,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_file(
    source: str,
    rel_path: str,
    pack: LoadedMigrationPack,
) -> tuple[list[MigrationFinding], bool]:
    """
    Scan one file and return (findings, syntax_ok).

    Uses AST when the file parses cleanly; falls back to text scanning otherwise.
    rel_path should be forward-slash-normalized and repository-relative.
    Never sends source code to external services.
    """
    try:
        tree = ast.parse(source, filename=rel_path, type_comments=False)
    except SyntaxError:
        logger.debug("Syntax error in %s — using text fallback", rel_path)
        return _scan_file_text(source, rel_path, pack), False

    source_lines = source.splitlines(keepends=True)
    imports = _collect_imports(tree)

    findings: list[MigrationFinding] = []
    for rule in pack.detection_rules.rules:
        findings.extend(_apply_rule_ast(rule, tree, source_lines, rel_path, pack, imports))
    return findings, True


class PythonASTAnalyzer:
    """
    LanguageAnalyzer implementation for Python using AST-first analysis.

    Delegates to scan_workspace() below.  Registered in analyzers/registry.py
    under the "python-ast" kind.
    """

    @property
    def analyzer_kind(self) -> str:
        return "python-ast"

    def scan(self, workspace: Path, pack: LoadedMigrationPack) -> ScanResult:
        return scan_workspace(workspace, pack)


def scan_workspace(
    workspace: Path,
    pack: LoadedMigrationPack,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> ScanResult:
    """
    Scan all Python files under workspace.

    Skips excluded directories (handled by _is_excluded_dir from profiler).
    Logs only file counts and rule match counts — never raw source.
    """
    from upgradepilot.analyzers.repository_profiler import _is_excluded_dir  # local import

    t0 = time.monotonic()
    all_findings: list[MigrationFinding] = []
    syntax_error_files: list[str] = []
    scanned = 0
    files_with_findings: set[str] = set()

    for py_file in sorted(workspace.rglob("*.py")):
        # Skip excluded directories
        if _is_excluded_dir(py_file.parent, workspace):
            continue
        # Skip oversized files
        try:
            size = py_file.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            logger.debug("Skipping oversized file: %s (%d bytes)", py_file, size)
            continue

        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Could not read %s: %s", py_file, exc)
            continue

        rel = py_file.relative_to(workspace).as_posix()
        file_findings, syntax_ok = scan_file(source, rel, pack)
        scanned += 1
        if not syntax_ok:
            syntax_error_files.append(rel)
        if file_findings:
            all_findings.extend(file_findings)
            files_with_findings.add(rel)

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "Scan complete: %d files, %d findings, %.0f ms",
        scanned,
        len(all_findings),
        elapsed_ms,
    )
    return ScanResult(
        findings=all_findings,
        scanned_files=scanned,
        files_with_findings=len(files_with_findings),
        syntax_error_files=syntax_error_files,
        detector=DETECTOR_NAME,
        detector_version=pack.metadata.detector_version,
    )
