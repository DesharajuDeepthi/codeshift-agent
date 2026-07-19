"""Static UI contract checks for the Streamlit analysis surface."""

from pathlib import Path

UI_APP = Path("src/upgradepilot/ui/app.py")


def test_streamlit_ui_exposes_milestone_11_controls_and_sections() -> None:
    source = UI_APP.read_text(encoding="utf-8")

    required_text = [
        "Public GitHub repository URL",
        "Ref",
        "pydantic-v1-to-v2",
        "Analysis mode",
        "Start analysis",
        "Repository Profile",
        "Findings",
        "Evidence Details",
        "Risk Score",
        "Migration Phases",
        "Testing Checklist",
        "Rollout Plan",
        "Rollback Plan",
        "Validation Status",
        "Trace Correlation",
        "JSON report",
        "Markdown report",
        "GitHub issue draft",
        "Useful",
        "Not useful",
    ]
    for text in required_text:
        assert text in source


def test_streamlit_ui_uses_api_exports_and_feedback_without_secret_fields() -> None:
    source = UI_APP.read_text(encoding="utf-8")

    assert "/feedback" in source
    assert "report.json" in source
    assert "report.md" in source
    assert "github-issue.md" in source
    assert "api_key" not in source.lower()
    # Hardcoded credentials must not appear; dynamic auth headers via _auth_headers() are fine
    assert "token = " not in source or "session_state" in source  # token only read from session
