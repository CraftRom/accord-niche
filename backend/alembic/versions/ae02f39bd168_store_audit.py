"""Store audit revisions and test evidence."""
from alembic import op
import sqlalchemy as sa

revision = "ae02f39bd168"
down_revision = "e6b2d8f41a37"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("store_audit_events",
        sa.Column("environment", sa.String(16), primary_key=True),
        sa.Column("item", sa.String(64), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False))


def downgrade():
    op.drop_table("store_audit_events")
