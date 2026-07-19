"""analyses table — durable per-user analysis storage with delta support

V1 stored analyses in-process (documented known limitation). V2 introduces the
durable table with multi-tenancy (user_id), cross-run memory (thread_id), and
delta detection (delta jsonb) built in from the start. If a future deployment
already has an analyses table, this migration guards with IF NOT EXISTS.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            analysis_id  uuid PRIMARY KEY,
            user_id      uuid NOT NULL
                         DEFAULT '00000000-0000-0000-0000-000000000000'
                         REFERENCES users (user_id),
            thread_id    text,
            repository_url text NOT NULL,
            ref          text NOT NULL,
            commit_sha   text,
            status       text NOT NULL,
            finding_count integer,
            report       jsonb,
            delta        jsonb,
            created_at   timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        )
        """
    )
    # Backfill any pre-existing rows (a deployment that added its own table)
    # onto the legacy sentinel user, then drop the permissive default so all
    # new inserts must carry a real user_id.
    op.execute(
        "UPDATE analyses SET user_id = '00000000-0000-0000-0000-000000000000' "
        "WHERE user_id IS NULL"
    )
    op.execute("ALTER TABLE analyses ALTER COLUMN user_id DROP DEFAULT")
    op.execute("CREATE INDEX IF NOT EXISTS ix_analyses_user_id ON analyses (user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analyses_thread_id "
        "ON analyses (thread_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_analyses_thread_id")
    op.execute("DROP INDEX IF EXISTS ix_analyses_user_id")
    op.execute("DROP TABLE IF EXISTS analyses")
