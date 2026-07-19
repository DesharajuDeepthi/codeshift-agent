"""Unit tests for manifest parsers (requirements.txt, pyproject.toml PEP621/Poetry)."""

from __future__ import annotations

from upgradepilot.analyzers.manifest_parser import (
    parse_pyproject_toml,
    parse_requirements_txt,
)
from upgradepilot.models.profile import ConstraintKind

# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------


class TestRequirementsTxt:
    def test_exact_version(self) -> None:
        deps, errors = parse_requirements_txt("pydantic==1.10.13\n", "requirements.txt")
        assert len(deps) == 1
        assert deps[0].normalized_name == "pydantic"
        assert deps[0].constraint.kind == ConstraintKind.EXACT
        assert deps[0].constraint.lower == "1.10.13"
        assert not errors

    def test_bounded_range(self) -> None:
        deps, errors = parse_requirements_txt("fastapi>=0.95.0,<1.0.0\n", "r.txt")
        assert len(deps) == 1
        assert deps[0].constraint.kind == ConstraintKind.BOUNDED
        assert deps[0].constraint.lower == "0.95.0"
        assert deps[0].constraint.upper == "1.0.0"

    def test_unpinned(self) -> None:
        deps, errors = parse_requirements_txt("pydantic\n", "r.txt")
        assert deps[0].constraint.kind == ConstraintKind.UNPINNED

    def test_compatible_release(self) -> None:
        deps, _ = parse_requirements_txt("httpx~=0.24.0\n", "r.txt")
        assert deps[0].constraint.kind == ConstraintKind.BOUNDED

    def test_extras_stripped(self) -> None:
        deps, _ = parse_requirements_txt("uvicorn[standard]>=0.20.0\n", "r.txt")
        assert deps[0].normalized_name == "uvicorn"
        assert deps[0].constraint.kind == ConstraintKind.RANGE

    def test_comment_lines_skipped(self) -> None:
        deps, _ = parse_requirements_txt("# just a comment\npydantic==1.10\n", "r.txt")
        assert len(deps) == 1

    def test_inline_comment_stripped(self) -> None:
        deps, _ = parse_requirements_txt("pydantic==1.10  # pinned\n", "r.txt")
        assert deps[0].constraint.kind == ConstraintKind.EXACT

    def test_env_marker_stripped(self) -> None:
        deps, _ = parse_requirements_txt("pywin32>=1.0; sys_platform=='win32'\n", "r.txt")
        assert deps[0].normalized_name == "pywin32"

    def test_line_continuation(self) -> None:
        content = "pydantic \\\n  ==1.10.13\n"
        deps, _ = parse_requirements_txt(content, "r.txt")
        assert deps[0].normalized_name == "pydantic"

    def test_dash_option_skipped(self) -> None:
        deps, _ = parse_requirements_txt("-r other-requirements.txt\npydantic==1.10\n", "r.txt")
        assert len(deps) == 1

    def test_normalized_name(self) -> None:
        deps, _ = parse_requirements_txt("PyDantic==1.10\n", "r.txt")
        assert deps[0].normalized_name == "pydantic"
        deps, _ = parse_requirements_txt("my_package==1.0\n", "r.txt")
        assert deps[0].normalized_name == "my-package"

    def test_parser_version_set(self) -> None:
        deps, _ = parse_requirements_txt("pydantic==1.10\n", "r.txt")
        assert deps[0].parser == "requirements_txt"
        assert deps[0].parser_version != ""

    def test_malformed_line_captured_as_error(self) -> None:
        # Lines starting with options are skipped, but truly unparseable are errors
        deps, errors = parse_requirements_txt("@@@invalid@@@\n", "r.txt")
        assert len(errors) == 1

    def test_empty_content(self) -> None:
        deps, errors = parse_requirements_txt("", "r.txt")
        assert deps == []
        assert errors == []


# ---------------------------------------------------------------------------
# pyproject.toml — PEP 621
# ---------------------------------------------------------------------------


PEP621_CONTENT = """\
[project]
name = "myapp"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0.0,<3.0.0",
    "httpx>=0.24.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]
"""


class TestPyprojectPep621:
    def test_pep621_dependencies_parsed(self) -> None:
        deps, errors, rt = parse_pyproject_toml(PEP621_CONTENT, "pyproject.toml")
        names = {d.normalized_name for d in deps}
        assert "pydantic" in names
        assert "httpx" in names

    def test_pep621_optional_deps_parsed(self) -> None:
        deps, errors, rt = parse_pyproject_toml(PEP621_CONTENT, "pyproject.toml")
        names = {d.normalized_name for d in deps}
        assert "pytest" in names

    def test_pep621_requires_python(self) -> None:
        _, _, rt = parse_pyproject_toml(PEP621_CONTENT, "pyproject.toml")
        assert any(">=3.10" in r for r in rt)

    def test_pep621_pydantic_bounded(self) -> None:
        deps, _, _ = parse_pyproject_toml(PEP621_CONTENT, "pyproject.toml")
        pyd = next(d for d in deps if d.normalized_name == "pydantic")
        assert pyd.constraint.kind == ConstraintKind.BOUNDED
        assert pyd.constraint.lower == "2.0.0"

    def test_malformed_toml_returns_error(self) -> None:
        bad = "[project\nname = 'broken'"
        deps, errors, rt = parse_pyproject_toml(bad, "pyproject.toml")
        assert len(errors) == 1
        assert "TOML" in errors[0]
        assert deps == []


# ---------------------------------------------------------------------------
# pyproject.toml — Poetry
# ---------------------------------------------------------------------------


POETRY_CONTENT = """\
[tool.poetry]
name = "myservice"

[tool.poetry.dependencies]
python = "^3.9"
pydantic = "^1.10"
requests = "^2.28"

[tool.poetry.dev-dependencies]
pytest = "^7.0"

[tool.poetry.group.test.dependencies]
httpx = ">=0.24"
"""


class TestPyprojectPoetry:
    def test_poetry_main_deps(self) -> None:
        deps, errors, rt = parse_pyproject_toml(POETRY_CONTENT, "pyproject.toml")
        names = {d.normalized_name for d in deps}
        assert "pydantic" in names
        assert "requests" in names

    def test_poetry_dev_deps(self) -> None:
        deps, _, _ = parse_pyproject_toml(POETRY_CONTENT, "pyproject.toml")
        names = {d.normalized_name for d in deps}
        assert "pytest" in names

    def test_poetry_group_deps(self) -> None:
        deps, _, _ = parse_pyproject_toml(POETRY_CONTENT, "pyproject.toml")
        names = {d.normalized_name for d in deps}
        assert "httpx" in names

    def test_poetry_python_runtime(self) -> None:
        _, _, rt = parse_pyproject_toml(POETRY_CONTENT, "pyproject.toml")
        assert any("^3.9" in r for r in rt)

    def test_poetry_pydantic_range(self) -> None:
        deps, _, _ = parse_pyproject_toml(POETRY_CONTENT, "pyproject.toml")
        pyd = next(d for d in deps if d.normalized_name == "pydantic")
        # ^1.10 is a range/compatible constraint
        assert pyd.constraint.kind in (ConstraintKind.RANGE, ConstraintKind.BOUNDED)
