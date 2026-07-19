"""Unit tests for V2 Streamlit UI helper functions."""

from __future__ import annotations

from upgradepilot.ui.app import _delta_badge


def test_delta_badge_empty_when_no_delta():
    assert _delta_badge(None) == ""
    assert _delta_badge({}) == ""


def test_delta_badge_fixed_only():
    badge = _delta_badge({"fixed": [1, 2], "new": [], "still_open": []})
    assert "↓2 fixed" in badge
    assert "new" not in badge
    assert "open" not in badge


def test_delta_badge_new_only():
    badge = _delta_badge({"fixed": [], "new": [1], "still_open": []})
    assert "↑1 new" in badge
    assert "fixed" not in badge


def test_delta_badge_all_parts():
    badge = _delta_badge({"fixed": [1], "new": [2, 3], "still_open": [4, 5, 6]})
    assert "↓1 fixed" in badge
    assert "↑2 new" in badge
    assert "=3 open" in badge


def test_delta_badge_no_change_when_all_empty():
    badge = _delta_badge({"fixed": [], "new": [], "still_open": []})
    assert badge == "no change"


def test_delta_badge_parts_joined_with_separator():
    badge = _delta_badge({"fixed": [1], "new": [2], "still_open": []})
    assert "·" in badge
