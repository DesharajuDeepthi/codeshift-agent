"""Unit tests for auto-detect pack selection in select_migration_pack."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from upgradepilot.graph.state import FIXTURE_SUPPORTED, make_initial_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_PROFILE: dict[str, Any] = {
    "source_files_by_language": {"python": ["src/app.py"]},
    "detected_languages": ["python"],
    "primary_language": "python",
    "python_file_count": 1,
    "python_files": ["src/app.py"],
    "source_roots": ["src"],
    "manifest_files": [],
    "all_dependencies": [],
    "pydantic_dependencies": [],
    "runtime_declarations": [],
    "test_profile": {
        "test_files": [],
        "frameworks": [],
        "ci_systems": [],
        "ci_files": [],
        "config_files": [],
    },
    "docker_files": [],
    "packaging_files": [],
    "excluded_paths": [],
    "syntax_errors": [],
    "applicability": {
        "pydantic_signal": "not_found",
        "pydantic_evidence": [],
        "is_python_repo": True,
        "has_pydantic_imports": False,
        "python_file_count": 1,
    },
    "profiler_version": "2.0.0",
}


def _make_state(pack_id: str | None = None) -> dict[str, Any]:
    request_data = {
        "repository_url": "https://github.com/owner/repo",
        "ref": "main",
        "migration_pack": pack_id,
        "analysis_mode": "standard",
        "request_id": "test-id",
        "created_at": "2026-01-01T00:00:00Z",
        "github_owner": "owner",
        "github_repo": "repo",
    }
    state = dict(make_initial_state("test-analysis", request_data, FIXTURE_SUPPORTED))
    state["profile"] = _BASE_PROFILE
    return state


def _mock_assessment(status: str, confidence: float) -> MagicMock:
    a = MagicMock()
    a.status.value = status
    a.confidence = confidence
    a.warnings = []
    return a


def _mock_pack(pack_id: str, display_name: str) -> MagicMock:
    m = MagicMock()
    m.metadata.pack_id = pack_id
    m.metadata.display_name = display_name
    return m


def _mock_registry(
    pack_assessments: list[tuple[str, str, str, float]],
) -> tuple[MagicMock, dict[str, tuple[str, float]]]:
    """Build a mock registry from [(pack_id, display_name, status, confidence)]."""
    packs = {pid: _mock_pack(pid, dn) for pid, dn, _, _ in pack_assessments}
    registry = MagicMock()
    registry.list_ids.return_value = [pid for pid, *_ in pack_assessments]
    registry.get.side_effect = lambda pid: packs[pid]
    scores = {pid: (st, conf) for pid, _, st, conf in pack_assessments}
    return registry, scores


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoDetect:
    def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        from upgradepilot.graph.nodes.profiling import select_migration_pack

        return asyncio.run(select_migration_pack(state))  # type: ignore[arg-type]

    def _status_val(self, result: dict[str, Any]) -> str:
        v = result["applicability_status"]
        return v.value if hasattr(v, "value") else str(v)

    def test_single_supported_pack_selected(self) -> None:
        registry, scores = _mock_registry(
            [("pydantic-v1-to-v2", "Pydantic v1 → v2", "SUPPORTED", 0.9)]
        )

        def fake_engine(pack: Any) -> Any:
            e = MagicMock()
            pid = pack.metadata.pack_id
            status, conf = scores[pid]
            e.assess.return_value = _mock_assessment(status, conf)
            return e

        with (
            patch("upgradepilot.migration.loader.load_all_packs", return_value=registry),
            patch(
                "upgradepilot.migration.applicability.ApplicabilityEngine",
                side_effect=fake_engine,
            ),
        ):
            result = self._run(_make_state(pack_id=None))

        assert result["pack_id"] == "pydantic-v1-to-v2"
        assert self._status_val(result) == "SUPPORTED"
        assert result["pack_candidates"] != []

    def test_no_applicable_pack_returns_not_applicable(self) -> None:
        registry, scores = _mock_registry(
            [
                ("pydantic-v1-to-v2", "Pydantic v1 → v2", "NOT_APPLICABLE", 0.1),
                ("django-v3-to-v4", "Django v3 → v4", "NOT_APPLICABLE", 0.1),
            ]
        )

        def fake_engine(pack: Any) -> Any:
            e = MagicMock()
            pid = pack.metadata.pack_id
            status, conf = scores[pid]
            e.assess.return_value = _mock_assessment(status, conf)
            return e

        with (
            patch("upgradepilot.migration.loader.load_all_packs", return_value=registry),
            patch(
                "upgradepilot.migration.applicability.ApplicabilityEngine",
                side_effect=fake_engine,
            ),
        ):
            result = self._run(_make_state(pack_id=None))

        assert self._status_val(result) == "NOT_APPLICABLE"
        assert result["pack_id"] == ""
        assert len(result["pack_candidates"]) == 2
        assert any(e["error_code"] == "NO_APPLICABLE_PACK" for e in result.get("errors", []))

    def test_highest_confidence_pack_wins(self) -> None:
        registry, scores = _mock_registry(
            [
                ("django-v3-to-v4", "Django v3 → v4", "SUPPORTED", 0.95),
                ("pydantic-v1-to-v2", "Pydantic v1 → v2", "SUPPORTED", 0.60),
            ]
        )

        def fake_engine(pack: Any) -> Any:
            e = MagicMock()
            pid = pack.metadata.pack_id
            status, conf = scores[pid]
            e.assess.return_value = _mock_assessment(status, conf)
            return e

        with (
            patch("upgradepilot.migration.loader.load_all_packs", return_value=registry),
            patch(
                "upgradepilot.migration.applicability.ApplicabilityEngine",
                side_effect=fake_engine,
            ),
        ):
            result = self._run(_make_state(pack_id=None))

        assert result["pack_id"] == "django-v3-to-v4"

    def test_tie_warning_emitted(self) -> None:
        registry, scores = _mock_registry(
            [
                ("pydantic-v1-to-v2", "Pydantic v1 → v2", "SUPPORTED", 0.90),
                ("django-v3-to-v4", "Django v3 → v4", "SUPPORTED", 0.85),
            ]
        )

        def fake_engine(pack: Any) -> Any:
            e = MagicMock()
            pid = pack.metadata.pack_id
            status, conf = scores[pid]
            e.assess.return_value = _mock_assessment(status, conf)
            return e

        with (
            patch("upgradepilot.migration.loader.load_all_packs", return_value=registry),
            patch(
                "upgradepilot.migration.applicability.ApplicabilityEngine",
                side_effect=fake_engine,
            ),
        ):
            result = self._run(_make_state(pack_id=None))

        assert result["pack_id"] == "pydantic-v1-to-v2"
        assert any("Django" in w for w in result.get("warnings", []))

    def test_explicit_pack_bypasses_auto_detect(self) -> None:
        """When migration_pack is specified, only that pack is evaluated."""
        pack = _mock_pack("pydantic-v1-to-v2", "Pydantic v1 → v2")
        registry = MagicMock()
        registry.list_ids.return_value = ["pydantic-v1-to-v2", "django-v3-to-v4"]
        registry.get.return_value = pack

        assessment = _mock_assessment("SUPPORTED", 0.9)

        def fake_engine(p: Any) -> Any:
            e = MagicMock()
            e.assess.return_value = assessment
            return e

        with (
            patch("upgradepilot.migration.loader.load_all_packs", return_value=registry),
            patch(
                "upgradepilot.migration.applicability.ApplicabilityEngine",
                side_effect=fake_engine,
            ),
        ):
            result = self._run(_make_state(pack_id="pydantic-v1-to-v2"))

        assert result["pack_id"] == "pydantic-v1-to-v2"
        registry.list_ids.assert_not_called()
