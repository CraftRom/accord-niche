"""Independent browser identities/sessions mapped to the same canonical shop users/orders.

Revision intentionally builds on ACCORD perfume migration; no changes to ELFAR's
existing order/cart/Telegram tables, apart from two new website-only tables.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ae102a1c91ff'
down_revision = 'c9a26015d0a1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table('website_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('google_sub', sa.String(255), nullable=True, unique=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('verified_phone', sa.String(32), nullable=True),
        sa.Column('linked_telegram_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, unique=True),
        sa.Column('phone_send_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phone_window_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phone_window_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table('website_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('website_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_website_sessions_account', 'website_sessions', ['account_id'])
    op.create_table('website_telegram_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tg_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table('website_telegram_links')
    op.drop_index('ix_website_sessions_account', 'website_sessions')
    op.drop_table('website_sessions')
    op.drop_table('website_accounts')
    op.drop_column('users', 'phone_verified_at')
