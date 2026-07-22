"""Relational findings table + analyses cross-analysis columns.

Adds individual finding rows for delta computation, and extends the analyses
table with the columns needed for cross-analysis queries (pack_id, pack_version,
report_status, owner, repo).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend analyses with cross-analysis query columns
    op.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS pack_id TEXT")
    op.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS pack_version TEXT")
    op.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS report_status TEXT")
    op.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS owner TEXT")
    op.execute("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS repo TEXT")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analyses_owner_repo"
        " ON analyses (owner, repo, created_at DESC)"
    )

    # Relational findings table — one row per finding per analysis
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS findings (
            finding_id   UUID        PRIMARY KEY,
            analysis_id  UUID        NOT NULL
                         REFERENCES analyses (analysis_id) ON DELETE CASCADE,
            pack_id      TEXT        NOT NULL,
            pack_version TEXT        NOT NULL,
            rule_id      TEXT        NOT NULL,
            category     TEXT        NOT NULL,
            severity     TEXT        NOT NULL,
            file         TEXT        NOT NULL,
            line_start   INT         NOT NULL,
            line_end     INT         NOT NULL,
            symbol       TEXT        NOT NULL,
            confidence   FLOAT       NOT NULL,
            match_kind   TEXT        NOT NULL,
            content_hash TEXT        NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_findings_analysis_id ON findings (analysis_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_findings_rule_pack ON findings (pack_id, rule_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_findings_content_hash ON findings (content_hash)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_findings_content_hash")
    op.execute("DROP INDEX IF EXISTS ix_findings_rule_pack")
    op.execute("DROP INDEX IF EXISTS ix_findings_analysis_id")
    op.execute("DROP TABLE IF EXISTS findings")
    op.execute("DROP INDEX IF EXISTS ix_analyses_owner_repo")
    op.execute("ALTER TABLE analyses DROP COLUMN IF EXISTS repo")
    op.execute("ALTER TABLE analyses DROP COLUMN IF EXISTS owner")
    op.execute("ALTER TABLE analyses DROP COLUMN IF EXISTS report_status")
    op.execute("ALTER TABLE analyses DROP COLUMN IF EXISTS pack_version")
    op.execute("ALTER TABLE analyses DROP COLUMN IF EXISTS pack_id")
