"""Alembic environment configuration for CorridorKey (CRKY-49).

Reads CK_DATABASE_URL from environment and targets the 'ck' schema.
Runs migrations against Supabase Postgres.
"""

import os
import sys

from alembic import context

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Database URL from environment
DATABASE_URL = os.environ.get("CK_DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError("CK_DATABASE_URL environment variable is required for migrations")


def run_migrations_offline():
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
        version_table_schema="ck",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode — connects and executes."""
    from psycopg2 import connect

    connection = connect(DATABASE_URL, options="-c search_path=ck,public")
    connection.autocommit = False

    context.configure(
        connection=connection,
        target_metadata=None,
        version_table="alembic_version",
        version_table_schema="ck",
    )

    try:
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
