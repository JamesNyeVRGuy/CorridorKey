"""Add webhooks table (CRKY-174).

Revision ID: 008
Revises: 007
Create Date: 2026-04-14

Moves webhook configs out of the ck.settings JSON blob into a real
table. Previously create/delete loaded the whole dict, mutated it,
and saved it back — two admins creating webhooks in parallel could
lose one, and delete races had the same problem.
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ck.webhooks (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            url TEXT NOT NULL,
            events JSONB NOT NULL DEFAULT '[]'::jsonb,
            format TEXT NOT NULL DEFAULT 'json',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by TEXT NOT NULL DEFAULT '',
            created_at DOUBLE PRECISION NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ck_webhooks_org ON ck.webhooks (org_id)")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
                EXECUTE 'GRANT ALL ON TABLE ck.webhooks TO postgres';
            END IF;
        END $$
    """)
    op.execute("""
        INSERT INTO ck.webhooks (id, org_id, url, events, format, active, created_by, created_at)
        SELECT
            entry.key,
            COALESCE(entry.value->>'org_id', ''),
            COALESCE(entry.value->>'url', ''),
            COALESCE(entry.value->'events', '[]'::jsonb),
            COALESCE(entry.value->>'format', 'json'),
            COALESCE((entry.value->>'active')::boolean, TRUE),
            COALESCE(entry.value->>'created_by', ''),
            COALESCE((entry.value->>'created_at')::DOUBLE PRECISION, 0)
        FROM ck.settings s,
             LATERAL jsonb_each(s.value) AS entry
        WHERE s.key = 'webhooks'
          AND jsonb_typeof(s.value) = 'object'
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ck.webhooks")
