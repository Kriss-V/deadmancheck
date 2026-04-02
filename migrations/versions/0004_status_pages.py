"""status pages table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS status_pages (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            monitor_ids TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_status_pages_user_id ON status_pages(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_status_pages_slug ON status_pages(slug)")


def downgrade() -> None:
    op.drop_table('status_pages')
