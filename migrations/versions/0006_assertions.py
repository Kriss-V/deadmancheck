"""Add assertions to monitors and assertion_results to pings

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-02
"""
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS assertions TEXT DEFAULT NULL")
    op.execute("ALTER TABLE pings ADD COLUMN IF NOT EXISTS assertion_results TEXT DEFAULT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE monitors DROP COLUMN IF EXISTS assertions")
    op.execute("ALTER TABLE pings DROP COLUMN IF EXISTS assertion_results")
