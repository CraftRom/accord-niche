"""Customer card: name from the Google sign-in, purchase statistics, chats."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api import auth
from api.routers import customers as customers_router
from shop import models as m
from shop.config import settings
from shop.entities import OperatorRole as Role, OrderStatus
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository


@pytest_asyncio.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, 'jwt_secret', 'unit-test-secret-' * 4)
    monkeypatch.setattr(settings, 'dashboard_login', 'root')
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    now = datetime.now(timezone.utc)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all([
            m.User(id=1, tg_id=-1, referral_code='WEB1'),                      # website buyer (Google)
            m.User(id=2, tg_id=555, referral_code='TG2', first_name='Тарас'),  # linked Telegram profile
            m.User(id=3, tg_id=-3, referral_code='WEB3'),                      # guest without Google
            m.Brand(id=1, name='Creed', name_key='creed'), m.Brand(id=2, name='Kilian', name_key='kilian'),
        ])
        session.add_all([
            m.Product(id=1, sku='P1', name='Aventus 5 мл', name_lower='aventus 5 мл', brand='Creed', brand_id=1, price=Decimal('600'), stock=5),
            m.Product(id=2, sku='P2', name='Angels 5 мл', name_lower='angels 5 мл', brand='Kilian', brand_id=2, price=Decimal('400'), stock=5),
            m.WebsiteAccount(id=1, user_id=1, google_sub='g-1', email='olena@example.com', display_name='Олена Коваль',
                             linked_telegram_user_id=2),
        ])
        orders = [
            m.Order(id=1, user_id=1, total=Decimal('1200'), business_state='sale', status=OrderStatus.DONE,
                    attribution={'channel': 'accord_website'}, created_at=now - timedelta(days=30)),
            m.Order(id=2, user_id=2, total=Decimal('400'), business_state='sale', status=OrderStatus.DONE,
                    attribution={'channel': 'telegram_miniapp'}, created_at=now - timedelta(days=10)),
            m.Order(id=3, user_id=1, total=Decimal('999'), business_state='refusal', status=OrderStatus.CANCELLED,
                    created_at=now - timedelta(days=1)),
            m.Order(id=4, user_id=3, total=Decimal('50'), business_state='sale', status=OrderStatus.DONE),
        ]
        session.add_all(orders)
        session.add_all([
            m.OrderItem(order_id=1, product_id=1, name='Aventus 5 мл', price=Decimal('600'), qty=2),
            m.OrderItem(order_id=2, product_id=2, name='Angels 5 мл', price=Decimal('400'), qty=1),
            m.OrderItem(order_id=3, product_id=2, name='Angels 5 мл', price=Decimal('999'), qty=9),
            m.OrderMessage(order_id=2, user_id=2, direction='in', text='Коли відправите?', is_read=False),
            m.OrderMessage(order_id=2, user_id=2, direction='out', text='Сьогодні', is_read=True),
            m.SupportThread(id=7, user_id=2, status='open', last_message_at=now),
        ])
        await session.commit()
        repo = SqlRepository(session)
        app = FastAPI()
        app.include_router(customers_router.router, prefix='/api/customers')
        app.dependency_overrides[get_repo] = lambda: repo
        from shop.db import get_session
        app.dependency_overrides[get_session] = lambda: session
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
            yield http
    await engine.dispose()




@pytest.fixture
def staff():
    return {'Authorization': 'Bearer ' + auth.create_token('root', Role.SYSADMIN, 0)}


@pytest.mark.asyncio
async def test_list_shows_the_name_and_email_from_google(env, staff):
    rows = (await env.get('/api/customers', headers=staff)).json()
    web = next(r for r in rows if r['id'] == 1)
    assert web['display_name'] == 'Олена Коваль' and web['email'] == 'olena@example.com' and web['google_connected']
    linked = next(r for r in rows if r['id'] == 2)
    assert linked['display_name'] == 'Олена Коваль', 'linked Telegram profile shows the account name'
    guest = next(r for r in rows if r['id'] == 3)
    assert guest['display_name'] is None and guest['email'] is None and not guest['google_connected']


@pytest.mark.asyncio
async def test_search_finds_website_buyers_by_google_name_and_email(env, staff):
    # SQLite lower() is ASCII-only; PostgreSQL also matches Cyrillic in any case.
    by_name = (await env.get('/api/customers', params={'search': 'Коваль'}, headers=staff)).json()
    by_email = (await env.get('/api/customers', params={'search': 'OLENA@'}, headers=staff)).json()
    assert {r['id'] for r in by_name} == {1, 2} and {r['id'] for r in by_email} == {1, 2}


@pytest.mark.asyncio
async def test_summary_counts_every_proven_identity(env, staff):
    data = (await env.get('/api/customers/1/summary', headers=staff)).json()
    stats = data['stats']
    assert data['user_ids'] == [1, 2] and data['telegram_connected']
    assert stats['orders'] == 3 and stats['sales'] == 2 and stats['lost'] == 1
    assert stats['revenue'] == '1600.00' and stats['average_check'] == '800.00'
    assert stats['average_order'] == '800.00', 'cancelled orders do not lower the average order'
    assert [b['name'] for b in data['brands']] == ['Creed', 'Kilian'] and data['brands'][1]['qty'] == 1
    assert {c['key']: c['orders'] for c in data['channels']} == {'website': 1, 'miniapp': 1, 'unknown': 1}
    assert data['order_chats'] == [{**data['order_chats'][0], 'order_id': 2, 'messages': 2, 'unread': 1}]
    assert data['support_threads'][0]['id'] == 7
    guest = (await env.get('/api/customers/3/summary', headers=staff)).json()
    assert guest['user_ids'] == [3] and guest['stats']['revenue'] == '50.00' and guest['display_name'] is None


@pytest.mark.asyncio
async def test_customer_card_is_staff_only(env):
    assert (await env.get('/api/customers/1/summary')).status_code in (401, 403)
    assert (await env.get('/api/customers/99/summary', headers={'Authorization': 'Bearer ' + auth.create_token('root', Role.SYSADMIN, 0)})).status_code == 404
