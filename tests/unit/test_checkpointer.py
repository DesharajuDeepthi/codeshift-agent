"""Tests for LangGraph checkpointer factories."""

from __future__ import annotations

from upgradepilot.graph.checkpointer import psycopg_connection_string


def test_psycopg_connection_string_accepts_plain_postgres_url() -> None:
    url = "postgresql://user:pass@localhost:5432/db"

    assert psycopg_connection_string(url) == url


def test_psycopg_connection_string_normalizes_sqlalchemy_driver_url() -> None:
    url = "postgresql+psycopg://user:pass@postgres:5432/db"

    assert psycopg_connection_string(url) == "postgresql://user:pass@postgres:5432/db"
