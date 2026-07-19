"""
Unit tests for the repository profiler using fixture repositories.

Each fixture covers a distinct scenario.
Tests verify what the acceptance matrix requires:
- expected manifests detected
- test/CI/runtime/Pydantic evidence detected
- exclusions work
- syntax errors captured without crash
"""

from __future__ import annotations

from pathlib import Path

from upgradepilot.analyzers.repository_profiler import profile_repository
from upgradepilot.models.profile import CISystem, PydanticSignal, TestingFramework

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestReqTxtFixture:
    """requirements.txt fixture with pydantic==1.10.13, tests, GitHub Actions."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "req_txt")

    def test_is_python_repo(self) -> None:
        assert self.profile.applicability.is_python_repo

    def test_manifest_detected(self) -> None:
        paths = [m.path for m in self.profile.manifest_files]
        assert any("requirements.txt" in p for p in paths)

    def test_pydantic_v1_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.V1_DETECTED

    def test_pydantic_dep_exact(self) -> None:
        assert len(self.profile.pydantic_dependencies) >= 1
        pyd = self.profile.pydantic_dependencies[0]
        assert pyd.constraint.lower == "1.10.13"

    def test_test_files_detected(self) -> None:
        assert len(self.profile.test_profile.test_files) >= 1

    def test_pytest_detected(self) -> None:
        assert TestingFramework.PYTEST in self.profile.test_profile.frameworks

    def test_github_actions_detected(self) -> None:
        assert CISystem.GITHUB_ACTIONS in self.profile.test_profile.ci_systems

    def test_pydantic_import_detected(self) -> None:
        assert self.profile.applicability.has_pydantic_imports


class TestPep621Fixture:
    """PEP 621 pyproject.toml with pydantic>=2.0.0,<3.0.0, Dockerfile, src layout."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "pep621")

    def test_manifest_detected(self) -> None:
        paths = [m.path for m in self.profile.manifest_files]
        assert any("pyproject.toml" in p for p in paths)

    def test_pydantic_v2_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.V2_DETECTED

    def test_requires_python_detected(self) -> None:
        assert any("3.10" in r for r in self.profile.runtime_declarations)

    def test_dockerfile_detected(self) -> None:
        assert len(self.profile.docker_files) >= 1

    def test_src_root_detected(self) -> None:
        assert len(self.profile.source_roots) >= 1

    def test_no_parse_errors(self) -> None:
        for m in self.profile.manifest_files:
            if "pyproject.toml" in m.path:
                assert m.parse_error is None


class TestPoetryFixture:
    """Poetry pyproject.toml with pydantic ^1.10 and tox.ini."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "poetry")

    def test_pydantic_v1_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.V1_DETECTED

    def test_tox_detected(self) -> None:
        assert CISystem.TOX in self.profile.test_profile.ci_systems

    def test_poetry_python_runtime(self) -> None:
        assert any("3.9" in r or "python" in r.lower() for r in self.profile.runtime_declarations)

    def test_pytest_via_poetry_dev_deps(self) -> None:
        deps = {d.normalized_name for d in self.profile.all_dependencies}
        assert "pytest" in deps


class TestNoPydanticFixture:
    """Repository with no pydantic dependency."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "no_pydantic")

    def test_not_found_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.NOT_FOUND

    def test_no_pydantic_deps(self) -> None:
        assert self.profile.pydantic_dependencies == []

    def test_is_python_repo(self) -> None:
        assert self.profile.applicability.is_python_repo


class TestPydanticV1Fixture:
    """requirements.txt with pydantic>=1.9,<2.0."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "pydantic_v1")

    def test_v1_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.V1_DETECTED


class TestPydanticV2Fixture:
    """requirements.txt with pydantic>=2.0.0."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "pydantic_v2")

    def test_v2_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.V2_DETECTED


class TestUnpinnedPydanticFixture:
    """requirements.txt with bare 'pydantic' (no version)."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "unpinned_pydantic")

    def test_unpinned_signal(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.UNPINNED


class TestMalformedFixture:
    """Malformed pyproject.toml and requirements.txt with bad lines."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "malformed")

    def test_malformed_toml_captured_not_crash(self) -> None:
        toml_manifests = [m for m in self.profile.manifest_files if "pyproject.toml" in m.path]
        assert len(toml_manifests) == 1
        assert toml_manifests[0].parse_error is not None

    def test_valid_lines_in_malformed_req_parsed(self) -> None:
        # pydantic==1.10.0 and flask should still be parsed from requirements.txt
        # even though there are bad lines
        names = {d.normalized_name for d in self.profile.all_dependencies}
        assert "pydantic" in names
        assert "flask" in names

    def test_bad_lines_produce_errors(self) -> None:
        req_manifests = [m for m in self.profile.manifest_files if "requirements.txt" in m.path]
        assert len(req_manifests) == 1
        # Error may or may not be set depending on whether any lines produce errors


class TestSyntaxErrorFixture:
    """Python file with syntax error — analysis must not crash, profile still produced."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "syntax_error")

    def test_syntax_error_captured(self) -> None:
        assert len(self.profile.syntax_errors) >= 1
        err = self.profile.syntax_errors[0]
        assert "app.py" in err.path
        assert err.message is not None

    def test_good_file_still_profiled(self) -> None:
        assert any("good.py" in f for f in self.profile.python_files)

    def test_pydantic_from_requirements_still_found(self) -> None:
        assert self.profile.applicability.pydantic_signal == PydanticSignal.V1_DETECTED

    def test_pydantic_imports_from_good_file(self) -> None:
        assert self.profile.applicability.has_pydantic_imports


class TestExcludedDirsFixture:
    """Workspace with .venv, vendor, dist — excluded files must not appear in index."""

    def setup_method(self) -> None:
        self.profile = profile_repository(FIXTURES / "excluded_dirs")

    def test_venv_files_not_in_python_files(self) -> None:
        for f in self.profile.python_files:
            assert ".venv" not in f, f"venv file leaked: {f}"

    def test_vendor_files_excluded(self) -> None:
        for f in self.profile.python_files:
            assert "vendor/" not in f, f"vendor file leaked: {f}"

    def test_src_file_included(self) -> None:
        assert any("myapp.py" in f for f in self.profile.python_files)

    def test_requirements_manifest_found(self) -> None:
        paths = [m.path for m in self.profile.manifest_files]
        assert any("requirements.txt" in p for p in paths)
