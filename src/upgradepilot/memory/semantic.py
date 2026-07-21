"""
Semantic long-term memory for UpgradePilot findings.

Stores embeddings of past findings in Postgres (pgvector) so that when a
new analysis runs, the LLM agents receive similar past findings as context.

Flow:
  store_findings_embeddings(findings, analysis_id, repo_url)
      → embed each finding text → INSERT into finding_embeddings

  retrieve_similar_findings(finding_text, *, exclude_analysis_id, top_k)
      → embed query → cosine similarity search → return top_k rows
"""

from __future__ import annotations

import json
import os
from typing import Any

_TABLE_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS finding_embeddings (
    id              SERIAL PRIMARY KEY,
    analysis_id     TEXT        NOT NULL,
    finding_id      TEXT        NOT NULL,
    repository_url  TEXT        NOT NULL,
    rule_id         TEXT        NOT NULL,
    file            TEXT        NOT NULL DEFAULT '',
    severity        TEXT        NOT NULL DEFAULT 'medium',
    snippet         TEXT        NOT NULL DEFAULT '',
    interpretation  TEXT        NOT NULL DEFAULT '',
    embedding       vector(1536),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finding_embeddings_analysis
    ON finding_embeddings (analysis_id);
CREATE INDEX IF NOT EXISTS idx_finding_embeddings_vec
    ON finding_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
"""

_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIM = 1536


def _conn_string() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def _api_key() -> str:
    return os.environ.get("LLM_API_KEY", "")


def ensure_table() -> None:
    """Create pgvector extension and finding_embeddings table if not present."""
    import psycopg

    cs = _conn_string()
    if not cs:
        return
    with psycopg.connect(cs) as conn:
        conn.execute(_TABLE_DDL)
        conn.commit()


def _embed(texts: list[str]) -> list[list[float]]:
    """
    Call OpenAI embeddings API for a batch of texts.
    Returns a list of 1536-dim float vectors.
    """
    import httpx

    api_key = _api_key()
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set — cannot create embeddings")

    resp = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": _EMBED_MODEL, "input": texts},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # API returns items sorted by index
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


def _finding_text(finding: dict[str, Any]) -> str:
    """Build a rich text representation of a finding for embedding."""
    parts = [
        f"rule: {finding.get('rule_id', '')}",
        f"file: {finding.get('file', '')}",
        f"severity: {finding.get('severity', '')}",
        f"snippet: {finding.get('snippet') or finding.get('code_snippet', '')}",
    ]
    return " | ".join(p for p in parts if p.split(": ", 1)[1])


def store_findings_embeddings(
    findings: list[dict[str, Any]],
    *,
    analysis_id: str,
    repository_url: str,
    interpretation_map: dict[str, str] | None = None,
) -> int:
    """
    Embed all findings from a completed analysis and store in Postgres.

    interpretation_map: optional {finding_id: interpretation_text} so
    similar-finding retrieval can surface what was previously said about it.

    Returns the number of embeddings stored.
    """
    import psycopg
    from psycopg.types.json import Jsonb  # noqa: F401

    if not findings:
        return 0

    cs = _conn_string()
    if not cs or not _api_key():
        return 0

    texts = [_finding_text(f) for f in findings]

    try:
        vectors = _embed(texts)
    except Exception:
        return 0

    rows = []
    for finding, vec in zip(findings, vectors):
        fid = str(finding.get("finding_id", ""))
        interp = (interpretation_map or {}).get(fid, "")
        rows.append((
            analysis_id,
            fid,
            repository_url,
            str(finding.get("rule_id", "")),
            str(finding.get("file", "")),
            str(finding.get("severity", "medium")),
            str(finding.get("snippet") or finding.get("code_snippet", ""))[:2000],
            interp[:2000],
            json.dumps(vec),
        ))

    with psycopg.connect(cs) as conn:
        conn.executemany(  # type: ignore[attr-defined]
            """
            INSERT INTO finding_embeddings
                (analysis_id, finding_id, repository_url, rule_id,
                 file, severity, snippet, interpretation, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        conn.commit()

    return len(rows)


def retrieve_similar_findings(
    finding: dict[str, Any],
    *,
    exclude_analysis_id: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Find the top_k most similar past findings using cosine similarity.

    Excludes the current analysis so we don't retrieve our own findings.
    Returns list of dicts with rule_id, file, severity, snippet, interpretation.
    """
    import psycopg

    cs = _conn_string()
    if not cs or not _api_key():
        return []

    query_text = _finding_text(finding)
    try:
        vectors = _embed([query_text])
    except Exception:
        return []

    vec_str = json.dumps(vectors[0])

    with psycopg.connect(cs) as conn:
        rows = conn.execute(
            """
            SELECT rule_id, file, severity, snippet, interpretation,
                   repository_url,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM   finding_embeddings
            WHERE  analysis_id != %s
              AND  embedding IS NOT NULL
            ORDER  BY embedding <=> %s::vector
            LIMIT  %s
            """,
            (vec_str, exclude_analysis_id, vec_str, top_k),
        ).fetchall()

    return [
        {
            "rule_id": r[0],
            "file": r[1],
            "severity": r[2],
            "snippet": r[3],
            "interpretation": r[4],
            "repository_url": r[5],
            "similarity": round(float(r[6]), 3),
        }
        for r in rows
        if float(r[6]) > 0.75  # only return genuinely similar findings
    ]
