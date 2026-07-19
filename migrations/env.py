"""Alembic environment — reads DATABASE_URL from the application settings."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

# Migrations are written imperatively (op.create_table / op.execute), so there
# is no ORM metadata to autogenerate against.
target_metadata = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL must be set to run migrations "
            "(e.g. postgresql+psycopg://upgradepilot:upgradepilot@localhost:5432/upgradepilot)"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
