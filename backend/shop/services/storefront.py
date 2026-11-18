"""Public merchandising: real SKUs, stock-aware prices and completed-sales ranks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import unicodedata
import time
from weakref import WeakKeyDictionary
import asyncio

WINDOW_DAYS = 90
CACHE_SECONDS = 10
_cache = WeakKeyDictionary()
_locks = WeakKeyDictionary()


def normalized(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize('NFKC', str(value or '')).casefold())


def aroma_name(product):
    name = product.name.strip()
    volume = product.volume_ml
    if volume and volume > 0:
        # Strip only this SKU's declared volume, never a number in a fragrance name.
        name = re.sub(r'\s*[-–—,(]?\s*' + re.escape(str(volume)) + r'\s*(?:мл|ml)\s*\)?$', '', name, flags=re.I).strip() or name
    return name


def group_catalog(products, sales, serialize):
    groups = {}
    for product in products:
        if not product.is_published or not product.name.strip() or product.price <= 0:
            continue
        name, brand = aroma_name(product), product.brand.strip()
        key = normalized(brand) + ':' + normalized(name)
        # A missing identity must not merge unrelated unnamed records.
        group = groups.setdefault(key, dict(key=key, id=product.id, name=name, brand=brand,
            gender=product.gender or 'unisex', description=product.description or '', variants=[],
            categories=[], is_new=False, is_featured=False, is_set=False, _units=0, _order=product.sort_order))
        group['id'] = min(group['id'], product.id)
        group['variants'].append(serialize(product))
        group['is_new'] |= bool(product.is_new)
        group['is_featured'] |= bool(product.is_featured)
        group['_units'] += max(0, sales.get(product.id, 0))
        group['_order'] = min(group['_order'], product.sort_order)
        if product.category_id and product.category_name:
            category = {'id': product.category_id, 'name': product.category_name}
            if category not in group['categories']:
                group['categories'].append(category)
        group['is_set'] |= bool(re.search(r'\b(?:набір|набори|набор|сет|set|discovery)\b',
            ' '.join([name, product.category_name or '', product.subcategory_name or '']), re.I))
    result = list(groups.values())
    for group in result:
        group['variants'].sort(key=lambda p: (p.stock <= 0, p.volume_ml or 100000, p.price, p.id))
        buyable = [p for p in group['variants'] if p.stock > 0]
        prices = buyable or group['variants']
        group['default_product_id'] = min(prices, key=lambda p:(p.price,p.id)).id
        group['stock'] = sum(max(0, p.stock) for p in group['variants'])
        group['min_price'] = min(p.price for p in prices)
        units = [p.price / p.volume_ml for p in prices if p.volume_ml and p.volume_ml > 0]
        group['price_per_ml'] = min(units) if units else None
        group['image'] = next((p.photo_url or p.photo_endpoint for p in group['variants'] if p.photo_url or p.photo_endpoint), '')
        group['volumes'] = sorted({p.volume_ml for p in group['variants'] if p.volume_ml and p.volume_ml > 0})
        group['bestseller_rank'] = None
    ranked = sorted((g for g in result if g['_units'] > 0 and g['stock'] > 0),
                    key=lambda g: (-g['_units'], g['_order'], g['id']))
    for rank, group in enumerate(ranked, 1):
        group['bestseller_rank'] = rank
    return result


async def snapshot(repo, serialize):
    # Per-engine cache: no cross-database contamination. No private order data
    # leaves this service; only relative ranks are included in public responses.
    engine = getattr(getattr(repo, 's', None), 'bind', None)
    cached = _cache.get(engine) if engine is not None else None
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    async def load():
        now = datetime.now(timezone.utc)
        products, sales = await repo.storefront_data(now - timedelta(days=WINDOW_DAYS), now)
        result = {'groups': group_catalog(products, sales, serialize), 'updated_at': now.isoformat()}
        if engine is not None:
            _cache[engine] = (time.monotonic(), result)
        return result
    if engine is None:
        return await load()
    loop = asyncio.get_running_loop()
    if engine not in _locks or _locks[engine][0] is not loop:
        _locks[engine] = (loop, asyncio.Lock())
    async with _locks[engine][1]:
        cached = _cache.get(engine)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        return await load()


def sorted_groups(groups, sort='recommended'):
    available = lambda g: g['stock'] <= 0
    rank = lambda g: g['bestseller_rank'] or 1000000000
    if sort == 'price_asc': key = lambda g: (available(g), g['min_price'], g['id'])
    elif sort == 'price_desc': key = lambda g: (available(g), -g['min_price'], g['id'])
    elif sort == 'name': key = lambda g: (available(g), g['name'].casefold(), g['id'])
    elif sort == 'popular': key = lambda g: (available(g), rank(g), g['_order'], g['id'])
    elif sort == 'new': key = lambda g: (available(g), not g['is_new'], g['_order'], g['id'])
    else: key = lambda g: (available(g), not g['is_featured'], rank(g), g['_order'], g['id'])
    return sorted(groups, key=key)
