"""Drop the retired promo landing pages and their Cloudflare credentials.

Promo pages were removed from ACCORD in v1.23.0. This revision removes their
tables, aggregate statistics and the encrypted Cloudflare token/account that
only that feature used. The data is not recoverable from the database after
upgrade; downgrade recreates empty tables only.

Revision ID: c8f1e5a3d702
Revises: a3d9b6e14f02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c8f1e5a3d702"
down_revision = "a3d9b6e14f02"
branch_labels = None
depends_on = None

JSON = JSONB().with_variant(sa.JSON(), "sqlite")
SETTINGS = ("promo_cloudflare_api_token", "promo_cloudflare_account_id")


def upgrade():
    op.execute("DROP TABLE IF EXISTS promo_landing_daily_stats")
    op.execute("DROP TABLE IF EXISTS promo_landing_pages")
    settings = sa.table("settings", sa.column("key", sa.String))
    op.execute(settings.delete().where(settings.c.key.in_(SETTINGS)))


def downgrade():
    op.create_table(
        "promo_landing_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("draft_config", JSON, nullable=False),
        sa.Column("published_config", JSON, nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("domain", name="uq_promo_landing_pages_domain"),
    )
    op.create_index("ix_promo_landing_pages_domain", "promo_landing_pages", ["domain"], unique=True)
    op.create_index("ix_promo_landing_pages_is_published", "promo_landing_pages", ["is_published"])
    op.create_table(
        "promo_landing_daily_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["page_id"], ["promo_landing_pages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("page_id", "day", name="uq_promo_landing_stat_day"),
    )
    op.create_index("ix_promo_landing_stats_page_day", "promo_landing_daily_stats", ["page_id", "day"])
