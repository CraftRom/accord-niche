"""Real database merchandising and public API contracts; no demo catalog."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from api.routers import public_catalog as api
from shop import models as m
from shop.entities import Product
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services.storefront import group_catalog, snapshot, _cache, _locks


@pytest_asyncio.fixture
async def store():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session, SqlRepository(session)
    _cache.pop(engine, None)
    _locks.pop(engine, None)
    await engine.dispose()


def product(id, **changes):
    values = dict(id=id, category_id=None, sku='TEST-' + str(id), name='Aroma 5 мл',
                  price=Decimal('100'), stock=3, brand='REAL BRAND', volume_ml=5)
    values.update(changes)
    return Product(**values)


def test_group_price_uses_buyable_variants_and_preserves_real_identity():
    rows = [product(1, name='Aroma 2 мл', volume_ml=2, price=Decimal('10'), stock=0),
            product(2, is_new=True), product(3, name='Other', brand='OTHER', volume_ml=None)]
    groups = group_catalog(rows, {1:4, 2:3, 3:5}, api.public_product)
    aroma = next(g for g in groups if g['name'] == 'Aroma')
    assert len(aroma['variants']) == 2
    assert aroma['min_price'] == 100 and aroma['price_per_ml'] == 20
    assert aroma['id']==1 and aroma['default_product_id']==2
    assert aroma['bestseller_rank'] == 1 and aroma['is_new']
    assert set(p.id for g in groups for p in g['variants']) == {1, 2, 3}


def test_manual_recommendations_are_not_fake_bestsellers():
    groups = group_catalog([product(1, is_featured=True)], {}, api.public_product)
    assert groups[0]['is_featured'] is True
    assert groups[0]['bestseller_rank'] is None
    assert group_catalog([], {}, api.public_product) == []


def test_volume_suffix_only_strips_the_declared_volume():
    groups = group_catalog([product(1, name='Aroma 30', volume_ml=5),
                            product(2, name='Aroma 30 - 5 ml', volume_ml=5)], {}, api.public_product)
    assert len(groups) == 1 and groups[0]['name'] == 'Aroma 30'
    groups = group_catalog([product(3, name='Sunset', brand='', volume_ml=None)], {}, api.public_product)
    assert not groups[0]['is_set'] and groups[0]['brand'] == ''


@pytest.mark.asyncio
async def test_sql_sales_exclude_pending_refusal_old_and_future_orders(store):
    session, repo = store
    now = datetime.now(timezone.utc)
    session.add(m.User(id=1, tg_id=1, referral_code='store-test'))
    session.add_all([m.Product(id=i, sku='T-' + str(i), name='Aroma ' + str(i),
                              price=Decimal('100') if i != 4 else 0, stock=3, brand='BRAND',
                              is_active=(i != 3)) for i in range(1, 5)])
    await session.commit()
    events = [
        ('sale', now - timedelta(days=1), 1, 3),
        ('pending', now - timedelta(days=1), 1, 100),
        ('refusal', now - timedelta(days=1), 1, 200),
        ('sale', now - timedelta(days=91), 1, 300),
        ('sale', now + timedelta(days=1), 1, 400),
        ('sale', None, 2, 2),
        ('sale', now - timedelta(days=1), None, 9),
        ('sale', now - timedelta(days=1), 2, -2),
    ]
    for i, (state, event, pid, qty) in enumerate(events, 1):
        session.add(m.Order(id=i, user_id=1, status=m.OrderStatus.DONE, business_state=state,
                            business_state_at=event, created_at=now - timedelta(days=2)))
        session.add(m.OrderItem(order_id=i, product_id=pid, qty=qty, name='snapshot', price=100))
    await session.commit()
    products, sales = await repo.storefront_data(now - timedelta(days=90), now)
    assert {p.id for p in products} == {1, 2}
    assert sales == {1:3, 2:2}


@pytest_asyncio.fixture
async def client(store):
    session, repo = store
    app = FastAPI()
    app.include_router(api.router, prefix='/api/public')
    app.dependency_overrides[get_repo] = lambda: repo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://accordniche.pp.ua') as client:
        yield client, session, repo


@pytest.mark.asyncio
async def test_empty_database_has_no_fabricated_products_brands_or_hits(client):
    client, _, _ = client
    home = await client.get('/api/public/storefront')
    assert home.status_code == 200
    data = home.json()
    assert data['hits'] == data['recommended'] == data['new_arrivals'] == data['selection'] == []
    assert data['total'] == data['available'] == 0
    catalog = (await client.get('/api/public/aromas')).json()
    assert catalog['items'] == [] and catalog['brands'] == []
    assert (await client.get('/api/public/aromas/1')).status_code == 404


@pytest.mark.asyncio
async def test_volume_filter_uses_selected_sku_prices_stock_and_does_not_mutate_cached_catalog(client):
    client,session,_=client
    session.add_all([
        m.Product(id=1,sku='FILTER-1',brand='A',name='First 2 мл',volume_ml=2,price=10,stock=4),
        m.Product(id=2,sku='FILTER-2',brand='A',name='First 10 мл',volume_ml=10,price=200,stock=0),
        m.Product(id=3,sku='FILTER-3',brand='B',name='Second 10 мл',volume_ml=10,price=150,stock=3),
    ])
    await session.commit()
    filtered=(await client.get('/api/public/aromas?volume=10&sort=price_asc')).json()
    assert [item['name'] for item in filtered['items']]==['Second','First']
    first=next(item for item in filtered['items'] if item['name']=='First')
    assert first['min_price']=='200.00' and first['stock']==0 and first['default_product_id']==2
    assert first['volumes']==[10] and [p['id'] for p in first['variants']]==[2]
    available=(await client.get('/api/public/aromas?volume=10&available=true')).json()
    assert [item['name'] for item in available['items']]==['Second']
    regular=(await client.get('/api/public/aromas')).json()
    original=next(item for item in regular['items'] if item['name']=='First')
    assert original['min_price']=='10.00' and original['stock']==4 and len(original['variants'])==2
    assert (await client.get('/api/public/products?ids=2147483648')).status_code==422


@pytest.mark.asyncio
async def test_filters_group_pagination_details_and_public_projection(client):
    client, session, _ = client
    session.add_all([
        m.Product(id=1, sku='P1', brand='BRAND', name='Aroma 2 мл', volume_ml=2, price=20, stock=0),
        m.Product(id=2, sku='P2', brand='BRAND', name='Aroma 5 мл', volume_ml=5, price=100, stock=4, is_new=True, is_featured=True),
        m.Product(id=3, sku='P3', brand='SECOND', name='Other', price=200, stock=2),
        m.Product(id=4, sku='P4', brand='SECOND', name='Unavailable', price=1, stock=0),
    ])
    await session.commit()
    page = await client.get('/api/public/aromas?limit=1')
    assert page.status_code == 200 and page.headers['cache-control'] == 'no-store'
    data = page.json()
    assert data['total'] == 3 and len(data['items']) == 1
    assert data['brands'] == ['BRAND', 'SECOND']
    assert data['volumes'] == [2,5]
    assert len(data['items'][0]['variants']) == 2
    assert data['items'][0]['bestseller_rank'] is None
    assert '_units' not in page.text and '"sku"' not in page.text and 'revenue' not in page.text
    filtered = (await client.get('/api/public/aromas?brand=SECOND&available=true')).json()
    assert [g['name'] for g in filtered['items']] == ['Other']
    detail = (await client.get('/api/public/aromas/2')).json()
    assert detail['item']['id'] == 1 and len(detail['item']['variants']) == 2
    home = (await client.get('/api/public/storefront')).json()
    assert home['hits'] == [] and len(home['recommended']) == len(home['new_arrivals']) == 1
    assert (await client.get('/api/public/aromas?offset=100')).json()['items'] == []
    assert (await client.get('/api/public/aromas?kind=hits')).json()['items'] == []
    assert (await client.get('/api/public/aromas?sort=not-a-sort')).status_code == 422
    assert (await client.get('/api/public/aromas?volume=2&available=true')).json()['items'] == []
    assert len((await client.get('/api/public/aromas?volume=5&available=true')).json()['items']) == 1


@pytest.mark.asyncio
async def test_public_contacts_read_saved_seller_settings_without_exposing_secrets(client):
    from shop.services.shop_settings import invalidate_cache
    client, session, _ = client
    session.add_all([m.Setting(key='seller_phone', value='+380501234567'),
                     m.Setting(key='seller_email', value='shop@example.test'),
                     m.Setting(key='seller_name', value='Seller from database')])
    await session.commit()
    invalidate_cache()
    try:
        data = (await client.get('/api/public/site-config')).json()
        assert data['phone'] == '+380501234567'
        assert data['seller_name'] == 'Seller from database'
        assert data['email'] == 'shop@example.test'
        assert 'bot_token' not in data and 'card_number' not in data
    finally:
        invalidate_cache()


@pytest.mark.asyncio
async def test_cart_batch_only_returns_active_real_skus_and_rejects_unbounded_input(client):
    client, session, _ = client
    session.add_all([m.Product(id=1, sku='P1', name='No brand', price=100, stock=2),
                     m.Product(id=2, sku='P2', name='Hidden', price=100, stock=2, is_active=False)])
    await session.commit()
    assert [p['id'] for p in (await client.get('/api/public/products?ids=1,2,999')).json()] == [1]
    for ids in ['1;DROP TABLE orders', '-1', '0', ','.join(str(x) for x in range(1, 32)), '9999999999999999999']:
        assert (await client.get('/api/public/products', params={'ids':ids})).status_code == 422


@pytest.mark.asyncio
async def test_hits_are_sales_ranked_groups_not_individual_volumes(client):
    client, session, _ = client
    now = datetime.now(timezone.utc)
    session.add(m.User(id=1, tg_id=1, referral_code='hits-test'))
    session.add_all([
        m.Product(id=1, sku='H1', brand='BRAND', name='Aroma 2 мл', volume_ml=2, price=50, stock=3),
        m.Product(id=2, sku='H2', brand='BRAND', name='Aroma 5 мл', volume_ml=5, price=100, stock=3),
        m.Product(id=3, sku='H3', brand='OTHER', name='Other', price=200, stock=3, is_featured=True),
    ])
    session.add(m.Order(id=1, user_id=1, business_state='sale', business_state_at=now - timedelta(days=1)))
    session.add_all([m.OrderItem(order_id=1, product_id=i, qty=qty, price=100, name='snapshot') for i, qty in [(1,3),(2,3),(3,5)]])
    await session.commit()
    home = (await client.get('/api/public/storefront')).json()
    assert [g['name'] for g in home['hits']] == ['Aroma', 'Other']
    assert [g['bestseller_rank'] for g in home['hits']] == [1,2]
    assert len(home['hits'][0]['variants']) == 2
    assert len(home['recommended']) == 1


@pytest.mark.asyncio
async def test_catalog_pages_cover_all_groups_without_sku_duplicates(client):
    client, session, _ = client
    session.add_all([m.Product(id=i, sku='PAGE-' + str(i), brand='BRAND', name='Aroma ' + str(i), price=i, stock=1) for i in range(1, 31)])
    await session.commit()
    first = (await client.get('/api/public/aromas?limit=24&sort=price_asc')).json()
    second = (await client.get('/api/public/aromas?limit=24&sort=price_asc&offset=24')).json()
    assert first['total'] == second['total'] == 30
    assert len(first['items']) == 24 and len(second['items']) == 6
    assert {g['id'] for g in first['items']} | {g['id'] for g in second['items']} == set(range(1,31))
    assert not ({g['id'] for g in first['items']} & {g['id'] for g in second['items']})


@pytest.mark.asyncio
async def test_storefront_cache_is_single_flight_and_isolated_per_database(store):
    _, repo = store
    original, calls = repo.storefront_data, []
    async def counted(*args):
        calls.append(1)
        await asyncio.sleep(.01)
        return await original(*args)
    repo.storefront_data = counted
    await asyncio.gather(*(snapshot(repo, api.public_product) for _ in range(5)))
    assert len(calls) == 1
    other = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with other.begin() as connection:
            await connection.run_sync(m.Base.metadata.create_all)
        async with async_sessionmaker(other)() as session:
            session.add(m.Product(id=1, sku='OTHER-DB', brand='OTHER DATABASE', name='Other', price=100, stock=1))
            await session.commit()
            other_snapshot = await snapshot(SqlRepository(session), api.public_product)
            assert other_snapshot['groups'][0]['brand'] == 'OTHER DATABASE'
        assert (await snapshot(repo, api.public_product))['groups'] == []
    finally:
        _cache.pop(other, None)
        _locks.pop(other, None)
        await other.dispose()


def test_unsafe_photos_and_discount_labels_are_not_fabricated():
    p = product(1, photo_url='javascript:alert(1)', old_price=Decimal('50'), is_sale=True)
    output = api.public_product(p)
    assert output.photo_url is None and output.old_price is None and not output.is_sale


@pytest.mark.asyncio
async def test_visible_unbranded_product_can_be_ordered_and_invalid_price_keeps_cart(store):
    session, repo = store
    session.add(m.User(id=1, tg_id=1, referral_code='unbranded-cart'))
    session.add_all([m.Product(id=1, sku='CART1', name='Real product', brand='', price=100, stock=2),
                     m.Product(id=2, sku='CART2', name='Unpriced', price=0, stock=2)])
    await session.commit()
    await repo.replace_cart(1, [(1,1)])
    with pytest.raises(ValueError):
        await repo.replace_cart(1, [(2,1)])
    rows = (await session.execute(select(m.CartItem.product_id, m.CartItem.qty))).all()
    assert rows == [(1,1)]
