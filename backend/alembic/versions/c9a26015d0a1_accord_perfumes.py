"""ACCORD NICHE: sellable perfume SKU metadata, no change to existing stock/pricing."""
from alembic import op
import sqlalchemy as sa

revision = "c9a26015d0a1"
down_revision = "fb4a8c2d1e70"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("products", sa.Column("brand", sa.String(100), server_default="", nullable=False))
    op.add_column("products", sa.Column("gender", sa.String(12), server_default="unisex", nullable=False))
    op.add_column("products", sa.Column("volume_ml", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("is_featured", sa.Boolean(), server_default=sa.false(), nullable=False))

def downgrade():
    op.drop_column("products", "is_featured")
    op.drop_column("products", "volume_ml")
    op.drop_column("products", "gender")
    op.drop_column("products", "brand")
