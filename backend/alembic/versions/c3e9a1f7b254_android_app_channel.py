"""Android app visits: one row per app launch, deduplicated like website visits.

Revision ID: c3e9a1f7b254
Revises: d4a7e2c91f60
"""
from alembic import op
import sqlalchemy as sa

revision = "c3e9a1f7b254"
down_revision = "d4a7e2c91f60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ux_analytics_app_session", "analytics_sessions", ["session_id"], unique=True,
                    postgresql_where=sa.text("channel = 'accord_android'"),
                    sqlite_where=sa.text("channel = 'accord_android'"))


def downgrade():
    op.drop_index("ux_analytics_app_session", table_name="analytics_sessions")
