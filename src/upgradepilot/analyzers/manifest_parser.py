"""
Manifest file parsers for requirements.txt, PEP 621 pyproject.toml, and Poetry.

Design principles:
- Pure, deterministic, no I/O (callers pass file contents as strings)
- Never run pip/poetry/uv to resolve versions
- Classify version constraints without inferring installed versions
- Capture parse errors as typed values; never raise on malformed input
- Record the parser name and version on every emitted evidence item
"""

from __future__ import annotations

import re
from typing import Any

from upgradepilot.models.profile import (
    ConstraintKind,
    DependencyEvidence,
    VersionConstraint,
)

PARSER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Normalisation helpers (PEP 503)
# ---------------------------------------------------------------------------

_NORM_RE = re.compile(r"[-_.]+")


def _normalize(name: str) -> str:
    return _NORM_RE.sub("-", name).lower()


# ---------------------------------------------------------------------------
# Version constraint classification
# ---------------------------------------------------------------------------

_EXACT_RE = re.compile(r"^==\s*[\w.*+!]+$")
_RANGE_RE = re.compile(r"[<>~^]")


def _classify_constraint(specifier: str) -> VersionConstraint:
    s = specifier.strip()
    if not s:
        return VersionConstraint(raw=s, kind=ConstraintKind.UNPINNED)
    if _EXACT_RE.match(s):
        version = re.sub(r"^==\s*", "", s)
        return VersionConstraint(raw=s, kind=ConstraintKind.EXACT, lower=version, upper=version)
    if "," in s:
        # Multiple specifiers — bounded range
        lower = upper = None
        for part in s.split(","):
            p = part.strip()
            if p.startswith(">="):
                lower = p[2:].strip()
            elif p.startswith("<="):
                upper = p[2:].strip()
            elif p.startswith(">"):
                lower = p[1:].strip()
            elif p.startswith("<"):
                upper = p[1:].strip()
        return VersionConstraint(raw=s, kind=ConstraintKind.BOUNDED, lower=lower, upper=upper)
    if s.startswith("~="):
        lower = s[2:].strip()
        return VersionConstraint(raw=s, kind=ConstraintKind.BOUNDED, lower=lower)
    if _RANGE_RE.search(s):
        return VersionConstraint(raw=s, kind=ConstraintKind.RANGE)
    if re.match(r"^!=", s):
        return VersionConstraint(raw=s, kind=ConstraintKind.AMBIGUOUS)
    return VersionConstraint(raw=s, kind=ConstraintKind.UNKNOWN)


# ---------------------------------------------------------------------------
# requirements.txt parser
# ---------------------------------------------------------------------------

# PEP 508 package name pattern (simplified)
_REQ_NAME_RE = re.compile(r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(.*)")
# Options to skip
_SKIP_PREFIXES = ("-r ", "-c ", "-e ", "--", "#", "http://", "https://", "git+", ".")


def parse_requirements_txt(
    content: str,
    manifest_path: str,
) -> tuple[list[DependencyEvidence], list[str]]:
    """
    Parse a requirements.txt file.

    Returns (evidence_list, error_list).
    Handles:
    - version specifiers
    - inline comments
    - line continuations
    - extras [extra1,extra2]
    - environment markers (ignored; package name still extracted)
    - blank lines and comment-only lines
    """
    evidence: list[DependencyEvidence] = []
    errors: list[str] = []

    # Merge line continuations
    merged_lines: list[tuple[int, str]] = []
    buf = ""
    start_line = 0
    for i, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            if not buf:
                start_line = i
            buf += stripped[:-1]
        else:
            full = (buf + stripped).strip()
            lineno = start_line if buf else i
            buf = ""
            start_line = 0
            merged_lines.append((lineno, full))

    for lineno, line in merged_lines:
        # Strip inline comment
        if "#" in line:
            line = line[: line.index("#")].strip()
        if not line:
            continue
        # Skip options/URLs/editable installs
        if any(line.startswith(p) for p in _SKIP_PREFIXES):
            continue

        # Strip environment marker
        if ";" in line:
            line = line[: line.index(";")].strip()

        # Strip extras and specifiers
        m = _REQ_NAME_RE.match(line)
        if not m:
            errors.append(f"line {lineno}: could not parse package name from {line!r}")
            continue

        package = m.group(1)
        rest = m.group(3).strip()

        # Strip extras [...]
        rest = re.sub(r"\[.*?\]", "", rest).strip()

        constraint = _classify_constraint(rest)
        evidence.append(
            DependencyEvidence(
                package=package,
                normalized_name=_normalize(package),
                constraint=constraint,
                manifest_path=manifest_path,
                line=lineno,
                parser="requirements_txt",
                parser_version=PARSER_VERSION,
                confidence=0.95,
            )
        )

    return evidence, errors


# ---------------------------------------------------------------------------
# pyproject.toml parser
# ---------------------------------------------------------------------------


def _parse_toml_safe(content: str) -> tuple[dict[str, Any], str | None]:
    """Parse TOML; return (data, error_message)."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef]
        except ImportError:
            return {}, "tomllib/tomli not available"
    try:
        data = tomllib.loads(content)
        return data, None
    except Exception as exc:
        return {}, str(exc)


def parse_pyproject_toml(
    content: str,
    manifest_path: str,
) -> tuple[list[DependencyEvidence], list[str], list[str]]:
    """
    Parse a pyproject.toml file (PEP 621 and Poetry).

    Returns (evidence_list, error_list, runtime_declarations).
    Handles:
    - [project].dependencies (PEP 621)
    - [project].optional-dependencies (PEP 621 extras)
    - [tool.poetry.dependencies]
    - [tool.poetry.dev-dependencies]
    - [tool.poetry.group.*.dependencies]
    - python_requires / requires-python → runtime declarations
    """
    evidence: list[DependencyEvidence] = []
    errors: list[str] = []
    runtime_decls: list[str] = []

    data, parse_error = _parse_toml_safe(content)
    if parse_error:
        errors.append(f"TOML parse error: {parse_error}")
        return evidence, errors, runtime_decls

    # --- PEP 621 ---
    project = data.get("project", {})
    if project:
        # requires-python
        requires_python = project.get("requires-python")
        if requires_python:
            runtime_decls.append(f"requires-python: {requires_python}")

        for dep_str in project.get("dependencies", []):
            ev, err = _parse_pep508(dep_str, manifest_path, "pyproject_pep621")
            if ev:
                evidence.append(ev)
            if err:
                errors.append(err)

        for group_deps in project.get("optional-dependencies", {}).values():
            for dep_str in group_deps:
                ev, err = _parse_pep508(dep_str, manifest_path, "pyproject_pep621_optional")
                if ev:
                    evidence.append(ev)
                if err:
                    errors.append(err)

    # --- Poetry ---
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {})
    if poetry:
        # Poetry python constraint
        poetry_deps = poetry.get("dependencies", {})
        python_constraint = poetry_deps.get("python")
        if python_constraint:
            runtime_decls.append(f"poetry-python: {python_constraint}")

        for section_name, deps in _collect_poetry_sections(poetry):
            for pkg, spec in deps.items():
                if pkg.lower() == "python":
                    continue
                ev = _parse_poetry_dep(pkg, spec, manifest_path, section_name)
                if ev:
                    evidence.append(ev)

    return evidence, errors, runtime_decls


def _collect_poetry_sections(
    poetry: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Yield (section_name, {pkg: spec}) for all Poetry dependency sections."""
    sections: list[tuple[str, dict[str, Any]]] = []
    for key in ("dependencies", "dev-dependencies"):
        val = poetry.get(key)
        if isinstance(val, dict):
            sections.append((f"poetry_{key}", val))
    # [tool.poetry.group.*.dependencies]
    for group_name, group_data in poetry.get("group", {}).items():
        deps = group_data.get("dependencies", {})
        if isinstance(deps, dict):
            sections.append((f"poetry_group_{group_name}", deps))
    return sections


def _parse_pep508(
    dep_str: str,
    manifest_path: str,
    parser_name: str,
) -> tuple[DependencyEvidence | None, str | None]:
    """Parse a single PEP 508 dependency string."""
    if not dep_str or not dep_str.strip():
        return None, None
    dep_str = dep_str.strip()
    # Strip environment marker
    if ";" in dep_str:
        dep_str = dep_str[: dep_str.index(";")].strip()
    m = _REQ_NAME_RE.match(dep_str)
    if not m:
        return None, f"could not parse PEP 508 dep: {dep_str!r}"
    package = m.group(1)
    rest = re.sub(r"\[.*?\]", "", m.group(3)).strip()
    constraint = _classify_constraint(rest)
    return (
        DependencyEvidence(
            package=package,
            normalized_name=_normalize(package),
            constraint=constraint,
            manifest_path=manifest_path,
            line=0,
            parser=parser_name,
            parser_version=PARSER_VERSION,
            confidence=0.9,
        ),
        None,
    )


def _parse_poetry_dep(
    package: str,
    spec: object,
    manifest_path: str,
    section: str,
) -> DependencyEvidence | None:
    """Parse a Poetry dependency entry (string or dict form)."""
    if isinstance(spec, str):
        raw = spec
    elif isinstance(spec, dict):
        raw = spec.get("version", "")
        if not isinstance(raw, str):
            raw = ""
    else:
        raw = ""

    # Poetry uses ^ and ~ prefixes
    if raw == "*":
        constraint = VersionConstraint(raw=raw, kind=ConstraintKind.UNPINNED)
    else:
        constraint = _classify_constraint(raw)

    return DependencyEvidence(
        package=package,
        normalized_name=_normalize(package),
        constraint=constraint,
        manifest_path=manifest_path,
        line=0,
        parser=section,
        parser_version=PARSER_VERSION,
        confidence=0.9,
    )
