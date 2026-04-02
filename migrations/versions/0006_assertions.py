"""Add assertions to monitors and assertion_results to pings"""
from alembic import op


def upgrade():
    op.execute("""
        ALTER TABLE monitors
        ADD COLUMN IF NOT EXISTS assertions TEXT DEFAULT NULL
    """)
    op.execute("""
        ALTER TABLE pings
        ADD COLUMN IF NOT EXISTS assertion_results TEXT DEFAULT NULL
    """)


def downgrade():
    op.execute("ALTER TABLE monitors DROP COLUMN IF EXISTS assertions")
    op.execute("ALTER TABLE pings DROP COLUMN IF EXISTS assertion_results")
