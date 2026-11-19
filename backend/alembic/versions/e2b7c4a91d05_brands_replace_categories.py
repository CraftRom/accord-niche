"""Brands replace categories and subcategories.

A perfume shop groups its products by brand. This revision adds the brand
dictionary (`brands`), links products to it (`products.brand_id`) and scopes
promo codes by brand (`promo_codes.brand_ids`). Categories and subcategories
are no longer used by the application; their tables and the old product
columns are kept untouched so a downgrade loses nothing.

Data migration, all inside the revision's transaction:
- every distinct non-empty `products.brand` (case-insensitive) becomes a
  brand and its products point at it;
- products hidden through an inactive category or subcategory stay hidden:
  the group no longer exists for the shop, so they are switched off
  individually (`is_active = false`);
- a promo limited to categories becomes limited to the brands of the
  products in those categories; when no such product exists the promo is
  switched off instead of silently applying to every order.

Revision ID: e2b7c4a91d05
Revises: c8f1e5a3d702
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "e2b7c4a91d05"
down_revision = "c8f1e5a3d702"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _ids(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [int(item) for item in value if str(item).lstrip("-").isdigit()]


def upgrade():
    op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_brands_name_key", "brands", ["name_key"], unique=True)
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_products_brand_id", "brands", ["brand_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_products_brand_id", ["brand_id"])
    with op.batch_alter_table("promo_codes") as batch:
        batch.add_column(sa.Column("brand_ids", JSON, nullable=False, server_default=sa.text("'[]'")))

    bind = op.get_bind()
    # 1. Brand dictionary from the products' brand names.
    seen = {}
    for pid, brand in bind.execute(sa.text("SELECT id, brand FROM products ORDER BY id")):
        name = " ".join(str(brand or "").split())[:100]
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen[key] = (bind.execute(
                sa.text("INSERT INTO brands (name, name_key, sort_order, is_active) VALUES (:name, :key, 0, :on) RETURNING id"),
                {"name": name, "key": key, "on": True}).scalar_one(), name)
        brand_id, canonical = seen[key]
        bind.execute(sa.text("UPDATE products SET brand_id = :brand, brand = :name WHERE id = :pid"),
                     {"brand": brand_id, "name": canonical, "pid": pid})

    # 2. Keep products hidden that only an inactive group was hiding.
    bind.execute(sa.text("""
        UPDATE products SET is_active = :off
        WHERE is_active = :on AND (
            category_id IN (SELECT id FROM categories WHERE is_active = :off)
            OR subcategory_id IN (SELECT id FROM subcategories WHERE is_active = :off)
            OR subcategory_id IN (SELECT s.id FROM subcategories s JOIN categories c ON c.id = s.category_id
                                  WHERE c.is_active = :off))
    """), {"on": True, "off": False})

    # 3. Category promos become brand promos (or are switched off).
    promos = bind.execute(sa.text("SELECT id, category_ids FROM promo_codes")).all()
    for promo_id, raw in promos:
        categories = _ids(raw)
        if not categories:
            continue
        rows = bind.execute(sa.text("""
            SELECT DISTINCT p.brand_id FROM products p
            LEFT JOIN subcategories s ON s.id = p.subcategory_id
            WHERE p.brand_id IS NOT NULL AND (p.category_id IN :cats OR s.category_id IN :cats)
        """).bindparams(sa.bindparam("cats", expanding=True)), {"cats": categories}).scalars().all()
        brand_ids = sorted(int(value) for value in rows)
        if brand_ids:
            bind.execute(sa.text("UPDATE promo_codes SET brand_ids = :ids WHERE id = :id").bindparams(
                sa.bindparam("ids", type_=JSON)), {"ids": brand_ids, "id": promo_id})
        else:
            bind.execute(sa.text("UPDATE promo_codes SET is_active = :off WHERE id = :id"), {"off": False, "id": promo_id})


def downgrade():
    with op.batch_alter_table("promo_codes") as batch:
        batch.drop_column("brand_ids")
    with op.batch_alter_table("products") as batch:
        batch.drop_index("ix_products_brand_id")
        batch.drop_constraint("fk_products_brand_id", type_="foreignkey")
        batch.drop_column("brand_id")
    op.drop_index("ux_brands_name_key", table_name="brands")
    op.drop_table("brands")
