"""
Deterministic repository profiler for Milestone 2.

Walks an extracted workspace and produces a RepositoryProfile.
Never executes repository code. Never calls package managers.
Captures syntax errors without failing the overall analysis.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from upgradepilot.analyzers.manifest_parser import (
    parse_pyproject_toml,
    parse_requirements_txt,
)
from upgradepilot.models.profile import (
    ApplicabilitySignals,
    CISystem,
    DependencyEvidence,
    ManifestFile,
    PydanticSignal,
    RepositoryProfile,
    SyntaxError_,
    TestingFramework,
    TestProfile,
)

logger = logging.getLogger(__name__)

PROFILER_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Multi-language extension map
# ---------------------------------------------------------------------------

_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".scala": "scala",
    ".clj": "clojure",
    ".ex": "elixir",
    ".exs": "elixir",
}

# ---------------------------------------------------------------------------
# Directory exclusion patterns
# Paths matching any of these are skipped entirely.
# ---------------------------------------------------------------------------

_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        "*.egg-info",
        ".eggs",
        "htmlcov",
        ".coverage",
        "site-packages",
        # common vendored directories
        "vendor",
        "third_party",
        "third-party",
        "extern",
        "external",
        # generated
        "generated",
        "gen",
        "_generated",
        "proto",
        "protobuf",
    }
)

# Glob-style patterns (simple suffix matches)
_EXCLUDED_DIR_SUFFIXES = (".egg-info",)

# ---------------------------------------------------------------------------
# File-name patterns
# ---------------------------------------------------------------------------

_MANIFEST_NAMES = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "requirements_dev.txt",
        "requirements-test.txt",
        "requirements_test.txt",
        "requirements-prod.txt",
        "requirements_prod.txt",
        "dev-requirements.txt",
        "test-requirements.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
    }
)

# Requirements files matching this pattern (requirements*.txt)
_REQUIREMENTS_RE = re.compile(r"requirements.*\.txt$", re.IGNORECASE)

_CI_FILES_RE = re.compile(
    r"(\.github/workflows/.*\.ya?ml"
    r"|tox\.ini"
    r"|noxfile\.py"
    r"|\.travis\.yml"
    r"|\.circleci/config\.yml"
    r"|Jenkinsfile"
    r"|azure-pipelines\.yml"
    r"|\.gitlab-ci\.yml)$",
    re.IGNORECASE,
)

_DOCKERFILE_RE = re.compile(
    r"(^|/)Dockerfile(\.[a-z0-9]+)?$",
    re.IGNORECASE,
)

_PACKAGING_FILES = frozenset({"MANIFEST.in", "PKG-INFO", "WHEEL", "METADATA", "RECORD"})

_TEST_FILE_RE = re.compile(r"(^|/)test_[^/]+\.py$|/tests?/[^/]*\.py$", re.IGNORECASE)

_PYTHON_RUNTIME_FILES = frozenset({".python-version", ".tool-versions"})

# Pydantic package names (normalized)
_PYDANTIC_NAMES = frozenset({"pydantic", "pydantic-settings", "pydantic-extra-types"})


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _is_excluded_dir(dir_path: Path, workspace: Path) -> bool:
    """Return True if any component of dir_path matches exclusion rules."""
    try:
        relative = dir_path.relative_to(workspace)
    except ValueError:
        return False
    for part in relative.parts:
        if part in _EXCLUDED_DIR_NAMES:
            return True
        if any(part.endswith(sfx) for sfx in _EXCLUDED_DIR_SUFFIXES):
            return True
    return False


def _rel_posix(path: Path, workspace: Path) -> str:
    """Return a POSIX relative path string."""
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Source-root detection
# ---------------------------------------------------------------------------


def _detect_source_roots(python_files: list[str]) -> list[str]:
    """
    Heuristic source-root detection.

    A directory is a likely source root if:
    - it contains an __init__.py, or
    - it is 'src/' and contains subdirectories with __init__.py, or
    - it appears to be the top-level package directory.
    """
    dirs: set[str] = set()
    for f in python_files:
        p = Path(f)
        parts = p.parts
        # Top-level .py files → root is ""
        if len(parts) == 1:
            dirs.add(".")
        else:
            parent = str(p.parent)
            dirs.add(parent)

    # Prefer 'src' layout if present
    src_roots: list[str] = []
    other_roots: list[str] = []
    for d in sorted(dirs):
        if d.startswith("src/") or d == "src":
            src_roots.append(d)
        else:
            other_roots.append(d)

    if src_roots:
        # Return the src/ packages
        nested = {p.split("/")[0] for p in src_roots if "/" in p}
        top_src = {"src"} if "src" in src_roots else set()
        top = sorted(nested | top_src)
        return list(top)

    # Find directories that look like top-level packages (contain __init__.py ref)
    init_dirs = {str(Path(f).parent) for f in python_files if Path(f).name == "__init__.py"}
    top_level = {d.split("/")[0] for d in init_dirs if d != "."}
    if top_level:
        return sorted(top_level)

    return ["."]


# ---------------------------------------------------------------------------
# Pydantic applicability signals
# ---------------------------------------------------------------------------


_V1_ONLY_PATTERNS = re.compile(
    r"(from\s+pydantic\s+import.*\bvalidator\b"
    r"|from\s+pydantic\s+import.*\broot_validator\b"
    r"|\bclass\s+Config\s*:"
    r"|\border_fields\s*="
    r"|\borm_mode\s*=\s*True)",
    re.MULTILINE,
)

_V2_ONLY_PATTERNS = re.compile(
    r"(from\s+pydantic\s+import.*\bfield_validator\b"
    r"|from\s+pydantic\s+import.*\bmodel_validator\b"
    r"|\bmodel_config\s*=)",
    re.MULTILINE,
)

_PYDANTIC_IMPORT_RE = re.compile(
    r"(import\s+pydantic|from\s+pydantic)",
    re.MULTILINE,
)


def _detect_pydantic_signal(
    pydantic_deps: list[DependencyEvidence],
    has_pydantic_imports: bool,
) -> PydanticSignal:
    """Classify the Pydantic signal from dependency evidence."""
    if not pydantic_deps:
        return PydanticSignal.NOT_FOUND

    from upgradepilot.models.profile import ConstraintKind

    for dep in pydantic_deps:
        if dep.normalized_name != "pydantic":
            continue
        kind = dep.constraint.kind
        raw = dep.constraint.raw.strip()

        if kind == ConstraintKind.EXACT:
            lower = dep.constraint.lower or ""
            if lower.startswith("1.") or lower.startswith("0."):
                return PydanticSignal.V1_DETECTED
            if lower.startswith("2."):
                return PydanticSignal.V2_DETECTED
            return PydanticSignal.AMBIGUOUS

        if kind == ConstraintKind.BOUNDED:
            lower = dep.constraint.lower or ""
            upper = dep.constraint.upper or ""
            if upper.startswith("2"):
                # upper <2 means v1
                return PydanticSignal.V1_DETECTED
            if lower.startswith("2"):
                return PydanticSignal.V2_DETECTED
            if lower.startswith("1"):
                if upper.startswith("3"):
                    return PydanticSignal.AMBIGUOUS
                return PydanticSignal.V1_DETECTED
            return PydanticSignal.AMBIGUOUS

        if kind == ConstraintKind.RANGE:
            # e.g. ~=1.x, >=1 etc.
            if re.search(r"[~^]?=?1\.", raw):
                return PydanticSignal.V1_DETECTED
            if re.search(r"[~^]?=?2\.", raw):
                return PydanticSignal.V2_DETECTED
            return PydanticSignal.AMBIGUOUS

        if kind == ConstraintKind.UNPINNED:
            return PydanticSignal.UNPINNED

    return PydanticSignal.AMBIGUOUS


# ---------------------------------------------------------------------------
# Main profiler
# ---------------------------------------------------------------------------


def profile_repository(workspace: Path) -> RepositoryProfile:
    """
    Walk the workspace and build a RepositoryProfile.

    All errors are captured; this function should never raise.
    """
    python_files: list[str] = []
    manifest_files: list[ManifestFile] = []
    all_deps: list[DependencyEvidence] = []
    runtime_decls: list[str] = []
    test_files: list[str] = []
    ci_files: list[str] = []
    docker_files: list[str] = []
    packaging_files: list[str] = []
    excluded_paths: list[str] = []
    syntax_errors: list[SyntaxError_] = []
    has_pydantic_imports = False
    # Multi-language tracking
    source_files_by_language: dict[str, list[str]] = {}

    ci_systems: set[CISystem] = set()
    test_frameworks: set[TestingFramework] = set()
    test_config_files: list[str] = []

    for path in sorted(workspace.rglob("*")):
        if path.is_dir():
            if _is_excluded_dir(path, workspace):
                excluded_paths.append(_rel_posix(path, workspace))
            continue

        if not path.is_file():
            continue

        # Skip files inside excluded directories
        if any(_is_excluded_dir(path.parent, workspace) for _ in [None]):
            excluded_paths.append(_rel_posix(path, workspace))
            continue

        # Check if any parent directory is excluded
        excluded = False
        for parent in path.parents:
            if parent == workspace:
                break
            if _is_excluded_dir(parent, workspace):
                excluded = True
                break
        if excluded:
            excluded_paths.append(_rel_posix(path, workspace))
            continue

        rel = _rel_posix(path, workspace)
        name = path.name

        # --- Multi-language source file tracking ---
        lang = _EXT_TO_LANGUAGE.get(path.suffix)
        if lang:
            source_files_by_language.setdefault(lang, []).append(rel)

        # --- Python files ---
        if path.suffix == ".py":
            python_files.append(rel)
            # Check for test file
            if _TEST_FILE_RE.search("/" + rel):
                test_files.append(rel)
                test_frameworks.add(TestingFramework.PYTEST)
            # Detect Pydantic imports (quick text scan before full AST)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if _PYDANTIC_IMPORT_RE.search(text):
                    has_pydantic_imports = True
                # Check for pytest usage
                if "import pytest" in text or "from pytest" in text:
                    test_frameworks.add(TestingFramework.PYTEST)
                if "import unittest" in text or "from unittest" in text:
                    test_frameworks.add(TestingFramework.UNITTEST)
                # Validate syntax (capture error without failing)
                try:
                    ast.parse(text, filename=rel)
                except SyntaxError as se:
                    syntax_errors.append(
                        SyntaxError_(
                            path=rel,
                            line=se.lineno,
                            col=se.offset,
                            message=str(se.msg),
                        )
                    )
            except OSError:
                pass

        # --- Manifest files ---
        if name in _MANIFEST_NAMES or _REQUIREMENTS_RE.match(name):
            errors: list[str] = []
            parse_error: str | None = None
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if name == "pyproject.toml":
                    deps, errors, rt = parse_pyproject_toml(text, rel)
                    all_deps.extend(deps)
                    runtime_decls.extend(rt)
                    parse_error = "; ".join(errors) if errors else None
                    # Check for tox/nox config inside pyproject.toml
                    if "[tool.tox]" in text or "[tox]" in text:
                        ci_systems.add(CISystem.TOX)
                        test_config_files.append(rel)
                    if "[tool.nox]" in text:
                        ci_systems.add(CISystem.NOX)
                elif _REQUIREMENTS_RE.match(name):
                    deps, errors = parse_requirements_txt(text, rel)
                    all_deps.extend(deps)
                    parse_error = "; ".join(errors) if errors else None
                # setup.py / setup.cfg noted but not parsed (complex; M4 scope)
            except OSError as exc:
                parse_error = str(exc)
            manifest_files.append(ManifestFile(path=rel, kind=name, parse_error=parse_error))

        # --- Runtime declarations ---
        if name in _PYTHON_RUNTIME_FILES:
            try:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
                runtime_decls.append(f"{name}: {content[:50]}")
            except OSError:
                pass

        # --- CI files ---
        if _CI_FILES_RE.search("/" + rel):
            ci_files.append(rel)
            if ".github/workflows" in rel:
                ci_systems.add(CISystem.GITHUB_ACTIONS)
            elif "tox.ini" in rel:
                ci_systems.add(CISystem.TOX)
                test_config_files.append(rel)
            elif "noxfile.py" in rel:
                ci_systems.add(CISystem.NOX)
                test_config_files.append(rel)

        # --- Dockerfile ---
        if _DOCKERFILE_RE.search("/" + rel) or name.lower() == "dockerfile":
            docker_files.append(rel)

        # --- Packaging ---
        if name in _PACKAGING_FILES or name.endswith(".dist-info"):
            packaging_files.append(rel)

        # --- tox.ini as standalone ---
        if name == "tox.ini":
            ci_systems.add(CISystem.TOX)
            if rel not in test_config_files:
                test_config_files.append(rel)

        # --- pytest.ini / conftest.py / setup.cfg ---
        if name in ("pytest.ini", "conftest.py"):
            test_frameworks.add(TestingFramework.PYTEST)
            test_config_files.append(rel)
        if name == "setup.cfg":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if "[tool:pytest]" in text or "[pytest]" in text:
                    test_frameworks.add(TestingFramework.PYTEST)
                    test_config_files.append(rel)
            except OSError:
                pass

    # --- Source roots ---
    source_roots = _detect_source_roots(python_files)

    # --- Pydantic evidence (backward compat) ---
    pydantic_deps = [d for d in all_deps if d.normalized_name in _PYDANTIC_NAMES]

    # --- Pydantic signal (backward compat) ---
    signal = _detect_pydantic_signal(pydantic_deps, has_pydantic_imports)

    applicability = ApplicabilitySignals(
        pydantic_signal=signal,
        pydantic_evidence=pydantic_deps,
        is_python_repo=len(python_files) > 0,
        has_pydantic_imports=has_pydantic_imports,
        python_file_count=len(python_files),
    )

    test_profile = TestProfile(
        test_files=test_files,
        frameworks=sorted(test_frameworks, key=lambda x: x.value),
        ci_systems=sorted(ci_systems, key=lambda x: x.value),
        ci_files=ci_files,
        config_files=test_config_files,
    )

    # --- Multi-language summary ---
    detected_languages = sorted(
        source_files_by_language.keys(),
        key=lambda lang: len(source_files_by_language[lang]),
        reverse=True,
    )
    primary_language = detected_languages[0] if detected_languages else None

    logger.info(
        "Repository profiled: python_files=%d pydantic_signal=%s languages=%s",
        len(python_files),
        signal,
        detected_languages,
    )

    return RepositoryProfile(
        source_files_by_language=source_files_by_language,
        detected_languages=detected_languages,
        primary_language=primary_language,
        python_files=python_files,
        python_file_count=len(python_files),
        source_roots=source_roots,
        manifest_files=manifest_files,
        all_dependencies=all_deps,
        pydantic_dependencies=pydantic_deps,
        runtime_declarations=runtime_decls,
        test_profile=test_profile,
        docker_files=docker_files,
        packaging_files=packaging_files,
        excluded_paths=excluded_paths,
        syntax_errors=syntax_errors,
        applicability=applicability,
        profiler_version=PROFILER_VERSION,
    )
