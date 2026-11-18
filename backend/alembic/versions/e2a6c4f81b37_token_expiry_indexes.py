"""Indexes for the housekeeping cleanup of expired website tokens (A11).

Revision ID: e2a6c4f81b37
Revises: d7e3a91c5b20
"""
from alembic import op

revision = "e2a6c4f81b37"
down_revision = "d7e3a91c5b20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_website_sessions_expires_at", "website_sessions", ["expires_at"])
    op.create_index("ix_website_telegram_links_expires_at", "website_telegram_links", ["expires_at"])


def downgrade():
    op.drop_index("ix_website_telegram_links_expires_at", table_name="website_telegram_links")
    op.drop_index("ix_website_sessions_expires_at", table_name="website_sessions")
