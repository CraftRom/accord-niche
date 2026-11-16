"""Moderated ACCORD blog; independent of order, catalog and identity history."""
from alembic import op
import sqlalchemy as sa

revision = "c04b19a7e230"
down_revision = "bc1a8f723f9d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("blog_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(180), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("excerpt", sa.String(500), nullable=False, server_default=""),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cover_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(120), nullable=False, server_default="Редакція ACCORD NICHE"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("comments_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_blog_posts_public", "blog_posts", ["status", "published_at", "id"])
    op.create_table("blog_slugs",
        sa.Column("slug", sa.String(180), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False))
    op.create_index("ix_blog_slugs_post_id", "blog_slugs", ["post_id"])
    op.create_table("blog_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("blog_comments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(120), nullable=False),
        sa.Column("is_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("client_key", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("moderation_note", sa.String(500), nullable=False, server_default=""),
        sa.Column("moderated_by", sa.String(64), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("post_id", "client_key", name="uq_blog_comment_retry"))
    op.create_index("ix_blog_comments_public", "blog_comments", ["post_id", "parent_id", "status", "id"])
    op.create_index("ix_blog_comments_moderation", "blog_comments", ["status", "created_at", "id"])
    op.create_index("ix_blog_comments_author_time", "blog_comments", ["author_user_id", "created_at"])


def downgrade():
    op.drop_table("blog_comments")
    op.drop_table("blog_slugs")
    op.drop_table("blog_posts")
