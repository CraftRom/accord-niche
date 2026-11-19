"""A12 load stand: 10 000 SKU and 100 000 orders in a NEW SQLite file.

    cd backend && python -m tools.accord_bench /tmp/accord-bench.db

Prints time, SQL statements and peak Python memory for the website order
history (first and a deep page), the profile and the catalog snapshot. It
refuses an existing file, so it can never write into a real database.
"""
import asyncio, sys, time, tracemalloc
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi import Request
from shop import models as m
from shop.repo.sql import SqlRepository
from api.routers import website_shop as web
from api.routers import public_catalog

async def main(path):
    from pathlib import Path
    if Path(path).exists():
        raise SystemExit('Вкажіть шлях до нового файла: стенд не пише в наявну БД')
    engine = create_async_engine('sqlite+aiosqlite:///' + path)
    async with engine.begin() as c:
        await c.run_sync(m.Base.metadata.create_all)
    now = datetime.now(timezone.utc)
    async with engine.begin() as c:
        await c.execute(insert(m.User), [{'id': 1, 'tg_id': -1, 'referral_code': 'A'}, {'id': 2, 'tg_id': 99, 'referral_code': 'B'}]
                        + [{'id': 10 + i, 'tg_id': -(10 + i), 'referral_code': f'U{i}'} for i in range(2000)])
        await c.execute(insert(m.WebsiteAccount), [{'id': 1, 'user_id': 1, 'google_sub': 'g', 'linked_telegram_user_id': 2}])
        await c.execute(insert(m.Brand), [{'id': i + 1, 'name': f'B{i}', 'name_key': f'b{i}', 'is_active': True} for i in range(40)])
        await c.execute(insert(m.Product), [{'id': i, 'brand_id': 1 + i % 40, 'name': f'Aroma {i // 3} {50 + 25 * (i % 3)} мл',
            'sku': f'SKU-{i:05d}', 'price': Decimal(100 + i % 500), 'stock': i % 7, 'is_active': True, 'brand': f'B{i % 40}',
            'volume_ml': 50 + 25 * (i % 3), 'name_lower': ''} for i in range(1, 10001)])
        orders = []
        for i in range(100000):
            uid = 1 if i % 20 == 0 else 2 if i % 20 == 1 else 10 + i % 2000
            orders.append({'id': i + 1, 'user_id': uid, 'status': m.OrderStatus.DONE, 'business_state': 'sale',
                           'business_state_at': now - timedelta(minutes=i), 'created_at': now - timedelta(minutes=i),
                           'subtotal': Decimal(100), 'discount': Decimal(0), 'bonus_used': Decimal(0), 'total': Decimal(100),
                           'payment_method': 'cod', 'search_key': ''})
        await c.execute(insert(m.Order), orders)
        await c.execute(insert(m.OrderItem), [{'order_id': i + 1, 'product_id': 1 + i % 10000, 'name': 'x', 'price': Decimal(100), 'qty': 1} for i in range(100000)])
    counter = {'n': 0}
    event.listen(engine.sync_engine, 'before_cursor_execute', lambda *a, **k: counter.__setitem__('n', counter['n'] + 1))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def account(_request, repo):
        return await repo.s.get(m.WebsiteAccount, 1)
    web._required_account = account
    req = Request({'type': 'http', 'method': 'GET', 'scheme': 'https', 'path': '/', 'headers': [], 'query_string': b''})

    async def measure(label, call):
        async with maker() as s:
            counter['n'] = 0; tracemalloc.start(); started = time.perf_counter()
            result = await call(SqlRepository(s))
            elapsed = (time.perf_counter() - started) * 1000; _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            print(f'{label:34s} {elapsed:8.1f} ms  {counter["n"]:3d} SQL  peak {peak / 1e6:6.1f} MB')
            return result

    for offset in (0, 3000):
        await measure(f'web orders offset={offset}', lambda r: web.orders(req, limit=30, offset=offset, repo=r))
    await measure('web profile', lambda r: web.profile(req, r))
    from shop.services import storefront
    storefront._cache.clear()
    await measure('catalog snapshot (cold)', lambda r: storefront.snapshot(r, public_catalog.public_product))
    await measure('catalog snapshot (cached)', lambda r: storefront.snapshot(r, public_catalog.public_product))
    await engine.dispose()

asyncio.run(main(sys.argv[1]))
