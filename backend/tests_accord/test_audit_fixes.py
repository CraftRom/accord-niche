"""Regression tests for the 2026-11-17 audit findings (expected, fixed behaviour).

Each test describes the correct behaviour; the audit evidence reproduced the
opposite. SQLite only, no network: the SMS provider is replaced in-process.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import Principal, create_token, require_admin, require_staff
from api.routers import broadcasts, catalog, promos
from api.routers import website_shop as web
from shop import models as m
from shop.access import permissions_for
from shop.config import settings
from shop.entities import OperatorRole as Role
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services.product_io import parse_salesdrive_xlsx
from shop.services.shop_service import CheckoutQuoteError, checkout_quote


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'audit-fixes.db'))
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(m.User(id=1, tg_id=-123, referral_code='AUDIT'))
        await session.commit()
        yield session, factory
    await engine.dispose()


def xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def request():
    return Request({'type': 'http', 'method': 'POST', 'scheme': 'https', 'path': '/',
                    'headers': [], 'server': ('accordniche.pp.ua', 443), 'query_string': b''})


# ------------------------------------------------------------ A10 role matrix

async def _client(repo, routers):
    app = FastAPI()
    for router, prefix in routers:
        app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_repo] = lambda: repo
    return app


@pytest.mark.asyncio
async def test_manager_reads_catalog_but_cannot_change_catalog_or_marketing(db, monkeypatch):
    session, _ = db
    repo = SqlRepository(session)
    monkeypatch.setattr(settings, 'jwt_secret', 'audit-fixes-signing-secret-' * 3)
    session.add(m.Operator(id=1, login='manager', name='Manager', role=Role.MANAGER.value,
                           password_hash='unused', auth_version=0, is_active=True))
    session.add(m.Operator(id=2, login='shopadmin', name='Admin', role=Role.ADMIN.value,
                           password_hash='unused', auth_version=0, is_active=True))
    session.add(m.Product(id=1, name='Aroma', sku='AUD-001', price=100, stock=10, is_active=True))
    await session.commit()
    app = await _client(repo, [(catalog.router, '/api/catalog'), (promos.router, '/api/promos'),
                               (broadcasts.router, '/api/broadcasts')])
    manager = {'Authorization': 'Bearer ' + create_token('manager', Role.MANAGER, operator_id=1)}
    admin = {'Authorization': 'Bearer ' + create_token('shopadmin', Role.ADMIN, operator_id=2)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://dashboard.test') as http:
        assert (await http.get('/api/catalog/products', headers=manager)).status_code == 200
        assert (await http.get('/api/catalog/products/1', headers=manager)).status_code == 200
        denied = [
            ('POST', '/api/catalog/categories', {'name': 'Manager-created'}),
            ('PATCH', '/api/catalog/products/1', {'price': '1'}),
            ('PATCH', '/api/catalog/products/1/stock-delta', {'delta': 5}),
            ('DELETE', '/api/catalog/products/1/purge', None),
            ('POST', '/api/promos', {'code': 'MANAGER90', 'value': '90'}),
            ('GET', '/api/promos', None),
            ('GET', '/api/broadcasts', None),
        ]
        for method, path, body in denied:
            response = await http.request(method, path, json=body, headers=manager)
            assert response.status_code == 403, (method, path, response.text)
        assert (await http.post('/api/catalog/categories', json={'name': 'Admin-created'}, headers=admin)).status_code == 201
        assert (await http.post('/api/promos', json={'code': 'ADMIN10', 'value': '10'}, headers=admin)).status_code == 201
    assert (await repo.get_product(1)).stock == 10
    assert 'catalog.manage' not in permissions_for(Role.MANAGER)
    assert 'marketing.manage' not in permissions_for(Role.MANAGER)
    assert {'catalog.manage', 'marketing.manage'} <= set(permissions_for(Role.ADMIN))


# ------------------------------------------------------- A08 parent visibility

@pytest.mark.asyncio
async def test_inactive_parent_hides_product_everywhere_without_rewriting_its_flag(db):
    session, _ = db
    repo = SqlRepository(session)
    session.add(m.Category(id=1, name='Hidden', is_active=False))
    session.add(m.Category(id=2, name='Visible', is_active=True))
    session.add(m.Subcategory(id=1, category_id=2, name='Hidden sub', is_active=False))
    session.add(m.Product(id=1, category_id=1, name='Hidden parent', sku='AUD-001', price=100, stock=10, is_active=True))
    session.add(m.Product(id=2, subcategory_id=1, name='Hidden sub product', sku='AUD-002', price=100, stock=10, is_active=True))
    session.add(m.Product(id=3, category_id=2, name='Visible', sku='AUD-003', price=100, stock=10, is_active=True))
    session.add(m.Product(id=4, category_id=2, name='Individually hidden', sku='AUD-004', price=100, stock=10, is_active=False))
    await session.commit()
    now = datetime.now(timezone.utc)
    products, _ = await repo.storefront_data(now - timedelta(days=30), now)
    assert [p.id for p in products] == [3]
    assert [p.id for p in await repo.list_products(only_active=True)] == [3]
    assert {p.id for p in await repo.list_products(inventory='hidden')} == {1, 2, 4}
    hidden = await repo.get_product(1)
    assert hidden.is_active and not hidden.is_published  # individual state kept
    with pytest.raises(ValueError):
        await repo.replace_cart(1, [(1, 1)])
    assert await repo.change_cart_qty_atomic(1, 2, 1) is None
    # A line saved before the group was hidden cannot be bought.
    session.add(m.CartItem(user_id=1, product_id=1, qty=1))
    await session.commit()
    with pytest.raises(CheckoutQuoteError, match='недоступний'):
        await checkout_quote(repo, await repo.get_user(1))
    # Re-enabling the group publishes only individually active products.
    await repo.update_category(1, {'name': 'Hidden', 'is_active': True})
    session.add(m.Product(id=5, category_id=1, name='Own flag off', sku='AUD-005', price=100, stock=1, is_active=False))
    await session.commit()
    products, _ = await repo.storefront_data(now - timedelta(days=30), now)
    assert sorted(p.id for p in products) == [1, 3]


# ------------------------------------------------------------ XLSX parsing

def test_parser_rejects_fractional_invalid_and_nonfinite_values_per_row():
    rows = parse_salesdrive_xlsx(xlsx([
        ['Товар', 'Залишок', 'Ціна'],
        ['Fraction', 1.9, 100],
        ['Valid', 2, '99,50'],
        ['Invalid stock', 'oops', 100],
        ['NaN price', 1, 'NaN'],
        ['Infinite', 1, 'inf'],
        ['Negative', -1, 10],
        ['Whole float', 3.0, 10],
    ]))
    by_name = {row['name']: row for row in rows}
    assert len(rows) == 7
    assert 'error' in by_name['Fraction'] and 'stock' not in by_name['Fraction']
    assert by_name['Valid']['stock'] == 2 and by_name['Valid']['current_price'] == Decimal('99.50')
    for name in ('Invalid stock', 'NaN price', 'Infinite', 'Negative'):
        assert by_name[name].get('error'), name
    assert by_name['Whole float']['stock'] == 3
    assert by_name['Fraction']['row'] == 2 and by_name['Whole float']['row'] == 8


# ------------------------------------------------------- import replay (A02)

@pytest.mark.asyncio
async def test_repeated_import_does_not_overwrite_stock_sold_in_between(db):
    session, _ = db
    repo = SqlRepository(session)
    session.add(m.Product(id=1, name='Aroma', sku='AUD-001', price=100, stock=10, is_active=True))
    await session.commit()
    app = await _client(repo, [(catalog.router, '/api/catalog')])
    who = Principal('root', 'root', Role.SYSADMIN, 0)
    app.dependency_overrides[require_staff] = lambda: who
    app.dependency_overrides[require_admin] = lambda: who
    body = xlsx([['SKU', 'Товар', 'Категорія', 'Субкатегорія', 'Ціна', 'Залишок'],
                 ['AUD-001', 'Aroma', '', '', 100, 10], ['AUD-BAD', 'Broken', '', '', 100, 1.5]])
    files = {'file': ('audit.xlsx', body, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://dashboard.test') as http:
        first = await http.post('/api/catalog/product-transfer/import', files=files)
        assert first.status_code == 202, first.text  # durable job, applied in the background
        job = (await http.get('/api/catalog/product-transfer/import/' + first.json()['job_id'])).json()
        assert job['status'] == 'done' and job['result']['updated'] == 1
        assert [e['row'] for e in job['result']['errors']] == [3]
        await repo.update_product(1, {'stock': 9})  # a sale after the import
        retry = await http.post('/api/catalog/product-transfer/import', files=files)
        assert retry.status_code == 200 and retry.json()['replayed'] is True
        assert (await repo.get_product(1)).stock == 9
        forced = await http.post('/api/catalog/product-transfer/import', files=files, data={'force': 'true'})
        assert forced.status_code == 202 and forced.json()['replayed'] is False
    assert (await repo.get_product(1)).stock == 10


# ------------------------------------------------------------- SMS limiter

@pytest.mark.asyncio
async def test_parallel_sms_requests_send_once_and_count_once(db, monkeypatch):
    session, factory = db
    session.add(m.WebsiteAccount(id=1, user_id=1, google_sub='audit-sub'))
    await session.commit()
    monkeypatch.setattr(web, '_require_csrf', lambda r: None)
    for name in ('ACCORD_TWILIO_ACCOUNT_SID', 'ACCORD_TWILIO_AUTH_TOKEN', 'ACCORD_TWILIO_VERIFY_SERVICE_SID'):
        monkeypatch.setenv(name, 'configured')  # .env fallback of the panel setting
    sent, loaded, ready = [], 0, asyncio.Event()

    async def account(_request, repo):
        nonlocal loaded
        row = await repo.s.get(m.WebsiteAccount, 1)
        loaded += 1
        if loaded == 2:
            ready.set()
        await ready.wait()  # both requests have read the same old row
        return row

    async def twilio(*args):
        sent.append(args)
        return {'status': 'pending'}

    monkeypatch.setattr(web, '_required_account', account)
    monkeypatch.setattr(web, '_twilio', twilio)
    async with factory() as a, factory() as b:
        results = await asyncio.gather(
            web.phone_send(web.PhoneIn(phone='+380671234567'), request(), SqlRepository(a)),
            web.phone_send(web.PhoneIn(phone='+380671234567'), request(), SqlRepository(b)),
            return_exceptions=True)
    assert sorted(type(r).__name__ for r in results) == ['HTTPException', 'dict']
    assert next(r for r in results if isinstance(r, HTTPException)).status_code == 429
    async with factory() as check:
        row = await check.get(m.WebsiteAccount, 1)
        assert len(sent) == 1 and row.phone_window_count == 1


@pytest.mark.asyncio
async def test_sms_hourly_limit_is_enforced_atomically(db, monkeypatch):
    session, factory = db
    old = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.add(m.WebsiteAccount(id=1, user_id=1, google_sub='audit-sub', phone_send_at=old,
                                 phone_window_at=old, phone_window_count=5))
    await session.commit()
    monkeypatch.setattr(web, '_require_csrf', lambda r: None)
    for name in ('ACCORD_TWILIO_ACCOUNT_SID', 'ACCORD_TWILIO_AUTH_TOKEN', 'ACCORD_TWILIO_VERIFY_SERVICE_SID'):
        monkeypatch.setenv(name, 'configured')  # .env fallback of the panel setting

    async def account(_request, repo):
        return await repo.s.get(m.WebsiteAccount, 1)

    async def twilio(*args):
        raise AssertionError('limit must stop the provider call')

    monkeypatch.setattr(web, '_required_account', account)
    monkeypatch.setattr(web, '_twilio', twilio)
    async with factory() as s:
        with pytest.raises(HTTPException) as error:
            await web.phone_send(web.PhoneIn(phone='+380671234567'), request(), SqlRepository(s))
    assert error.value.status_code == 429 and 'годину' in error.value.detail
