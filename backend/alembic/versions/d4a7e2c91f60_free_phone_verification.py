"""Free phone verification: own SMS codes and confirmation via the Telegram bot.

Twilio Verify is removed. Codes are generated and checked by the shop itself
(only an HMAC is stored on the website account) and delivered by a
self-hosted SMS gateway; alternatively the Telegram bot confirms the number
through the user's own contact. The stored Twilio credentials, including the
encrypted auth token, are deleted.

Revision ID: d4a7e2c91f60
Revises: e2b7c4a91d05
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a7e2c91f60"
down_revision = "e2b7c4a91d05"
branch_labels = None
depends_on = None

TWILIO = ("twilio_account_sid", "twilio_auth_token", "twilio_verify_service_sid")


def upgrade():
    with op.batch_alter_table("website_accounts") as batch:
        batch.add_column(sa.Column("phone_code_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("phone_code_phone", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("phone_code_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("phone_code_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "website_phone_confirmations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("website_accounts.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_website_phone_confirmations_expires_at", "website_phone_confirmations", ["expires_at"])
    settings = sa.table("settings", sa.column("key", sa.String))
    op.execute(settings.delete().where(settings.c.key.in_(TWILIO)))


def downgrade():
    op.drop_index("ix_website_phone_confirmations_expires_at", table_name="website_phone_confirmations")
    op.drop_table("website_phone_confirmations")
    with op.batch_alter_table("website_accounts") as batch:
        batch.drop_column("phone_code_attempts")
        batch.drop_column("phone_code_expires_at")
        batch.drop_column("phone_code_phone")
        batch.drop_column("phone_code_hash")
