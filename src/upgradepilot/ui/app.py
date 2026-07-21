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

# Browser-facing URL — used for links the user's browser must follow directly.
# Inside Docker the API is reachable as http://api:8000, but browsers can't
# resolve that hostname; PUBLIC_API_URL points to the host-accessible address.
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
JSON_REPORT_SUFFIX = "report.json"
MARKDOWN_REPORT_SUFFIX = "report.md"
GITHUB_ISSUE_SUFFIX = "github-issue.md"

# ---------------------------------------------------------------------------
# V2 Auth helpers
# ---------------------------------------------------------------------------

_AUTH_TOKEN_KEY = "auth_token"  # noqa: S105
_AUTH_LOGIN_KEY = "auth_login"


def _auth_headers() -> dict[str, str]:
    token = st.session_state.get(_AUTH_TOKEN_KEY)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _is_authenticated() -> bool:
    return bool(st.session_state.get(_AUTH_TOKEN_KEY))


def _handle_oauth_callback() -> None:
    """Store JWT from query params if the API redirected back here after OAuth."""
    params = st.query_params
    access_token = params.get("access_token")
    if not access_token:
        return
    # Clear all state so no stale analysis results show after fresh login
    st.session_state.clear()
    st.session_state[_AUTH_TOKEN_KEY] = access_token
    st.session_state[_AUTH_LOGIN_KEY] = params.get("login", "user")
    st.query_params.clear()
    st.rerun()


def _show_auth_sidebar() -> None:
    """Render login/logout controls in the sidebar."""
    st.sidebar.divider()
    if _is_authenticated():
        login = st.session_state.get(_AUTH_LOGIN_KEY, "user")
        st.sidebar.caption(f"Signed in as **{login}**")
        if st.sidebar.button("Sign out"):
            st.session_state.clear()
            st.rerun()
    else:
        login_url = f"{PUBLIC_API_URL}/auth/login"
        st.sidebar.markdown(f"[Login with GitHub]({login_url})", unsafe_allow_html=False)
        st.sidebar.caption("Sign in to track history and delta across runs.")


# ---------------------------------------------------------------------------
# V2 History helpers
# ---------------------------------------------------------------------------


def _delta_badge(delta: dict[str, Any] | None) -> str:
    """Format a compact delta badge string for the history sidebar."""
    if not delta:
        return ""
    fixed = len(delta.get("fixed") or [])
    new = len(delta.get("new") or [])
    still = len(delta.get("still_open") or [])
    parts = []
    if fixed:
        parts.append(f"↓{fixed} fixed")
    if new:
        parts.append(f"↑{new} new")
    if still:
        parts.append(f"={still} open")
    return " · ".join(parts) if parts else "no change"


def _show_history_sidebar() -> None:
    """Fetch and render the last 10 analyses for the authenticated user."""
    if not _is_authenticated():
        return
    try:
        resp = httpx.get(
            f"{API_BASE_URL}/analyses",
            headers=_auth_headers(),
            params={"limit": 10},
            timeout=10,
        )
        resp.raise_for_status()
        analyses: list[dict[str, Any]] = resp.json()
    except httpx.HTTPError:
        return

    st.sidebar.divider()
    st.sidebar.subheader("Recent analyses")
    if not analyses:
        st.sidebar.caption("No analyses yet.")
        return

    for item in analyses:
        aid = item.get("analysis_id", "")
        repo = item.get("repository_url", "")
        short_repo = repo.split("/")[-1] if "/" in repo else repo
        item_status = item.get("status", "")
        delta = item.get("delta")
        badge = _delta_badge(delta)
        label = f"{short_repo[:24]} [{item_status}]"
        if badge:
            label += f"\n{badge}"
        if st.sidebar.button(label, key=f"hist_{aid}"):
            st.session_state["analysis_id"] = aid
            st.rerun()


def _api(method: str, path: str, *, json_payload: object | None = None) -> httpx.Response:
    with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
        response = client.request(
            method,
            f"{API_BASE_URL}{path}",
            json=json_payload,
            headers=_auth_headers(),
        )
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

# Handle GitHub OAuth callback before any UI renders
_handle_oauth_callback()

st.title("UpgradePilot")
st.caption("Pydantic v1 to v2 migration intelligence")

# V2: auth + history sidebars
_show_auth_sidebar()
_show_history_sidebar()

with st.sidebar:
    st.header("Analysis")
    with st.form("analysis_form"):
        repository_url = st.text_input("Public GitHub repository URL")
        ref = st.text_input("Ref", value="main")
        st.text_input("Migration pack", value="pydantic-v1-to-v2", disabled=True)
        analysis_mode = st.selectbox("Analysis mode", ["standard", "fixture"], index=0)
        submitted = st.form_submit_button("Start analysis", type="primary")
    if submitted:
        try:
            response = _api(
                "POST",
                "/analyses",
                json_payload={
                    "repository_url": repository_url,
                    "ref": ref,
                    "migration_pack": "pydantic-v1-to-v2",
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
        st.caption(f"Stage: {status.get('current_stage') or 'queued'} | Status: {current_status}")
        if current_status == "running":
            _time.sleep(2)
            st.rerun()
        # V2: show delta badge if this run has a previous comparison
        analysis_meta = _safe_get(f"/analyses/{analysis_id}")
        if analysis_meta:
            delta = analysis_meta.get("delta")
            if delta:
                badge = _delta_badge(delta)
                st.info(f"Delta vs previous run: **{badge}**")

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
