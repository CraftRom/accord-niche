"""SEO fields for perfumes and blog posts, comment bans and auto-moderation.

Products get an optional SEO title/description, image alt text, the perfume
card (concentration, family, top/heart/base notes, perfumer, year) and
updated_at for sitemap lastmod. Blog posts get SEO title/description, focus
keyword, cover alt text and noindex. Comments get automatic moderation flags;
new tables hold comment bans and the moderation rules. Data is not changed.

Revision ID: e6b2d8f41a37
Revises: c3e9a1f7b254
"""
from alembic import op
import sqlalchemy as sa

revision = "e6b2d8f41a37"
down_revision = "c3e9a1f7b254"
branch_labels = None
depends_on = None

PRODUCT_TEXT = (("seo_title", 120), ("seo_description", 300), ("image_alt", 200), ("concentration", 24),
                ("fragrance_family", 80), ("top_notes", 500), ("heart_notes", 500), ("base_notes", 500),
                ("perfumer", 120))
POST_TEXT = (("seo_title", 120), ("seo_description", 300), ("focus_keyword", 80), ("cover_alt", 200))


def upgrade():
    with op.batch_alter_table("products") as batch:
        for name, length in PRODUCT_TEXT:
            batch.add_column(sa.Column(name, sa.String(length=length), nullable=False, server_default=""))
        batch.add_column(sa.Column("release_year", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True,
                                   server_default=sa.func.now()))
    with op.batch_alter_table("blog_posts") as batch:
        for name, length in POST_TEXT:
            batch.add_column(sa.Column(name, sa.String(length=length), nullable=False, server_default=""))
        batch.add_column(sa.Column("noindex", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    with op.batch_alter_table("blog_comments") as batch:
        batch.add_column(sa.Column("flags", sa.String(length=200), nullable=False, server_default=""))
    op.create_table(
        "blog_comment_bans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("author_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("reason", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("banned_by", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "blog_moderation_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("trusted_after", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("stop_words", sa.Text(), nullable=False, server_default=""),
        sa.Column("stop_word_action", sa.String(length=16), nullable=False, server_default="hold"),
        sa.Column("hold_links", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("blog_moderation_settings")
    op.drop_table("blog_comment_bans")
    with op.batch_alter_table("blog_comments") as batch:
        batch.drop_column("flags")
    with op.batch_alter_table("blog_posts") as batch:
        batch.drop_column("noindex")
        for name, _ in reversed(POST_TEXT):
            batch.drop_column(name)
    with op.batch_alter_table("products") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("release_year")
        for name, _ in reversed(PRODUCT_TEXT):
            batch.drop_column(name)
