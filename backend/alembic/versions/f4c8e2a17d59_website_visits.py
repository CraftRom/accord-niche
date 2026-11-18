"""Anonymous first-party website visits for the conversion funnel (A07).

Revision ID: f4c8e2a17d59
Revises: e2a6c4f81b37
"""
from alembic import op
import sqlalchemy as sa

revision = "f4c8e2a17d59"
down_revision = "e2a6c4f81b37"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analytics_sessions", sa.Column(
        "channel", sa.String(24), nullable=False, server_default="telegram_miniapp"))
    with op.batch_alter_table("analytics_sessions") as batch:  # SQLite-safe; direct on PostgreSQL
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
    op.create_index("ux_analytics_website_session", "analytics_sessions", ["session_id"], unique=True,
                    postgresql_where=sa.text("channel = 'accord_website'"))


def downgrade():
    # Anonymous visits cannot satisfy NOT NULL user_id; they are telemetry only.
    op.execute("DELETE FROM analytics_sessions WHERE user_id IS NULL")
    op.drop_index("ux_analytics_website_session", table_name="analytics_sessions")
    with op.batch_alter_table("analytics_sessions") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("analytics_sessions", "channel")
