"""uptime monitors and checks tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS uptime_monitors (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            name VARCHAR(255) NOT NULL,
            url TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL DEFAULT 300,
            timeout_seconds INTEGER NOT NULL DEFAULT 10,
            expected_status_code INTEGER NOT NULL DEFAULT 200,
            status VARCHAR(20) NOT NULL DEFAULT 'new',
            last_checked_at TIMESTAMPTZ,
            last_response_ms FLOAT,
            last_status_code INTEGER,
            next_check_at TIMESTAMPTZ,
            alert_sent_at TIMESTAMPTZ,
            alert_email VARCHAR(255),
            alert_webhook_url TEXT,
            slack_webhook_url TEXT,
            discord_webhook_url TEXT,
            telegram_bot_token VARCHAR(255),
            telegram_chat_id VARCHAR(100),
            pagerduty_key VARCHAR(255),
            alert_on_recovery BOOLEAN NOT NULL DEFAULT TRUE,
            is_paused BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_uptime_monitors_user_id ON uptime_monitors(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_uptime_monitors_next_check_at ON uptime_monitors(next_check_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS uptime_checks (
            id UUID PRIMARY KEY,
            monitor_id UUID NOT NULL REFERENCES uptime_monitors(id),
            checked_at TIMESTAMPTZ DEFAULT now(),
            is_up BOOLEAN NOT NULL,
            status_code INTEGER,
            response_ms FLOAT,
            error VARCHAR(500)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_uptime_checks_monitor_id ON uptime_checks(monitor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_uptime_checks_checked_at ON uptime_checks(checked_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS uptime_checks")
    op.execute("DROP TABLE IF EXISTS uptime_monitors")
