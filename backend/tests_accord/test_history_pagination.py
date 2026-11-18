"""A12: one database-paged timeline over a customer's proven identities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import Request
from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import customers
from api.routers import website_shop as web
from shop import models as m
from shop.repo.sql import SqlRepository

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'history.db'))
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
        await connection.execute(insert(m.User), [{'id': 1, 'tg_id': -1, 'referral_code': 'G'},
                                                  {'id': 2, 'tg_id': 77, 'referral_code': 'T'},
                                                  {'id': 3, 'tg_id': -3, 'referral_code': 'X'}])
        await connection.execute(insert(m.WebsiteAccount), [{'id': 1, 'user_id': 1, 'google_sub': 'g',
                                                              'linked_telegram_user_id': 2}])
        rows = []
        for n in range(1, 241):
            # Interleaved identities, pairs of equal timestamps, and a stranger.
            owner = 3 if n % 10 == 0 else (1 if n % 2 else 2)
            rows.append({'id': n, 'user_id': owner, 'status': m.OrderStatus.DONE, 'business_state': 'sale',
                         'created_at': NOW - timedelta(minutes=n // 2), 'subtotal': Decimal(1), 'discount': Decimal(0),
                         'bonus_used': Decimal(0), 'total': Decimal(n), 'payment_method': 'cod', 'search_key': ''})
        await connection.execute(insert(m.Order), rows)
        await connection.execute(insert(m.OrderItem), [{'order_id': n, 'name': f'Item {n}', 'price': Decimal(1), 'qty': 1}
                                                     for n in range(1, 241)])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    statements = []
    event.listen(engine.sync_engine, 'before_cursor_execute', lambda *a, **k: statements.append(a[2]))
    yield factory, statements
    await engine.dispose()


def expected_ids():
    own = [n for n in range(1, 241) if n % 10]
    return sorted(own, key=lambda n: (NOW - timedelta(minutes=n // 2), n), reverse=True)


@pytest.fixture
def account(monkeypatch):
    async def required(_request, repo):
        return await repo.s.get(m.WebsiteAccount, 1)
    monkeypatch.setattr(web, '_required_account', required)
    return Request({'type': 'http', 'method': 'GET', 'scheme': 'https', 'path': '/', 'headers': [], 'query_string': b''})


@pytest.mark.asyncio
async def test_pages_follow_one_merged_timeline_without_gaps_or_duplicates(db, account):
    factory, _ = db
    seen, offset = [], 0
    async with factory() as session:
        repo = SqlRepository(session)
        while True:
            page = await web.orders(account, limit=25, offset=offset, repo=repo)
            seen += [item['id'] for item in page['items']]
            offset += 25
            if not page['has_more']:
                break
    assert seen == expected_ids()
    assert not any(n % 10 == 0 for n in seen), 'another customer never leaks in'


@pytest.mark.asyncio
async def test_a_deep_page_costs_the_same_queries_as_the_first(db, account):
    factory, statements = db
    counts = []
    for offset in (0, 200):
        async with factory() as session:
            statements.clear()
            await web.orders(account, limit=5, offset=offset, repo=SqlRepository(session))
            orders = [sql for sql in statements if 'FROM orders' in sql]
            counts.append((len(statements), len(orders)))
            assert any('LIMIT' in sql and 'OFFSET' in sql for sql in orders), 'paged in SQL'
    assert counts[0] == counts[1]
    assert counts[0][1] == 1  # one orders query for both identities


@pytest.mark.asyncio
async def test_profile_reads_only_the_latest_order_and_counts_all_identities(db, account):
    factory, _ = db
    async with factory() as session:
        data = await web.profile(account, SqlRepository(session))
    assert data['last_order']['id'] == expected_ids()[0]
    assert data['orders_count'] == len(expected_ids())


@pytest.mark.asyncio
async def test_dashboard_customer_history_uses_the_same_merged_page(db):
    factory, _ = db
    async with factory() as session:
        data = await customers.customer_orders(1, limit=10, offset=20, paginated=True, repo=SqlRepository(session))
    assert [item['id'] for item in data['items']] == expected_ids()[20:30]
    assert data['total'] == len(expected_ids()) and data['has_more'] is True


@pytest.mark.asyncio
async def test_empty_identity_list_matches_nothing(db):
    factory, _ = db
    async with factory() as session:
        repo = SqlRepository(session)
        assert await repo.list_orders(user_id=[], limit=10) == []
        assert await repo.count_filtered_orders(user_id=[]) == 0
