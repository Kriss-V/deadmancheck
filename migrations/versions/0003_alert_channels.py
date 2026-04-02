"""alert channel columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('monitors', sa.Column('slack_webhook_url', sa.Text(), nullable=True))
    op.add_column('monitors', sa.Column('discord_webhook_url', sa.Text(), nullable=True))
    op.add_column('monitors', sa.Column('telegram_bot_token', sa.String(255), nullable=True))
    op.add_column('monitors', sa.Column('telegram_chat_id', sa.String(100), nullable=True))
    op.add_column('monitors', sa.Column('pagerduty_key', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('monitors', 'pagerduty_key')
    op.drop_column('monitors', 'telegram_chat_id')
    op.drop_column('monitors', 'telegram_bot_token')
    op.drop_column('monitors', 'discord_webhook_url')
    op.drop_column('monitors', 'slack_webhook_url')
