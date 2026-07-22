"""Streamlit UI for UpgradePilot analyses."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, cast

import httpx
import streamlit as st

API_BASE_URL = os.getenv(
    "UPGRADEPILOT_API_URL",
    os.getenv("API_URL", "http://localhost:8000"),
).rstrip("/")
JSON_REPORT_SUFFIX = "report.json"
MARKDOWN_REPORT_SUFFIX = "report.md"
GITHUB_ISSUE_SUFFIX = "github-issue.md"


def _api(method: str, path: str, *, json_payload: object | None = None) -> httpx.Response:
    with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
        response = client.request(method, f"{API_BASE_URL}{path}", json=json_payload)
        response.raise_for_status()
        return response


def _safe_get(path: str) -> dict[str, Any] | None:
    try:
        body = _api("GET", path).json()
        return cast(dict[str, Any], body) if isinstance(body, dict) else None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            return None
        st.warning("The analysis is not ready yet.")
    except httpx.HTTPError:
        st.error("UpgradePilot API is unavailable. Check that the FastAPI service is running.")
    return None


def _as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    return []


def _post_feedback(analysis_id: str, useful: bool, comment: str) -> None:
    try:
        payload = {
            "key": "useful" if useful else "not_useful",
            "score": useful,
            "value": {"source": "streamlit"},
            "comment": comment or None,
        }
        response = _api("POST", f"/analyses/{analysis_id}/feedback", json_payload=payload).json()
        if response.get("attached"):
            st.success("Feedback attached to the analysis trace.")
        else:
            st.info(
                "Feedback saved locally for this response; no active LangSmith trace was available."
            )
    except httpx.HTTPError:
        st.warning("Feedback could not be submitted right now.")


def _show_facts(report: dict[str, Any]) -> None:
    profile = _as_dict(report.get("profile"))
    observability = _as_dict(report.get("observability"))
    cols = st.columns(4)
    cols[0].metric("Status", str(report.get("status") or "unknown"))
    cols[1].metric("Applicability", str(report.get("applicability_status") or "unknown"))
    cols[2].metric("Migration Pack", str(report.get("migration_pack_version") or "unknown"))
    cols[3].metric("Trace", str(observability.get("status") or "disabled"))
    st.text_input("Resolved commit SHA", value=str(report.get("commit_sha") or ""), disabled=True)
    with st.expander("Repository Profile", expanded=True):
        st.json(
            {
                "python_files": profile.get("python_file_count")
                or len(_as_list(profile.get("python_files"))),
                "manifests": len(_as_list(profile.get("manifest_files"))),
                "tests": len(_as_list(_as_dict(profile.get("test_profile")).get("test_files"))),
                "profiler_version": profile.get("profiler_version"),
            }
        )


def _show_findings(report: dict[str, Any]) -> None:
    findings = _as_list(report.get("findings"))
    st.subheader("Findings")
    if not findings:
        st.info("No deterministic findings were produced.")
        return
    rows = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        location = _as_dict(finding.get("location"))
        rows.append(
            {
                "finding_id": finding.get("finding_id"),
                "rule_id": finding.get("rule_id"),
                "severity": finding.get("severity"),
                "file": location.get("file_path") or finding.get("file_path"),
                "line": location.get("start_line") or finding.get("line_number"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    with st.expander("Evidence Details"):
        st.json(findings)


def _show_evidence(report: dict[str, Any]) -> None:
    docs = _as_list(report.get("documentation_evidence"))
    st.subheader("Documentation Evidence")
    if not docs:
        st.info("No official documentation evidence was available.")
        return
    for item in docs:
        if not isinstance(item, dict):
            continue
        st.markdown(f"**{item.get('evidence_id') or 'evidence'}**")
        st.caption(
            f"Source: {item.get('source_id') or item.get('canonical_url') or 'unknown'} | "
            f"Retrieval: {item.get('cache_status') or item.get('retrieval_status') or 'unknown'} | "
            f"Freshness: {item.get('source_freshness') or item.get('retrieved_at') or 'unknown'}"
        )
        excerpt = item.get("bounded_excerpt") or item.get("excerpt")
        if excerpt:
            st.code(str(excerpt), language="text")


def _show_interpretations(report: dict[str, Any]) -> None:
    st.subheader("Risk Score")
    st.json(report.get("risk_assessment") or {})
    st.subheader("Compatibility Interpretation")
    interpretation = report.get("interpretation")
    if isinstance(interpretation, str):
        st.write(interpretation)
    else:
        st.json(interpretation or {})


def _show_recommendations(report: dict[str, Any]) -> None:
    plan = _as_dict(report.get("plan_draft"))
    if not plan:
        st.info("No migration plan was produced.")
        return

    # Executive summary
    summary = plan.get("executive_summary") or plan.get("impact_summary")
    if summary:
        st.subheader("Executive Summary")
        st.write(summary)

    # Migration phases
    phases = _as_list(plan.get("migration_phases") or plan.get("phases"))
    if phases:
        st.subheader("Migration Phases")
        for i, phase in enumerate(phases, 1):
            p = phase if isinstance(phase, dict) else {"description": str(phase)}
            with st.expander(
                f"Phase {i}: {p.get('name', p.get('phase', 'Phase'))}", expanded=i == 1
            ):
                st.write(p.get("description") or p.get("summary") or "")
                files = _as_list(p.get("file_paths") or p.get("steps"))
                for f in files:
                    st.write(f"- `{f}`")

    # File worklist
    worklist = _as_list(plan.get("file_worklist"))
    if worklist:
        st.subheader("File Worklist")
        rows = []
        for item in worklist:
            w = item if isinstance(item, dict) else {"path": str(item)}
            rows.append(
                {
                    "file": w.get("file_path") or w.get("path") or "",
                    "priority": w.get("priority") or w.get("change_type") or "",
                    "findings": w.get("findings_count") or "",
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)

    # Dependency actions
    dep_actions = _as_list(plan.get("dependency_actions"))
    if dep_actions:
        st.subheader("Dependency Actions")
        for item in dep_actions:
            st.write(
                f"- {item}"
                if isinstance(item, str)
                else f"- {item.get('action', '')}: `{item.get('package', '')}`"
            )

    # Checklists
    for label, key in (
        ("Testing Checklist", "testing_checklist"),
        ("Rollout Plan", "rollout_checklist"),
        ("Rollback Plan", "rollback_checklist"),
        ("Assumptions", "assumptions"),
        ("Gaps", "gaps"),
        ("Human Review Points", "human_review_points"),
    ):
        items = _as_list(plan.get(key))
        with st.expander(label, expanded=key in {"testing_checklist", "gaps"}):
            if items:
                for item in items:
                    st.write(f"- {item}")
            else:
                st.info("No entries were produced.")


def _show_validation(report: dict[str, Any]) -> None:
    st.subheader("Validation Status")
    st.write(report.get("validation_outcome") or "not_run")
    issues = _as_list(report.get("validation_issues"))
    if issues:
        st.dataframe(issues, use_container_width=True)
    warnings = [*_as_list(report.get("warnings")), *_as_list(report.get("limitations"))]
    if warnings:
        st.warning("\n".join(str(item) for item in warnings))
    observability = _as_dict(report.get("observability"))
    st.subheader("Trace Correlation")
    st.json(
        {
            "trace_id": observability.get("trace_id"),
            "root_run_id": observability.get("langsmith_root_run_id"),
            "status": observability.get("status"),
            "submitted": observability.get("langsmith_submitted"),
            "trace_url": observability.get("trace_url"),
        }
    )


def _show_exports(analysis_id: str, report: dict[str, Any]) -> None:
    st.subheader("Exports")
    markdown = _download_text(analysis_id, MARKDOWN_REPORT_SUFFIX)
    issue = _download_text(analysis_id, GITHUB_ISSUE_SUFFIX)
    st.download_button(
        "JSON report",
        data=_api("GET", f"/analyses/{analysis_id}/{JSON_REPORT_SUFFIX}").content,
        file_name=f"{analysis_id}.json",
        mime="application/json",
    )
    st.download_button(
        "Markdown report",
        data=markdown,
        file_name=f"{analysis_id}.md",
        mime="text/markdown",
    )
    st.download_button(
        "GitHub issue draft",
        data=issue,
        file_name=f"{analysis_id}-issue.md",
        mime="text/markdown",
    )
    st.caption(f"Report status: {report.get('status') or 'unknown'}")


def _download_text(analysis_id: str, suffix: str) -> str:
    try:
        return _api("GET", f"/analyses/{analysis_id}/{suffix}").text
    except httpx.HTTPError:
        return ""


st.set_page_config(page_title="UpgradePilot", layout="wide")
st.title("UpgradePilot")
st.caption("Agentic migration intelligence — any language, any framework")

# Fetch available packs once per session and cache them.
if "available_packs" not in st.session_state:
    try:
        resp = _api("GET", "/packs").json()
        st.session_state["available_packs"] = resp.get("packs", [])
    except httpx.HTTPError:
        st.session_state["available_packs"] = []

_pack_list: list[dict[str, Any]] = st.session_state.get("available_packs", [])
_AUTO_DETECT_LABEL = "Auto-detect (recommended)"
_pack_options = [_AUTO_DETECT_LABEL] + [f"{p['display_name']} ({p['pack_id']})" for p in _pack_list]

with st.sidebar:
    st.header("Analysis")
    with st.form("analysis_form"):
        repository_url = st.text_input("Public GitHub repository URL")
        ref = st.text_input("Ref", value="main")
        pack_selection = st.selectbox("Migration pack", options=_pack_options, index=0)
        analysis_mode = st.selectbox("Analysis mode", ["standard", "fixture"], index=0)
        submitted = st.form_submit_button("Start analysis", type="primary")
    if submitted:
        # Resolve pack_id: None triggers auto-detect in the graph.
        if pack_selection == _AUTO_DETECT_LABEL:
            pack_id_payload: str | None = None
        else:
            pack_id_payload = pack_selection.split("(")[-1].rstrip(")")
        try:
            response = _api(
                "POST",
                "/analyses",
                json_payload={
                    "repository_url": repository_url,
                    "ref": ref,
                    "migration_pack": pack_id_payload,
                    "analysis_mode": analysis_mode,
                },
            ).json()
            st.session_state["analysis_id"] = response["analysis_id"]
            st.success("Analysis started.")
        except httpx.HTTPStatusError as exc:
            st.error(exc.response.json().get("detail", "The request was rejected."))
        except httpx.HTTPError:
            st.error("UpgradePilot API is unavailable. Check that the FastAPI service is running.")

analysis_id = st.session_state.get("analysis_id")
if not analysis_id:
    st.info("Enter a public GitHub repository URL to start an analysis.")
else:
    import time as _time

    status = _safe_get(f"/analyses/{analysis_id}")
    if status:
        current_status = status.get("status") or "unknown"
        st.progress(float(status.get("progress") or 0.0))
        pack_label = status.get("migration_pack") or "auto-detecting…"
        st.caption(
            f"Stage: {status.get('current_stage') or 'queued'} | "
            f"Status: {current_status} | "
            f"Pack: {pack_label}"
        )
        if current_status == "running":
            _time.sleep(2)
            st.rerun()
        report = _safe_get(f"/analyses/{analysis_id}/report")
        if report:
            facts, evidence, interpretation, recommendations, validation, exports = st.tabs(
                [
                    "Facts",
                    "Evidence",
                    "Interpretations",
                    "Recommendations",
                    "Validation",
                    "Exports",
                ]
            )
            with facts:
                _show_facts(report)
                _show_findings(report)
            with evidence:
                _show_evidence(report)
            with interpretation:
                _show_interpretations(report)
            with recommendations:
                _show_recommendations(report)
            with validation:
                _show_validation(report)
            with exports:
                _show_exports(str(analysis_id), report)
            st.subheader("Feedback")
            comment = st.text_area("Comment", max_chars=2000)
            col_yes, col_no = st.columns(2)
            if col_yes.button("Useful"):
                _post_feedback(str(analysis_id), True, comment)
            if col_no.button("Not useful"):
                _post_feedback(str(analysis_id), False, comment)
