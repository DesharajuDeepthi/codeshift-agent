"""Unit tests for FindingsStore using an in-memory stub connection pool."""

from __future__ import annotations

import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from upgradepilot.models.finding import MatchKind, MigrationFinding
from upgradepilot.services.findings_store import (
    FindingsStore,
    _content_hash,
)

# ---------------------------------------------------------------------------
# In-memory stub that mimics psycopg3 async connection pool
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self, db: _StubDB) -> None:
        self._db = db
        self._executed: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, sql: str, *args: Any) -> None:
        self._db._execute(sql, args)

    async def executemany(self, sql: str, rows: list[Any]) -> None:
        for row in rows:
            self._db._execute(sql, tuple(row))

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        return self._db._fetchrow(sql, args)

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        return self._db._fetch(sql, args)

    async def cursor(self, sql: str, *args: Any):  # type: ignore[return]
        for row in self._db._fetch(sql, args):
            yield row


class _StubDB:
    """Minimal in-memory store mirroring the SQL schema."""

    def __init__(self) -> None:
        # analyses: analysis_id -> dict
        self.analyses: dict[str, dict[str, Any]] = {}
        # findings: list of dicts
        self.findings: list[dict[str, Any]] = []

    def seed_analysis(
        self,
        analysis_id: str,
        *,
        owner: str = "acme",
        repo: str = "myapp",
        pack_id: str = "pydantic-v1-to-v2",
        pack_version: str = "1.0.0",
        report_status: str = "validated",
        commit_sha: str = "abc123",
        created_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        self.analyses[analysis_id] = {
            "analysis_id": uuid.UUID(analysis_id),
            "owner": owner,
            "repo": repo,
            "pack_id": pack_id,
            "pack_version": pack_version,
            "report_status": report_status,
            "commit_sha": commit_sha,
            "created_at": created_at or datetime.now(UTC),
            "completed_at": completed_at or datetime.now(UTC),
        }

    def seed_finding(
        self,
        analysis_id: str,
        rule_id: str,
        content_hash: str,
        pack_id: str = "pydantic-v1-to-v2",
    ) -> None:
        self.findings.append(
            {
                "finding_id": uuid.uuid4(),
                "analysis_id": uuid.UUID(analysis_id),
                "rule_id": rule_id,
                "content_hash": content_hash,
                "pack_id": pack_id,
            }
        )

    # ------------------------------------------------------------------
    # SQL dispatcher — maps SQL fragments to in-memory operations
    # ------------------------------------------------------------------

    def _execute(self, sql: str, args: tuple[Any, ...]) -> None:
        sql_u = sql.upper()
        if "UPDATE ANALYSES" in sql_u:
            (pack_id, pack_version, report_status, owner, repo, commit_sha, analysis_id) = args
            aid = str(analysis_id)
            if aid not in self.analyses:
                self.analyses[aid] = {"analysis_id": analysis_id}
            rec = self.analyses[aid]
            rec["pack_id"] = pack_id
            rec["pack_version"] = pack_version
            rec["report_status"] = report_status
            rec["owner"] = owner
            rec["repo"] = repo
            rec["commit_sha"] = commit_sha
        elif "INSERT INTO FINDINGS" in sql_u:
            (
                finding_id,
                analysis_id,
                pack_id,
                pack_version,
                rule_id,
                category,
                severity,
                file,
                line_start,
                line_end,
                symbol,
                confidence,
                match_kind,
                content_hash,
            ) = args
            # honour ON CONFLICT DO NOTHING
            if not any(str(f["finding_id"]) == str(finding_id) for f in self.findings):
                self.findings.append(
                    {
                        "finding_id": finding_id,
                        "analysis_id": analysis_id,
                        "pack_id": pack_id,
                        "rule_id": rule_id,
                        "content_hash": content_hash,
                    }
                )

    def _fetchrow(self, sql: str, args: tuple[Any, ...]) -> dict[str, Any] | None:
        sql_u = sql.upper()
        if "TOTAL_REPOS" in sql_u:
            pack_id = args[0]
            count = len(
                {
                    a["analysis_id"]
                    for a in self.analyses.values()
                    if a.get("pack_id") == pack_id and a.get("report_status") == "validated"
                }
            )
            return {"total_repos": count}
        if "FROM ANALYSES" in sql_u and "REPORT_STATUS = 'VALIDATED'" in sql_u:
            owner, repo, exclude_id = args
            rows = [
                a
                for a in self.analyses.values()
                if a.get("owner") == owner
                and a.get("repo") == repo
                and a.get("report_status") == "validated"
                and str(a["analysis_id"]) != str(exclude_id)
            ]
            if not rows:
                return None
            rows.sort(key=lambda r: r.get("created_at", datetime.min), reverse=True)
            return rows[0]
        return None

    def _fetch(self, sql: str, args: tuple[Any, ...]) -> list[dict[str, Any]]:
        sql_u = sql.upper()
        if "RULE_ID" in sql_u and "CONTENT_HASH = ANY" in sql_u:
            analysis_id, hashes = args
            return [
                {"rule_id": f["rule_id"]}
                for f in self.findings
                if str(f["analysis_id"]) == str(analysis_id) and f["content_hash"] in hashes
            ]
        if "CONTENT_HASH" in sql_u and "ANALYSIS_ID = $1" in sql_u:
            analysis_id = args[0]
            return [
                {"content_hash": f["content_hash"]}
                for f in self.findings
                if str(f["analysis_id"]) == str(analysis_id)
            ]
        if "RULE_ID" in sql_u and "GROUP BY" in sql_u:
            pack_id = args[0]
            counts: dict[str, int] = defaultdict(int)
            for f in self.findings:
                aid = str(f["analysis_id"])
                a = self.analyses.get(aid, {})
                if f.get("pack_id") == pack_id and a.get("report_status") == "validated":
                    counts[f["rule_id"]] += 1
            return [{"rule_id": rid, "repo_count": cnt} for rid, cnt in counts.items()]
        if "A.OWNER" in sql_u and "A.REPO" in sql_u:
            owner, repo, limit = args
            rows = []
            for aid, a in self.analyses.items():
                if a.get("owner") == owner and a.get("repo") == repo:
                    fc = sum(1 for f in self.findings if str(f["analysis_id"]) == aid)
                    rows.append(
                        {
                            "analysis_id": a["analysis_id"],
                            "commit_sha": a.get("commit_sha"),
                            "report_status": a.get("report_status"),
                            "finding_count": fc,
                            "completed_at": a.get("completed_at"),
                        }
                    )
            rows.sort(
                key=lambda r: self.analyses[str(r["analysis_id"])].get("created_at", datetime.min),
                reverse=True,
            )
            return rows[:limit]
        return []


class _StubPool:
    def __init__(self, db: _StubDB) -> None:
        self._db = db

    @asynccontextmanager
    async def connection(self):  # type: ignore[return]
        yield _StubConn(self._db)


def _make_finding(
    rule_id: str = "PYD001",
    pack_id: str = "pydantic-v1-to-v2",
    file: str = "models.py",
    line_start: int = 10,
    symbol: str = "@validator",
) -> MigrationFinding:
    return MigrationFinding(
        rule_id=rule_id,
        pack_id=pack_id,
        pack_version="1.0.0",
        category="validator",
        severity="warning",
        file=file,
        line_start=line_start,
        line_end=line_start,
        evidence="@validator('name')",
        symbol=symbol,
        migration_concept="field_validator",
        source_ids=[],
        detector="ast",
        detector_version="1.0",
        confidence=0.95,
        match_kind=MatchKind.AST,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_stable_across_calls(self) -> None:
        h1 = _content_hash("pydantic-v1-to-v2", "PYD001", "models.py", 10, "@validator")
        h2 = _content_hash("pydantic-v1-to-v2", "PYD001", "models.py", 10, "@validator")
        assert h1 == h2

    def test_different_rule_different_hash(self) -> None:
        h1 = _content_hash("pydantic-v1-to-v2", "PYD001", "models.py", 10, "@validator")
        h2 = _content_hash("pydantic-v1-to-v2", "PYD002", "models.py", 10, "@validator")
        assert h1 != h2

    def test_different_line_different_hash(self) -> None:
        h1 = _content_hash("pydantic-v1-to-v2", "PYD001", "models.py", 10, "@validator")
        h2 = _content_hash("pydantic-v1-to-v2", "PYD001", "models.py", 11, "@validator")
        assert h1 != h2

    def test_is_hex_string(self) -> None:
        h = _content_hash("p", "r", "f", 1, "s")
        assert all(c in "0123456789abcdef" for c in h)
        assert len(h) == 64


class TestPersistAnalysis:
    @pytest.fixture
    def db(self) -> _StubDB:
        d = _StubDB()
        aid = str(uuid.uuid4())
        d.analyses[aid] = {"analysis_id": uuid.UUID(aid)}
        self._aid = aid
        return d

    @pytest.fixture
    def store(self, db: _StubDB) -> FindingsStore:
        return FindingsStore(_StubPool(db))

    @pytest.mark.asyncio
    async def test_updates_analyses_columns(self, store: FindingsStore, db: _StubDB) -> None:
        await store.persist_analysis(
            analysis_id=self._aid,
            pack_id="pydantic-v1-to-v2",
            pack_version="1.0.0",
            report_status="validated",
            owner="acme",
            repo="myapp",
            commit_sha="abc123",
            findings=[],
        )
        rec = db.analyses[self._aid]
        assert rec["pack_id"] == "pydantic-v1-to-v2"
        assert rec["owner"] == "acme"
        assert rec["repo"] == "myapp"

    @pytest.mark.asyncio
    async def test_inserts_findings_rows(self, store: FindingsStore, db: _StubDB) -> None:
        f = _make_finding()
        await store.persist_analysis(
            analysis_id=self._aid,
            pack_id="pydantic-v1-to-v2",
            pack_version="1.0.0",
            report_status="validated",
            owner="acme",
            repo="myapp",
            commit_sha="abc123",
            findings=[f],
        )
        assert len(db.findings) == 1
        assert db.findings[0]["rule_id"] == "PYD001"

    @pytest.mark.asyncio
    async def test_idempotent_on_duplicate_finding_id(
        self, store: FindingsStore, db: _StubDB
    ) -> None:
        f = _make_finding()
        await store.persist_analysis(
            analysis_id=self._aid,
            pack_id="pydantic-v1-to-v2",
            pack_version="1.0.0",
            report_status="validated",
            owner="acme",
            repo="myapp",
            commit_sha="abc123",
            findings=[f],
        )
        await store.persist_analysis(
            analysis_id=self._aid,
            pack_id="pydantic-v1-to-v2",
            pack_version="1.0.0",
            report_status="validated",
            owner="acme",
            repo="myapp",
            commit_sha="abc123",
            findings=[f],
        )
        assert len(db.findings) == 1


class TestDeltaVsPrevious:
    @pytest.fixture
    def db(self) -> _StubDB:
        return _StubDB()

    @pytest.fixture
    def store(self, db: _StubDB) -> FindingsStore:
        return FindingsStore(_StubPool(db))

    @pytest.mark.asyncio
    async def test_no_previous_returns_empty_delta(self, store: FindingsStore, db: _StubDB) -> None:
        current_id = str(uuid.uuid4())
        db.seed_analysis(current_id)
        delta = await store.delta_vs_previous("acme", "myapp", current_id)
        assert delta.previous_analysis_id is None
        assert delta.new_count == 0
        assert delta.resolved_count == 0
        assert delta.unchanged_count == 0

    @pytest.mark.asyncio
    async def test_all_new_when_no_overlap(self, store: FindingsStore, db: _StubDB) -> None:
        from datetime import timedelta

        prev_id = str(uuid.uuid4())
        current_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        db.seed_analysis(prev_id, created_at=now - timedelta(days=1))
        db.seed_analysis(current_id, created_at=now)

        db.seed_finding(current_id, "PYD001", "hash_new")

        delta = await store.delta_vs_previous("acme", "myapp", current_id)
        assert delta.new_count == 1
        assert delta.resolved_count == 0
        assert delta.unchanged_count == 0

    @pytest.mark.asyncio
    async def test_resolved_findings_detected(self, store: FindingsStore, db: _StubDB) -> None:
        from datetime import timedelta

        prev_id = str(uuid.uuid4())
        current_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        db.seed_analysis(prev_id, created_at=now - timedelta(days=1))
        db.seed_analysis(current_id, created_at=now)

        db.seed_finding(prev_id, "PYD001", "hash_old")

        delta = await store.delta_vs_previous("acme", "myapp", current_id)
        assert delta.resolved_count == 1
        assert delta.new_count == 0

    @pytest.mark.asyncio
    async def test_unchanged_findings_detected(self, store: FindingsStore, db: _StubDB) -> None:
        from datetime import timedelta

        prev_id = str(uuid.uuid4())
        current_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        db.seed_analysis(prev_id, created_at=now - timedelta(days=1))
        db.seed_analysis(current_id, created_at=now)

        db.seed_finding(prev_id, "PYD001", "shared_hash")
        db.seed_finding(current_id, "PYD001", "shared_hash")

        delta = await store.delta_vs_previous("acme", "myapp", current_id)
        assert delta.unchanged_count == 1
        assert delta.new_count == 0
        assert delta.resolved_count == 0


class TestRuleFrequency:
    @pytest.fixture
    def db(self) -> _StubDB:
        return _StubDB()

    @pytest.fixture
    def store(self, db: _StubDB) -> FindingsStore:
        return FindingsStore(_StubPool(db))

    @pytest.mark.asyncio
    async def test_empty_pack_returns_zero_repos(self, store: FindingsStore) -> None:
        stats = await store.rule_frequency("pydantic-v1-to-v2")
        assert stats.total_repos_analysed == 0
        assert stats.rules == []

    @pytest.mark.asyncio
    async def test_frequency_computed_correctly(self, store: FindingsStore, db: _StubDB) -> None:
        aid1 = str(uuid.uuid4())
        aid2 = str(uuid.uuid4())
        db.seed_analysis(aid1, pack_id="pydantic-v1-to-v2")
        db.seed_analysis(aid2, pack_id="pydantic-v1-to-v2")
        db.seed_finding(aid1, "PYD001", "h1")
        db.seed_finding(aid2, "PYD001", "h2")
        db.seed_finding(aid1, "PYD002", "h3")

        stats = await store.rule_frequency("pydantic-v1-to-v2")
        assert stats.total_repos_analysed == 2
        by_rule = {r.rule_id: r for r in stats.rules}
        assert by_rule["PYD001"].repo_count == 2
        assert by_rule["PYD001"].frequency == 1.0
        assert by_rule["PYD002"].repo_count == 1
        assert by_rule["PYD002"].frequency == 0.5


class TestHistoryForRepo:
    @pytest.fixture
    def db(self) -> _StubDB:
        return _StubDB()

    @pytest.fixture
    def store(self, db: _StubDB) -> FindingsStore:
        return FindingsStore(_StubPool(db))

    @pytest.mark.asyncio
    async def test_empty_history(self, store: FindingsStore) -> None:
        result = await store.history_for_repo("acme", "myapp")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_analyses_for_repo(self, store: FindingsStore, db: _StubDB) -> None:
        aid = str(uuid.uuid4())
        db.seed_analysis(aid, owner="acme", repo="myapp")
        result = await store.history_for_repo("acme", "myapp")
        assert len(result) == 1
        assert result[0]["analysis_id"] == aid

    @pytest.mark.asyncio
    async def test_excludes_other_repos(self, store: FindingsStore, db: _StubDB) -> None:
        aid1 = str(uuid.uuid4())
        aid2 = str(uuid.uuid4())
        db.seed_analysis(aid1, owner="acme", repo="myapp")
        db.seed_analysis(aid2, owner="acme", repo="other")
        result = await store.history_for_repo("acme", "myapp")
        assert len(result) == 1
        assert result[0]["analysis_id"] == aid1

    @pytest.mark.asyncio
    async def test_limit_is_honoured(self, store: FindingsStore, db: _StubDB) -> None:
        from datetime import timedelta

        now = datetime.now(UTC)
        for i in range(5):
            aid = str(uuid.uuid4())
            db.seed_analysis(aid, owner="acme", repo="myapp", created_at=now - timedelta(days=i))
        result = await store.history_for_repo("acme", "myapp", limit=3)
        assert len(result) == 3
