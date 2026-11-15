"""Preserve independently recorded guest orders and financial counters on Google sign-in.

Revision ID: bc1a8f723f9d
Revises: ae102a1c91ff
"""
from alembic import op
import sqlalchemy as sa

revision = 'bc1a8f723f9d'
down_revision = 'ae102a1c91ff'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('website_account_users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('website_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_website_account_users_account', 'website_account_users', ['account_id'])


def downgrade():
    op.drop_index('ix_website_account_users_account', table_name='website_account_users')
    op.drop_table('website_account_users')
