"""
Pack-driven applicability engine.

Replaces the hardcoded Pydantic applicability logic in
graph/nodes/profiling.py:select_migration_pack with a deterministic engine
that interprets a pack's applicability.yaml at runtime.

The engine evaluates each signal in order and aggregates results according to
the pack's aggregation rules.  No LLM calls are made here.

Signal kinds
------------
manifest_constraint   Evaluates version constraints on a named package in the
                      profile's all_dependencies list.
import_symbol         Detects whether specific symbols are imported from a
                      module (currently implemented as a regex check on the
                      code_signals; a future version can delegate to the
                      LanguageAnalyzer for higher accuracy).
v1_api_usage          Text pattern that only appears in the source version.
v2_api_usage          Text pattern that only appears in the target version.
compat_namespace      Import of a compat shim (e.g. pydantic.v1).
file_pattern          Presence of filenames matching a glob in the workspace.
language_present      Whether the pack's declared language is in the profile's
                      detected_languages list.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from upgradepilot.graph.state import ApplicabilityStatus
from upgradepilot.migration.models import ApplicabilityConfig, LoadedMigrationPack
from upgradepilot.models.profile import RepositoryProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalResult:
    """The outcome of evaluating one applicability signal."""

    signal_id: str
    kind: str
    fired: bool
    result_status: str | None  # e.g. "SUPPORTED", "NOT_APPLICABLE", "PROBABLE_NEEDS_REVIEW"
    confidence: float
    reason: str


@dataclass(frozen=True)
class ApplicabilityAssessment:
    """The aggregated result of running all signals against a repository profile."""

    status: ApplicabilityStatus
    confidence: float
    signals: list[SignalResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ApplicabilityEngine:
    """
    Evaluates a pack's applicability.yaml signals against a RepositoryProfile.

    Usage:
        engine = ApplicabilityEngine(pack)
        assessment = engine.assess(profile)
    """

    def __init__(self, pack: LoadedMigrationPack) -> None:
        self._pack = pack
        self._config: ApplicabilityConfig = pack.applicability

    def assess(
        self,
        profile: RepositoryProfile,
        workspace: Path | None = None,
    ) -> ApplicabilityAssessment:
        """
        Run all signals and return an applicability assessment.

        Parameters
        ----------
        profile:
            The repository profile produced by the profiler.
        workspace:
            Optional path to the extracted workspace.  Required only when
            evaluating file_pattern or import_symbol signals that need
            file-system access.
        """
        signals: list[SignalResult] = []
        warnings: list[str] = []

        for sig_def in self._config.manifest_signals:
            result = self._eval_manifest_signal(sig_def, profile)
            if result is not None:
                signals.append(result)

        for sig_def in self._config.code_signals:
            result = self._eval_code_signal(sig_def, profile, workspace)
            if result is not None:
                signals.append(result)

        status, confidence = self._aggregate(signals, warnings)
        return ApplicabilityAssessment(
            status=status, confidence=confidence, signals=signals, warnings=warnings
        )

    # ------------------------------------------------------------------
    # Manifest signals
    # ------------------------------------------------------------------

    def _eval_manifest_signal(
        self, sig: dict[str, Any], profile: RepositoryProfile
    ) -> SignalResult | None:
        signal_id = sig.get("signal_id", "unknown")
        kind = sig.get("kind", "")

        if kind == "manifest_constraint":
            return self._eval_manifest_constraint(sig, profile)

        logger.debug("Unknown manifest signal kind %r in signal %r — skipping", kind, signal_id)
        return None

    def _eval_manifest_constraint(
        self, sig: dict[str, Any], profile: RepositoryProfile
    ) -> SignalResult:
        signal_id = sig.get("signal_id", "unknown")
        target_package = sig.get("package", "")
        required = sig.get("required", False)
        absence_status = sig.get("absence_status", "NOT_APPLICABLE")
        result_status = sig.get("result_status")
        confidence = float(sig.get("confidence", 1.0))
        constraint_kind = sig.get("constraint_kind")
        version_prefix = sig.get("version_prefix")
        upper_lt = sig.get("upper_lt")
        lower_gte = sig.get("lower_gte")

        matching_deps = [
            d
            for d in profile.all_dependencies
            if d.normalized_name == target_package.lower().replace("_", "-")
        ]

        if not matching_deps:
            if required:
                return SignalResult(
                    signal_id=signal_id,
                    kind="manifest_constraint",
                    fired=True,
                    result_status=absence_status,
                    confidence=1.0,
                    reason=f"Package {target_package!r} not found in any manifest.",
                )
            return SignalResult(
                signal_id=signal_id,
                kind="manifest_constraint",
                fired=False,
                result_status=None,
                confidence=0.0,
                reason=f"Package {target_package!r} absent (signal optional).",
            )

        # Check version constraints against each matching dep
        for dep in matching_deps:
            c = dep.constraint
            if c is None:
                continue

            matched = False

            if constraint_kind == "exact" and version_prefix:
                raw = (c.lower or c.raw or "").lstrip("v")
                matched = c.kind.value == "exact" and raw.startswith(version_prefix)

            elif constraint_kind == "bounded" and upper_lt:
                matched = c.upper is not None and _version_lt(c.upper, upper_lt)

            elif constraint_kind == "bounded" and lower_gte:
                matched = c.lower is not None and _version_gte(c.lower, lower_gte)

            elif constraint_kind == "unpinned":
                matched = c.kind.value == "unpinned"

            elif constraint_kind is None:
                # Signal fires on mere presence
                matched = True

            if matched and result_status:
                return SignalResult(
                    signal_id=signal_id,
                    kind="manifest_constraint",
                    fired=True,
                    result_status=result_status,
                    confidence=confidence,
                    reason=(
                        f"Package {target_package!r} constraint {c.raw!r} "
                        f"matches rule (constraint_kind={constraint_kind!r})."
                    ),
                )

        return SignalResult(
            signal_id=signal_id,
            kind="manifest_constraint",
            fired=False,
            result_status=None,
            confidence=0.0,
            reason=f"Package {target_package!r} present but no constraint rule matched.",
        )

    # ------------------------------------------------------------------
    # Code signals
    # ------------------------------------------------------------------

    def _eval_code_signal(
        self,
        sig: dict[str, Any],
        profile: RepositoryProfile,
        workspace: Path | None,
    ) -> SignalResult | None:
        signal_id = sig.get("signal_id", "unknown")
        kind = sig.get("kind", "")

        if kind == "language_present":
            return self._eval_language_present(sig, profile)

        if kind == "file_pattern":
            return self._eval_file_pattern(sig, profile, workspace)

        # import_symbol, v1_api_usage, v2_api_usage, compat_namespace —
        # these require workspace access; skip gracefully if unavailable.
        if workspace is None:
            logger.debug(
                "Signal %r (kind=%r) requires workspace; skipping (workspace not provided).",
                signal_id,
                kind,
            )
            return None

        if kind in ("import_symbol", "v1_api_usage", "v2_api_usage", "compat_namespace"):
            return self._eval_code_pattern(sig, workspace)

        logger.debug("Unknown code signal kind %r in signal %r — skipping", kind, signal_id)
        return None

    def _eval_language_present(
        self, sig: dict[str, Any], profile: RepositoryProfile
    ) -> SignalResult:
        signal_id = sig.get("signal_id", "unknown")
        target_lang = sig.get("language", self._pack.metadata.language).lower()
        confidence = float(sig.get("confidence", 1.0))
        result_status = sig.get("result_status", "SUPPORTED")

        detected = [lang.lower() for lang in profile.detected_languages]
        fired = target_lang in detected
        return SignalResult(
            signal_id=signal_id,
            kind="language_present",
            fired=fired,
            result_status=result_status if fired else None,
            confidence=confidence if fired else 0.0,
            reason=(
                f"Language {target_lang!r} {'detected' if fired else 'not detected'} "
                f"in repository (detected: {detected})."
            ),
        )

    def _eval_file_pattern(
        self,
        sig: dict[str, Any],
        profile: RepositoryProfile,
        workspace: Path | None,
    ) -> SignalResult:
        signal_id = sig.get("signal_id", "unknown")
        glob = sig.get("glob", "")
        confidence = float(sig.get("confidence", 0.8))
        result_status = sig.get("result_status", "SUPPORTED")

        if not glob:
            return SignalResult(
                signal_id=signal_id,
                kind="file_pattern",
                fired=False,
                result_status=None,
                confidence=0.0,
                reason="No glob pattern specified in signal definition.",
            )

        # Check against all source files in the profile
        all_files = [f for files in profile.source_files_by_language.values() for f in files]
        matched = any(fnmatch.fnmatch(f, glob) for f in all_files)

        return SignalResult(
            signal_id=signal_id,
            kind="file_pattern",
            fired=matched,
            result_status=result_status if matched else None,
            confidence=confidence if matched else 0.0,
            reason=(
                f"File pattern {glob!r} {'matched' if matched else 'not found'} "
                f"in source file list."
            ),
        )

    def _eval_code_pattern(self, sig: dict[str, Any], workspace: Path) -> SignalResult | None:
        """Evaluate import/text patterns by scanning workspace files with regex."""
        import re

        signal_id = sig.get("signal_id", "unknown")
        kind = sig.get("kind", "")
        confidence = float(sig.get("confidence", 0.8))
        result_status = sig.get("result_status")

        pattern_str = _pattern_for_code_signal(sig)
        if not pattern_str:
            return None

        try:
            pattern = re.compile(pattern_str, re.MULTILINE)
        except re.error as exc:
            logger.warning("Signal %r: invalid regex %r — %s", signal_id, pattern_str, exc)
            return None

        lang = self._pack.metadata.language
        extensions = _extensions_for_language(lang)

        for filepath in workspace.rglob("*"):
            if not filepath.is_file():
                continue
            if extensions and filepath.suffix not in extensions:
                continue
            if any(part.startswith(".") for part in filepath.parts):
                continue
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if pattern.search(content):
                return SignalResult(
                    signal_id=signal_id,
                    kind=kind,
                    fired=True,
                    result_status=result_status,
                    confidence=confidence,
                    reason=(f"Pattern {pattern_str!r} matched in {filepath.name}."),
                )

        return SignalResult(
            signal_id=signal_id,
            kind=kind,
            fired=False,
            result_status=None,
            confidence=0.0,
            reason=f"Pattern {pattern_str!r} not found in any {lang} source file.",
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self, signals: list[SignalResult], warnings: list[str]
    ) -> tuple[ApplicabilityStatus, float]:
        agg = self._config.aggregation
        na_threshold = float(agg.get("not_applicable_threshold", 0.9))
        supported_threshold = float(agg.get("supported_threshold", 0.9))
        default_status_str = agg.get("default_status", "PROBABLE_NEEDS_REVIEW")

        # Signals that fired and have a result_status
        fired = [s for s in signals if s.fired and s.result_status]

        # Highest-confidence NOT_APPLICABLE signal
        na_signals = [s for s in fired if s.result_status == "NOT_APPLICABLE"]
        if na_signals:
            best = max(na_signals, key=lambda s: s.confidence)
            if best.confidence >= na_threshold:
                return ApplicabilityStatus.NOT_APPLICABLE, best.confidence

        # Highest-confidence SUPPORTED signal
        sup_signals = [s for s in fired if s.result_status == "SUPPORTED"]
        if sup_signals:
            best = max(sup_signals, key=lambda s: s.confidence)
            if best.confidence >= supported_threshold:
                return ApplicabilityStatus.SUPPORTED, best.confidence

        # Fallback
        default_map = {
            "PROBABLE_NEEDS_REVIEW": ApplicabilityStatus.SUPPORTED,
            "NOT_APPLICABLE": ApplicabilityStatus.NOT_APPLICABLE,
            "SUPPORTED": ApplicabilityStatus.SUPPORTED,
        }
        avg_conf = (sum(s.confidence for s in fired) / len(fired)) if fired else 0.0
        status = default_map.get(default_status_str, ApplicabilityStatus.NOT_APPLICABLE)
        warnings.append(
            f"Applicability assessment fell back to default status {default_status_str!r} "
            f"(average signal confidence: {avg_conf:.2f})."
        )
        return status, avg_conf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _version_lt(v: str, bound: str) -> bool:
    """Return True if version v is strictly less than bound (major.minor compare)."""
    try:
        vp = tuple(int(x) for x in v.split(".")[:2])
        bp = tuple(int(x) for x in bound.split(".")[:2])
        return vp < bp
    except (ValueError, TypeError):
        return False


def _version_gte(v: str, bound: str) -> bool:
    """Return True if version v is >= bound (major.minor compare)."""
    try:
        vp = tuple(int(x) for x in v.split(".")[:2])
        bp = tuple(int(x) for x in bound.split(".")[:2])
        return vp >= bp
    except (ValueError, TypeError):
        return False


def _pattern_for_code_signal(sig: dict[str, Any]) -> str | None:
    """Extract or synthesize a regex pattern string from a code signal definition."""
    import re

    kind = sig.get("kind", "")
    pattern = sig.get("pattern")
    if pattern:
        return str(pattern)

    if kind == "import_symbol":
        module = sig.get("module", "")
        symbols = sig.get("symbols", [])
        if symbols:
            sym_re = "|".join(re.escape(s) for s in symbols)
            return rf"(?:from\s+{re.escape(module)}\s+import\s+(?:[^;]*?\b(?:{sym_re})\b))"
        return rf"\b{re.escape(module)}\b"

    if kind == "compat_namespace":
        prefix = sig.get("module_prefix", "")
        if prefix:
            return rf"\b{re.escape(prefix)}\b"

    return None


def _extensions_for_language(language: str) -> frozenset[str]:
    _MAP: dict[str, frozenset[str]] = {
        "python": frozenset({".py", ".pyi"}),
        "typescript": frozenset({".ts", ".tsx", ".js", ".jsx"}),
        "javascript": frozenset({".js", ".jsx", ".mjs", ".cjs"}),
        "go": frozenset({".go"}),
        "rust": frozenset({".rs"}),
        "java": frozenset({".java"}),
        "ruby": frozenset({".rb"}),
    }
    return _MAP.get(language.lower(), frozenset())
