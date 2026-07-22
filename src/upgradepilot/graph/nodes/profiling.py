"""
profile_repository and select_migration_pack nodes.
"""

from __future__ import annotations

from typing import Any

from upgradepilot.graph.nodes._helpers import (
    _now,
    graph_error,
    is_fixture,
    node_error_record,
    node_record,
)
from upgradepilot.graph.state import (
    FIXTURE_NOT_APPLICABLE,
    FIXTURE_UNSUPPORTED,
    AnalysisStatus,
    ApplicabilityStatus,
    UpgradePilotState,
)

# ---------------------------------------------------------------------------
# profile_repository
# ---------------------------------------------------------------------------

_NODE_PROFILE = "profile_repository"

_FIXTURE_PROFILE: dict[str, Any] = {
    # Multi-language fields (new in profiler v2.0.0)
    "source_files_by_language": {"python": ["src/app/models.py", "src/app/schemas.py"]},
    "detected_languages": ["python"],
    "primary_language": "python",
    # Python-specific (backward compat)
    "python_file_count": 12,
    "python_files": ["src/app/models.py", "src/app/schemas.py"],
    "source_roots": ["src"],
    "manifest_files": [{"path": "pyproject.toml", "kind": "pyproject_toml", "parse_error": None}],
    "all_dependencies": [
        {
            "package": "pydantic",
            "normalized_name": "pydantic",
            "constraint": {"raw": ">=1.9,<2", "kind": "range", "lower": "1.9", "upper": "2"},
            "manifest_path": "pyproject.toml",
            "line": 12,
            "parser": "pyproject_toml",
            "parser_version": "1.0.0",
            "confidence": 1.0,
        }
    ],
    "pydantic_dependencies": [
        {
            "package": "pydantic",
            "normalized_name": "pydantic",
            "constraint": {"raw": ">=1.9,<2", "kind": "range", "lower": "1.9", "upper": "2"},
            "manifest_path": "pyproject.toml",
            "line": 12,
            "parser": "pyproject_toml",
            "parser_version": "1.0.0",
            "confidence": 1.0,
        }
    ],
    "runtime_declarations": ["python>=3.10"],
    "test_profile": {
        "test_files": ["tests/test_models.py"],
        "frameworks": ["pytest"],
        "ci_systems": ["github_actions"],
        "ci_files": [".github/workflows/ci.yml"],
        "config_files": ["pyproject.toml"],
    },
    "docker_files": [],
    "packaging_files": [],
    "excluded_paths": [],
    "syntax_errors": [],
    "applicability": {
        "pydantic_signal": "v1_detected",
        "pydantic_evidence": [],
        "is_python_repo": True,
        "has_pydantic_imports": True,
        "python_file_count": 12,
    },
    "profiler_version": "2.0.0",
}

_FIXTURE_PROFILE_NOT_APPLICABLE: dict[str, Any] = {
    **_FIXTURE_PROFILE,
    "all_dependencies": [],
    "pydantic_dependencies": [],
    "applicability": {
        "pydantic_signal": "not_found",
        "pydantic_evidence": [],
        "is_python_repo": True,
        "has_pydantic_imports": False,
        "python_file_count": 12,
    },
}

_FIXTURE_PROFILE_UNSUPPORTED: dict[str, Any] = {
    **_FIXTURE_PROFILE,
    "all_dependencies": [
        {
            "package": "pydantic",
            "normalized_name": "pydantic",
            "constraint": {"raw": ">=2", "kind": "bounded", "lower": "2", "upper": None},
            "manifest_path": "pyproject.toml",
            "line": 12,
            "parser": "pyproject_toml",
            "parser_version": "1.0.0",
            "confidence": 1.0,
        }
    ],
    "pydantic_dependencies": [
        {
            "package": "pydantic",
            "normalized_name": "pydantic",
            "constraint": {"raw": ">=2", "kind": "bounded", "lower": "2", "upper": None},
            "manifest_path": "pyproject.toml",
            "line": 12,
            "parser": "pyproject_toml",
            "parser_version": "1.0.0",
            "confidence": 1.0,
        }
    ],
    "applicability": {
        "pydantic_signal": "v2_detected",
        "pydantic_evidence": [],
        "is_python_repo": True,
        "has_pydantic_imports": True,
        "python_file_count": 12,
    },
}


async def profile_repository(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        scenario = state.get("fixture_scenario", "")
        if scenario == FIXTURE_NOT_APPLICABLE:
            profile = _FIXTURE_PROFILE_NOT_APPLICABLE
        elif scenario == FIXTURE_UNSUPPORTED:
            profile = _FIXTURE_PROFILE_UNSUPPORTED
        else:
            profile = _FIXTURE_PROFILE
        return {
            "profile": profile,
            "node_executions": [node_record(_NODE_PROFILE, started)],
        }

    snapshot_dict = state.get("snapshot")
    if not snapshot_dict:
        return {
            "status": AnalysisStatus.TERMINAL,
            "node_executions": [node_error_record(_NODE_PROFILE, started, "NO_SNAPSHOT")],
            "errors": [
                graph_error(_NODE_PROFILE, "NO_SNAPSHOT", "No snapshot available to profile")
            ],
        }

    try:
        from pathlib import Path

        from upgradepilot.analyzers.repository_profiler import profile_repository
        from upgradepilot.models.snapshot import RepositorySnapshot

        snapshot = RepositorySnapshot.model_validate(snapshot_dict)
        profile = profile_repository(Path(snapshot.workspace_path))
        return {
            "profile": profile.model_dump(),
            "node_executions": [node_record(_NODE_PROFILE, started)],
        }
    except Exception as exc:
        return {
            "status": AnalysisStatus.TERMINAL,
            "node_executions": [node_error_record(_NODE_PROFILE, started, "PROFILER_ERROR")],
            "errors": [graph_error(_NODE_PROFILE, "PROFILER_ERROR", str(exc))],
        }


# ---------------------------------------------------------------------------
# select_migration_pack
# ---------------------------------------------------------------------------

_NODE_PACK = "select_migration_pack"

_PACK_ID = "pydantic-v1-to-v2"


async def select_migration_pack(state: UpgradePilotState) -> dict[str, Any]:
    started = _now()

    if is_fixture(state):
        scenario = state.get("fixture_scenario", "")
        if scenario == FIXTURE_NOT_APPLICABLE:
            return {
                "applicability_status": ApplicabilityStatus.NOT_APPLICABLE,
                "pack_id": _PACK_ID,
                "node_executions": [node_record(_NODE_PACK, started)],
                "warnings": ["Pydantic v1 not detected in this repository (fixture)."],
            }
        if scenario == FIXTURE_UNSUPPORTED:
            return {
                "applicability_status": ApplicabilityStatus.UNSUPPORTED,
                "pack_id": _PACK_ID,
                "node_executions": [node_record(_NODE_PACK, started)],
                "warnings": ["Already on Pydantic v2 (fixture)."],
            }
        return {
            "applicability_status": ApplicabilityStatus.SUPPORTED,
            "pack_id": _PACK_ID,
            "node_executions": [node_record(_NODE_PACK, started)],
        }

    # STANDARD mode: run pack-driven applicability assessment from profile.
    profile_dict = state.get("profile")
    if not profile_dict:
        return {
            "status": AnalysisStatus.TERMINAL,
            "node_executions": [node_error_record(_NODE_PACK, started, "NO_PROFILE")],
            "errors": [graph_error(_NODE_PACK, "NO_PROFILE", "Profile is missing")],
        }

    try:
        from pathlib import Path

        from upgradepilot.migration.applicability import ApplicabilityEngine
        from upgradepilot.migration.errors import PackNotFoundError
        from upgradepilot.migration.loader import load_all_packs
        from upgradepilot.models.profile import RepositoryProfile
        from upgradepilot.models.snapshot import RepositorySnapshot

        profile = RepositoryProfile.model_validate(profile_dict)
        pack_id = state.get("request_data", {}).get("migration_pack", _PACK_ID)

        registry = load_all_packs()
        try:
            pack = registry.get(pack_id)
        except PackNotFoundError:
            available = registry.list_ids()
            return {
                "applicability_status": ApplicabilityStatus.ERROR,
                "pack_id": pack_id,
                "node_executions": [node_error_record(_NODE_PACK, started, "PACK_NOT_FOUND")],
                "errors": [
                    graph_error(
                        _NODE_PACK,
                        "PACK_NOT_FOUND",
                        f"Migration pack {pack_id!r} not found. Available: {available}",
                    )
                ],
            }

        # Resolve workspace path for code-signal evaluation (optional).
        workspace: Path | None = None
        snapshot_dict = state.get("snapshot")
        if snapshot_dict:
            snapshot = RepositorySnapshot.model_validate(snapshot_dict)
            workspace = Path(snapshot.workspace_path)

        engine = ApplicabilityEngine(pack)
        assessment = engine.assess(profile, workspace)

        extra: dict[str, Any] = {}
        if assessment.warnings:
            extra["warnings"] = assessment.warnings

        # Map assessment status to ApplicabilityStatus enum.
        # ApplicabilityEngine returns ApplicabilityStatus directly.
        return {
            "applicability_status": assessment.status,
            "pack_id": pack_id,
            "node_executions": [node_record(_NODE_PACK, started)],
            **extra,
        }

    except Exception as exc:
        return {
            "applicability_status": ApplicabilityStatus.ERROR,
            "pack_id": state.get("request_data", {}).get("migration_pack", _PACK_ID),
            "node_executions": [node_error_record(_NODE_PACK, started, "APPLICABILITY_ERROR")],
            "errors": [graph_error(_NODE_PACK, "APPLICABILITY_ERROR", str(exc))],
        }
