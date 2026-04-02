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
    op.create_table(
        'status_pages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('monitor_ids', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_status_pages_slug', 'status_pages', ['slug'])
    op.create_index('ix_status_pages_user_id', 'status_pages', ['user_id'])


def downgrade() -> None:
    op.drop_table('status_pages')
