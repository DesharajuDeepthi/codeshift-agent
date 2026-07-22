"""Cross-analysis findings persistence and delta computation.

FindingsStore wraps an async connection pool (psycopg3) and exposes:
- persist_analysis: write findings rows + update analyses metadata
- delta_vs_previous: compare content hashes against the prior run
- rule_frequency: fleet-wide rule hit rate for a pack
- history_for_repo: chronological list of past analyses for a repo
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from upgradepilot.models.finding import MigrationFinding

# ---------------------------------------------------------------------------
# Public models
# ---------------------------------------------------------------------------


class FindingsDelta(BaseModel):
    previous_analysis_id: str | None = None
    previous_commit_sha: str | None = None
    previous_completed_at: datetime | None = None
    new_count: int = 0
    resolved_count: int = 0
    unchanged_count: int = 0
    new_rule_ids: list[str] = []
    resolved_rule_ids: list[str] = []


class RuleFrequency(BaseModel):
    rule_id: str
    pack_id: str
    repo_count: int
    total_repos: int
    frequency: float


class PackStats(BaseModel):
    pack_id: str
    total_repos_analysed: int
    rules: list[RuleFrequency]


# ---------------------------------------------------------------------------
# Connection pool protocol — lets unit tests inject a stub
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Content-address helper
# ---------------------------------------------------------------------------


def _content_hash(
    pack_id: str,
    rule_id: str,
    file: str,
    line_start: int,
    symbol: str,
) -> str:
    raw = f"{pack_id}|{rule_id}|{file}|{line_start}|{symbol}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# FindingsStore
# ---------------------------------------------------------------------------


class FindingsStore:
    def __init__(self, pool: Any) -> None:  # noqa: ANN401
        self._pool = pool

    async def persist_analysis(
        self,
        analysis_id: str,
        pack_id: str,
        pack_version: str,
        report_status: str,
        owner: str,
        repo: str,
        commit_sha: str,
        findings: list[MigrationFinding],
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                UPDATE analyses
                SET pack_id       = $1,
                    pack_version  = $2,
                    report_status = $3,
                    owner         = $4,
                    repo          = $5,
                    commit_sha    = COALESCE(commit_sha, $6)
                WHERE analysis_id = $7
                """,
                pack_id,
                pack_version,
                report_status,
                owner,
                repo,
                commit_sha,
                uuid.UUID(analysis_id),
            )
            if findings:
                rows = [
                    (
                        uuid.UUID(f.finding_id),
                        uuid.UUID(analysis_id),
                        f.pack_id,
                        f.pack_version,
                        f.rule_id,
                        f.category,
                        f.severity,
                        f.file,
                        f.line_start,
                        f.line_end,
                        f.symbol,
                        f.confidence,
                        f.match_kind,
                        _content_hash(f.pack_id, f.rule_id, f.file, f.line_start, f.symbol),
                    )
                    for f in findings
                ]
                await conn.executemany(
                    """
                    INSERT INTO findings (
                        finding_id, analysis_id, pack_id, pack_version,
                        rule_id, category, severity,
                        file, line_start, line_end, symbol,
                        confidence, match_kind, content_hash
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7,
                        $8, $9, $10, $11, $12, $13, $14
                    )
                    ON CONFLICT (finding_id) DO NOTHING
                    """,
                    rows,
                )

    async def delta_vs_previous(
        self,
        owner: str,
        repo: str,
        current_analysis_id: str,
    ) -> FindingsDelta:
        async with self._pool.connection() as conn:
            prev_row = await conn.fetchrow(
                """
                SELECT analysis_id, commit_sha, completed_at
                FROM analyses
                WHERE owner = $1
                  AND repo  = $2
                  AND report_status = 'validated'
                  AND analysis_id != $3
                ORDER BY created_at DESC
                LIMIT 1
                """,
                owner,
                repo,
                uuid.UUID(current_analysis_id),
            )
            if prev_row is None:
                return FindingsDelta()

            prev_id: uuid.UUID = prev_row["analysis_id"]

            current_hashes: set[str] = {
                row["content_hash"]
                async for row in conn.cursor(
                    "SELECT content_hash FROM findings WHERE analysis_id = $1",
                    uuid.UUID(current_analysis_id),
                )
            }
            prev_hashes: set[str] = {
                row["content_hash"]
                async for row in conn.cursor(
                    "SELECT content_hash FROM findings WHERE analysis_id = $1",
                    prev_id,
                )
            }

            new_hashes = current_hashes - prev_hashes
            resolved_hashes = prev_hashes - current_hashes
            unchanged = current_hashes & prev_hashes

            new_rule_ids = await _rule_ids_for_hashes(
                conn, uuid.UUID(current_analysis_id), new_hashes
            )
            resolved_rule_ids = await _rule_ids_for_hashes(conn, prev_id, resolved_hashes)

            return FindingsDelta(
                previous_analysis_id=str(prev_id),
                previous_commit_sha=prev_row["commit_sha"],
                previous_completed_at=prev_row["completed_at"],
                new_count=len(new_hashes),
                resolved_count=len(resolved_hashes),
                unchanged_count=len(unchanged),
                new_rule_ids=new_rule_ids,
                resolved_rule_ids=resolved_rule_ids,
            )

    async def rule_frequency(self, pack_id: str) -> PackStats:
        async with self._pool.connection() as conn:
            total_row = await conn.fetchrow(
                """
                SELECT COUNT(DISTINCT COALESCE(owner || '/' || repo, analysis_id::text))
                       AS total_repos
                FROM analyses
                WHERE pack_id = $1
                  AND report_status = 'validated'
                """,
                pack_id,
            )
            total_repos: int = total_row["total_repos"] if total_row else 0

            rows = await conn.fetch(
                """
                SELECT f.rule_id,
                       COUNT(DISTINCT a.analysis_id) AS repo_count
                FROM findings f
                JOIN analyses a ON a.analysis_id = f.analysis_id
                WHERE f.pack_id = $1
                  AND a.report_status = 'validated'
                GROUP BY f.rule_id
                ORDER BY repo_count DESC
                """,
                pack_id,
            )
            rules = [
                RuleFrequency(
                    rule_id=row["rule_id"],
                    pack_id=pack_id,
                    repo_count=row["repo_count"],
                    total_repos=total_repos,
                    frequency=row["repo_count"] / total_repos if total_repos else 0.0,
                )
                for row in rows
            ]
            return PackStats(
                pack_id=pack_id,
                total_repos_analysed=total_repos,
                rules=rules,
            )

    async def history_for_repo(
        self,
        owner: str,
        repo: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT a.analysis_id,
                       a.commit_sha,
                       a.report_status,
                       a.completed_at,
                       COUNT(f.finding_id) AS finding_count
                FROM analyses a
                LEFT JOIN findings f ON f.analysis_id = a.analysis_id
                WHERE a.owner = $1 AND a.repo = $2
                GROUP BY a.analysis_id, a.commit_sha, a.report_status, a.completed_at
                ORDER BY a.created_at DESC
                LIMIT $3
                """,
                owner,
                repo,
                limit,
            )
            return [
                {
                    "analysis_id": str(row["analysis_id"]),
                    "commit_sha": row["commit_sha"],
                    "report_status": row["report_status"],
                    "finding_count": row["finding_count"],
                    "completed_at": row["completed_at"].isoformat()
                    if row["completed_at"]
                    else None,
                }
                for row in rows
            ]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _rule_ids_for_hashes(
    conn: Any,  # noqa: ANN401
    analysis_id: uuid.UUID,
    hashes: set[str],
) -> list[str]:
    if not hashes:
        return []
    rows = await conn.fetch(
        "SELECT DISTINCT rule_id FROM findings WHERE analysis_id = $1 AND content_hash = ANY($2)",
        analysis_id,
        list(hashes),
    )
    return sorted(row["rule_id"] for row in rows)
