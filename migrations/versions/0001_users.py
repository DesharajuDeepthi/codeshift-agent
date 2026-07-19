"""users table for multi-tenant auth (GitHub OAuth identity only, no passwords)

Revision ID: 0001
Revises:
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("github_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("login", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_users_github_id", "users", ["github_id"])

    # Sentinel owner for pre-V2 (single-user) analyses backfilled in 0003.
    op.execute(
        """
        INSERT INTO users (user_id, github_id, login, email, is_active)
        VALUES ('00000000-0000-0000-0000-000000000000', -1, 'legacy', NULL, false)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_users_github_id", table_name="users")
    op.drop_table("users")
