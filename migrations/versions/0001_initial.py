"""initial

Revision ID: 0001
Revises:
Create Date: 2026-03-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('plan', sa.String(50), nullable=False, server_default='free'),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('plan_expires_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    op.create_table(
        'monitors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=True),
        sa.Column('tags', sa.String(500), nullable=False, server_default=''),
        sa.Column('schedule_type', sa.String(20), nullable=False, server_default='period'),
        sa.Column('period_seconds', sa.Integer(), nullable=True),
        sa.Column('cron_expression', sa.String(100), nullable=True),
        sa.Column('grace_seconds', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('expect_duration_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expect_duration_max_seconds', sa.Integer(), nullable=True),
        sa.Column('duration_alert_pct', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('avg_duration_seconds', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='new'),
        sa.Column('last_ping_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_duration_seconds', sa.Float(), nullable=True),
        sa.Column('next_expected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('alert_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('alert_email', sa.String(255), nullable=True),
        sa.Column('alert_webhook_url', sa.Text(), nullable=True),
        sa.Column('alert_on_recovery', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_paused', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_monitors_user_id', 'monitors', ['user_id'])

    op.create_table(
        'pings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('monitor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('monitors.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False, server_default='success'),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('duration_anomaly', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('source_ip', sa.String(45), nullable=True),
    )
    op.create_index('ix_pings_monitor_id', 'pings', ['monitor_id'])
    op.create_index('ix_pings_received_at', 'pings', ['received_at'])


def downgrade() -> None:
    op.drop_table('pings')
    op.drop_table('monitors')
    op.drop_table('users')
