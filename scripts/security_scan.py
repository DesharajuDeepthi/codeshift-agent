"""Local release security checks for secrets, dependency locks, and containers."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SECRET_PATTERNS = {
    "openai_or_anthropic_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "langsmith_key": re.compile(r"ls__[A-Za-z0-9]{40,}"),
    "github_token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "eval_results",
    "workspace",
}
EXCLUDED_FILES = {".env", ".env.local"}
SECRET_SCAN_SUFFIXES = {
    ".dockerignore",
    ".example",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
ALLOWLIST_SECRET_FILES = {
    Path("tests/unit/test_redaction.py"),
    Path("tests/unit/test_tracing.py"),
    Path("tests/unit/test_logging.py"),
    Path("UpgradePilot_Claude_Code_Full_Prompts_With_Modes.md"),
}


def run(root: Path) -> dict[str, Any]:
    """Run local release security checks."""
    findings: list[dict[str, Any]] = []
    findings.extend(_secret_findings(root))
    findings.extend(_dependency_findings(root))
    findings.extend(_container_findings(root))
    return {
        "passed": not any(finding["severity"] == "error" for finding in findings),
        "findings": findings,
        "scanned_root": str(root),
    }


def _secret_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in _iter_files(root):
        rel = path.relative_to(root)
        if rel in ALLOWLIST_SECRET_FILES:
            continue
        if path.suffix not in SECRET_SCAN_SUFFIXES and path.name not in {
            "Dockerfile",
            "Dockerfile.ui",
        }:
            continue
        text = _read_text(path)
        if text is None:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "severity": "error",
                        "category": "secret_scan",
                        "code": name,
                        "path": str(rel),
                        "line": line,
                        "detail": "Potential secret pattern in release-scanned file.",
                    }
                )
    return findings


def _dependency_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not (root / "uv.lock").exists():
        findings.append(
            {
                "severity": "error",
                "category": "dependency_scan",
                "code": "missing_lockfile",
                "detail": "uv.lock is required for reproducible dependency resolution.",
            }
        )
    pyproject = _read_text(root / "pyproject.toml") or ""
    if "dependencies = [" not in pyproject:
        findings.append(
            {
                "severity": "error",
                "category": "dependency_scan",
                "code": "missing_dependencies",
                "detail": "pyproject.toml does not expose project dependencies.",
            }
        )
    return findings


def _container_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name in ("Dockerfile", "Dockerfile.ui"):
        text = _read_text(root / name) or ""
        if "USER appuser" not in text:
            findings.append(
                {
                    "severity": "error",
                    "category": "container_scan",
                    "code": "container_runs_as_root",
                    "path": name,
                    "detail": "Runtime image should switch to a non-root user.",
                }
            )
        if "HEALTHCHECK" not in text:
            findings.append(
                {
                    "severity": "warning",
                    "category": "container_scan",
                    "code": "missing_healthcheck",
                    "path": name,
                    "detail": "Runtime image has no Docker healthcheck.",
                }
            )
        if re.search(r"FROM\s+[^:\s]+:latest\b", text):
            findings.append(
                {
                    "severity": "error",
                    "category": "container_scan",
                    "code": "latest_base_image",
                    "path": name,
                    "detail": "Base image tags must be pinned away from latest.",
                }
            )
    compose = _read_text(root / "docker-compose.yml") or ""
    if "env_file:" not in compose or ".env" not in compose:
        findings.append(
            {
                "severity": "warning",
                "category": "container_scan",
                "code": "compose_env_missing",
                "path": "docker-compose.yml",
                "detail": "Compose should load secrets from a local env file or environment.",
            }
        )
    return findings


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        rel_parts = set(path.relative_to(root).parts)
        if rel_parts & EXCLUDED_DIRS:
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if path.is_file():
            files.append(path)
    return files


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except FileNotFoundError:
        return None


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Security Scan Results",
        "",
        f"- Passed: `{result['passed']}`",
        f"- Findings: `{len(result['findings'])}`",
        "",
        "| Severity | Category | Code | Path | Detail |",
        "|---|---|---|---|---|",
    ]
    for finding in result["findings"]:
        lines.append(
            "| {severity} | {category} | {code} | {path} | {detail} |".format(
                severity=finding.get("severity", ""),
                category=finding.get("category", ""),
                code=finding.get("code", ""),
                path=finding.get("path", ""),
                detail=finding.get("detail", ""),
            )
        )
    if not result["findings"]:
        lines.append("| info | all | no_findings |  | Local release scan found no issues. |")
    lines.append("")
    lines.append(
        "Note: local `.env` files, caches, virtualenvs, and test fixtures with synthetic "
        "keys are excluded from the release scan."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    result = run(Path(args.root).resolve())
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if args.markdown_output:
        Path(args.markdown_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown_output).write_text(_markdown(result), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "findings": len(result["findings"])}))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
