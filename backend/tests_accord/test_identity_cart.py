"""ACCORD identity + cart regression checks independent of the Telegram runtime.

Run from backend: python -m pytest -q tests_accord
These tests don't claim to replace a PostgreSQL integration test.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect

from shop import models as m
from shop.repo.sql import SqlRepository
from shop.services.website_identity import _order_time, _owned_user_ids, attach_guest_identity


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class CartSession:
    def __init__(self, products, user=True):
        self.user = SimpleNamespace(id=1) if user else None
        self.products = products
        self.calls = []
        self.new_lines = []
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, query):
        self.calls.append('lock_user')
        return self.user

    async def scalars(self, query):
        self.calls.append('lock_products')
        return ScalarRows(self.products)

    async def execute(self, query):
        self.calls.append('delete_previous_cart')

    def add_all(self, objects):
        self.new_lines = list(objects)
        self.calls.append('insert_replacement_cart')

    async def commit(self):
        self.commits += 1
        self.calls.append('commit')

    async def rollback(self):
        self.rollbacks += 1
        self.calls.append('rollback')


def product(id, stock, brand='CREED', active=True, price=Decimal('100')):
    return SimpleNamespace(id=id, stock=stock, brand=brand, is_active=active, price=price, name=f'Aroma {id}')


@pytest.mark.asyncio
async def test_replace_cart_writes_both_lines_in_one_transaction():
    session = CartSession([product(3, 10), product(7, 3)])
    await SqlRepository(session).replace_cart(1, [(3, 2), (7, 3)])
    assert session.commits == 1 and session.rollbacks == 0
    assert [(x.product_id, x.qty, x.user_id) for x in session.new_lines] == [(3, 2, 1), (7, 3, 1)]
    assert session.calls == ['lock_user', 'lock_products', 'delete_previous_cart', 'insert_replacement_cart', 'commit']


@pytest.mark.asyncio
@pytest.mark.parametrize('products,items', [
    ([product(3, 1)], [(3, 2)]),
    ([product(3, 10, price=Decimal('0'))], [(3, 1)]),
    ([product(3, 10, active=False)], [(3, 1)]),
    ([product(3, 10)], [(3, 1), (4, 1)]),
    ([product(3, 10)], [(3, 1), (3, 2)]),
])
async def test_invalid_replacement_never_deletes_existing_cart(products, items):
    session = CartSession(products)
    with pytest.raises(ValueError):
        await SqlRepository(session).replace_cart(1, items)
    assert session.commits == 0
    assert 'delete_previous_cart' not in session.calls


class IdentitySession:
    def __init__(self, aliases=(), existing_link=None):
        self.aliases = list(aliases)
        self.existing_link = existing_link
        self.added = []
        self.deleted = []
        self.executed = 0
        self.flushed = 0

    async def scalars(self, query):
        return ScalarRows(self.aliases)

    async def scalar(self, query):
        return self.existing_link

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed += 1

    async def execute(self, query):
        self.executed += 1

    async def delete(self, value):
        self.deleted.append(value)


def account(id, user_id, google_sub=None, linked=None):
    return SimpleNamespace(id=id, user_id=user_id, google_sub=google_sub,
                           linked_telegram_user_id=linked)


@pytest.mark.asyncio
async def test_three_channel_history_uses_proven_identities_and_deduplicates():
    acc = account(10, 100, google_sub='google-sub', linked=300)
    repo = SimpleNamespace(s=IdentitySession(aliases=[200, 300, 200]))
    assert await _owned_user_ids(repo, acc) == [100, 200, 300]


@pytest.mark.asyncio
async def test_google_identity_attaches_guest_without_touching_order_owner():
    session = IdentitySession()
    original = account(2, 200)
    target = account(1, 100, google_sub='google-sub')
    await attach_guest_identity(SimpleNamespace(s=session), target, original)
    assert [(x.account_id, x.user_id) for x in session.added] == [(1, 200)]
    assert session.flushed == 1 and session.executed == 1 and session.deleted == [original]
    # The service has no order UPDATE: order ownership/financial ledger remains intact.


@pytest.mark.asyncio
async def test_identity_owner_conflict_does_not_transfer_guest_data():
    session = IdentitySession(existing_link=SimpleNamespace(account_id=9))
    with pytest.raises(HTTPException) as exc:
        await attach_guest_identity(SimpleNamespace(s=session), account(1, 100, 'google-sub'), account(2, 200))
    assert exc.value.status_code == 409
    assert not session.added and not session.deleted and session.executed == 0


def test_order_sorting_mixed_database_timezones():
    naive = {'created_at': datetime(2026, 11, 15, 10, 0)}
    aware = {'created_at': datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)}
    assert _order_time(aware) > _order_time(naive)
    assert _order_time({}) == 0


def test_schema_enforces_one_owner_per_guest_identity():
    assert m.WebsiteAccountUser.__table__.c.user_id.unique is True
    assert 'website_account_users' in m.Base.metadata.tables
    assert m.WebsiteAccountUser.__table__.c.account_id.foreign_keys
