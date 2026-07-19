"""User-facing report renderers for API downloads and GitHub issue drafts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from fastapi.encoders import jsonable_encoder

from upgradepilot.observability.redaction import sanitize_value

# User-facing reports must keep every field; only secrets are redacted and very
# long strings bounded. Evidence snippets are already bounded upstream (≤8 lines),
# so these generous limits exist purely as a redaction safety net — they must not
# drop report keys or list items the way trace-export sanitization does.
_REPORT_MAX_STRING_CHARS = 8_000
_REPORT_MAX_LINES = 400
_REPORT_MAX_COLLECTION_ITEMS = 2_000
_REPORT_MAX_DEPTH = 16


def safe_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe, secret-redacted copy of a report without dropping fields."""
    return cast(
        dict[str, Any],
        jsonable_encoder(
            sanitize_value(
                dict(report),
                max_string_chars=_REPORT_MAX_STRING_CHARS,
                max_lines=_REPORT_MAX_LINES,
                max_collection_items=_REPORT_MAX_COLLECTION_ITEMS,
                max_depth=_REPORT_MAX_DEPTH,
            )
        ),
    )


def report_json_bytes(report: Mapping[str, Any]) -> bytes:
    """Render a report as deterministic, redacted JSON bytes."""
    return json.dumps(safe_report(report), indent=2, sort_keys=True).encode("utf-8")


def render_markdown_report(report: Mapping[str, Any]) -> str:
    """Render the final report with facts, interpretations, and recommendations separated."""
    safe = safe_report(report)
    lines: list[str] = [
        "# UpgradePilot Analysis Report",
        "",
        "## Facts",
        f"- Analysis ID: `{_text(safe.get('analysis_id'))}`",
        f"- Status: `{_text(safe.get('status'))}`",
        f"- Repository: `{_text(safe.get('repository_url'))}`",
        f"- Requested ref: `{_text(safe.get('ref'))}`",
        f"- Resolved commit SHA: `{_text(safe.get('commit_sha'))}`",
        f"- Migration pack: `{_text(safe.get('migration_pack'))}`",
        f"- Migration pack version: `{_text(safe.get('migration_pack_version'))}`",
        f"- Applicability: `{_text(safe.get('applicability_status'))}`",
        "",
    ]
    lines.extend(_profile_lines(safe.get("profile")))
    lines.extend(_dependency_lines(safe.get("dependencies")))
    lines.extend(_finding_lines(safe.get("findings")))
    lines.extend(_documentation_lines(safe.get("documentation_evidence")))
    lines.extend(
        [
            "## Interpretations",
            _block(safe.get("interpretation"), "No interpretation was produced."),
            "",
            "## Recommendations",
            _plan_markdown(safe.get("plan_draft")),
            "",
            "## Risk",
            _block(safe.get("risk_assessment"), "No risk assessment was produced."),
            "",
            "## Validation",
            f"- Outcome: `{_text(safe.get('validation_outcome'))}`",
        ]
    )
    lines.extend(_validation_issue_lines(safe.get("validation_issues")))
    lines.extend(_warning_lines(safe))
    lines.extend(_observability_lines(safe.get("observability")))
    return "\n".join(lines).strip() + "\n"


def render_github_issue_body(report: Mapping[str, Any]) -> str:
    """Render a GitHub issue-body draft without claiming work was executed."""
    safe = safe_report(report)
    lines: list[str] = [
        "## UpgradePilot Migration Plan",
        "",
        f"Repository: `{_text(safe.get('repository_url'))}`",
        f"Commit: `{_text(safe.get('commit_sha'))}`",
        f"Migration pack: `{_text(safe.get('migration_pack'))}` "
        f"`{_text(safe.get('migration_pack_version'))}`",
        "",
        "### Summary",
        _summary_text(safe.get("plan_draft"), safe.get("interpretation")),
        "",
        "### Worklist",
    ]
    lines.extend(_file_worklist_lines(safe.get("plan_draft")))
    lines.extend(
        [
            "",
            "### Testing Checklist",
            _checklist(safe.get("plan_draft"), "testing_checklist"),
            "",
            "### Rollout Checklist",
            _checklist(safe.get("plan_draft"), "rollout_checklist"),
            "",
            "### Rollback Checklist",
            _checklist(safe.get("plan_draft"), "rollback_checklist"),
            "",
            "### Human Review",
            _checklist(safe.get("plan_draft"), "human_review_points"),
            "",
            "### Evidence",
        ]
    )
    lines.extend(_issue_evidence_lines(safe.get("findings"), safe.get("documentation_evidence")))
    lines.extend(
        [
            "",
            "_This draft is advisory. It does not claim that code was changed or tests passed._",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _items(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return []


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return {}


def _block(value: object, fallback: str) -> str:
    if not value:
        return fallback
    if isinstance(value, str):
        return value
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True, default=str) + "\n```"


def _profile_lines(profile: object) -> list[str]:
    data = _mapping(profile)
    if not data:
        return ["## Repository Profile", "No repository profile was produced.", ""]
    python_file_count = data.get("python_file_count") or len(_items(data.get("python_files")))
    test_files = _mapping(data.get("test_profile")).get("test_files")
    return [
        "## Repository Profile",
        f"- Python files: `{_text(python_file_count)}`",
        f"- Manifest files: `{len(_items(data.get('manifest_files')))} `",
        f"- Test files: `{len(_items(test_files))}`",
        f"- Profiler version: `{_text(data.get('profiler_version'))}`",
        "",
    ]


def _dependency_lines(dependencies: object) -> list[str]:
    lines = ["## Dependencies"]
    items = _items(dependencies)
    if not items:
        return [*lines, "No dependency records were produced.", ""]
    for item in items[:20]:
        dep = _mapping(item)
        name = dep.get("normalized_name") or dep.get("name") or "dependency"
        specifier = dep.get("specifier") or dep.get("version") or ""
        lines.append(f"- `{_text(name)}` {_text(specifier)}")
    if len(items) > 20:
        lines.append(f"- Additional dependency records omitted: `{len(items) - 20}`")
    lines.append("")
    return lines


def _finding_lines(findings: object) -> list[str]:
    lines = ["## Findings"]
    items = _items(findings)
    if not items:
        return [*lines, "No deterministic findings were produced.", ""]
    for item in items[:50]:
        finding = _mapping(item)
        location = _mapping(finding.get("location"))
        evidence = _mapping(finding.get("evidence"))
        path = location.get("file_path") or finding.get("file_path") or ""
        line = location.get("start_line") or finding.get("line_number") or ""
        snippet = evidence.get("snippet") or finding.get("snippet") or ""
        lines.append(
            f"- `{_text(finding.get('finding_id'))}` `{_text(finding.get('rule_id'))}` "
            f"{_text(path)}:{_text(line)}"
        )
        if snippet:
            lines.append(f"  - Snippet: `{_text(snippet)}`")
    lines.append("")
    return lines


def _documentation_lines(evidence: object) -> list[str]:
    lines = ["## Documentation Evidence"]
    items = _items(evidence)
    if not items:
        return [*lines, "No documentation evidence was available.", ""]
    for item in items[:30]:
        doc = _mapping(item)
        source = doc.get("source_id") or doc.get("source_url") or doc.get("canonical_url")
        cache = doc.get("cache_status") or doc.get("retrieval_status")
        freshness = doc.get("source_freshness") or doc.get("retrieved_at")
        lines.append(f"- `{_text(doc.get('evidence_id'))}` source `{_text(source)}`")
        lines.append(f"  - Retrieval: `{_text(cache)}`; freshness: `{_text(freshness)}`")
        excerpt = doc.get("bounded_excerpt") or doc.get("excerpt")
        if excerpt:
            lines.append(f"  - Excerpt: `{_text(excerpt)}`")
    lines.append("")
    return lines


def _plan_markdown(plan: object) -> str:
    data = _mapping(plan)
    if not data:
        return "No migration plan was produced."
    preferred = [
        "executive_summary",
        "impact_summary",
        "migration_phases",
        "file_worklist",
        "dependency_actions",
        "testing_checklist",
        "rollout_checklist",
        "rollback_checklist",
        "assumptions",
        "gaps",
        "human_review_points",
    ]
    lines: list[str] = []
    for key in preferred:
        if key in data and data[key]:
            lines.append(f"### {key.replace('_', ' ').title()}")
            lines.append(_block(data[key], ""))
            lines.append("")
    return "\n".join(lines).strip() or _block(data, "No migration plan was produced.")


def _validation_issue_lines(issues: object) -> list[str]:
    items = _items(issues)
    if not items:
        return ["- Issues: none", ""]
    lines = ["- Issues:"]
    for item in items[:30]:
        issue = _mapping(item)
        lines.append(
            f"  - `{_text(issue.get('issue_type') or issue.get('code'))}` "
            f"{_text(issue.get('message'))}"
        )
    lines.append("")
    return lines


def _warning_lines(report: Mapping[str, Any]) -> list[str]:
    warnings = _items(report.get("warnings"))
    limitations = _items(report.get("limitations"))
    if not warnings and not limitations:
        return ["## Partial Or Degraded Warnings", "None.", ""]
    lines = ["## Partial Or Degraded Warnings"]
    for item in [*warnings, *limitations]:
        lines.append(f"- {_text(item)}")
    lines.append("")
    return lines


def _observability_lines(observability: object) -> list[str]:
    data = _mapping(observability)
    if not data:
        return ["## Trace Correlation", "Tracing metadata was not available.", ""]
    return [
        "## Trace Correlation",
        f"- Trace ID: `{_text(data.get('trace_id'))}`",
        f"- Root run ID: `{_text(data.get('langsmith_root_run_id'))}`",
        f"- Status: `{_text(data.get('status'))}`",
        f"- Submitted: `{_text(data.get('langsmith_submitted'))}`",
        f"- Trace URL: `{_text(data.get('trace_url'))}`",
        "",
    ]


def _summary_text(plan: object, interpretation: object) -> str:
    plan_data = _mapping(plan)
    summary = plan_data.get("executive_summary") or plan_data.get("impact_summary")
    if summary:
        return _text(summary)
    return _text(interpretation) if interpretation else "Review the listed findings and evidence."


def _file_worklist_lines(plan: object) -> list[str]:
    data = _mapping(plan)
    items = _items(data.get("file_worklist"))
    if not items:
        return ["- [ ] Review deterministic findings and linked evidence."]
    lines: list[str] = []
    for item in items[:30]:
        work = _mapping(item)
        label = work.get("file_path") or work.get("path") or item
        lines.append(f"- [ ] {_text(label)}")
    return lines


def _checklist(plan: object, key: str) -> str:
    data = _mapping(plan)
    items = _items(data.get(key))
    if not items:
        return "- [ ] Review required actions."
    return "\n".join(f"- [ ] {_text(item)}" for item in items[:30])


def _issue_evidence_lines(findings: object, docs: object) -> list[str]:
    lines: list[str] = []
    for item in _items(findings)[:20]:
        finding = _mapping(item)
        lines.append(
            f"- Finding `{_text(finding.get('finding_id'))}` cites rule "
            f"`{_text(finding.get('rule_id'))}`."
        )
    for item in _items(docs)[:20]:
        doc = _mapping(item)
        lines.append(
            f"- Documentation `{_text(doc.get('evidence_id'))}` from "
            f"`{_text(doc.get('source_id') or doc.get('canonical_url'))}`."
        )
    if not lines:
        lines.append("- Evidence was unavailable or the analysis ended before evidence retrieval.")
    return lines
