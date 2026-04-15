"""Add clip_retention_policy table (CRKY-178).

Revision ID: 012
Revises: 011
Create Date: 2026-04-14

Moves the single retention policy record out of the ck.settings JSON
blob into a dedicated singleton-row table. The race window here is
small (two admins updating retention simultaneously) but the bug is
the same structural class as the rest of CRKY-169.
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ck.clip_retention_policy (
            id TEXT PRIMARY KEY,
            policy JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
                EXECUTE 'GRANT ALL ON TABLE ck.clip_retention_policy TO postgres';
            END IF;
        END $$
    """)

    op.execute("""
        INSERT INTO ck.clip_retention_policy (id, policy)
        SELECT 'default', s.value
        FROM ck.settings s
        WHERE s.key = 'clip_retention_policy'
          AND jsonb_typeof(s.value) = 'object'
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ck.clip_retention_policy")
