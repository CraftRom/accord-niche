"""Google Merchant Center feed and blog RSS (shop/services/feeds.py)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import seo as seo_router
from shop import models as m
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services import feeds, seo

G = '{http://base.google.com/ns/1.0}'


@pytest_asyncio.fixture
async def repo(tmp_path):
    feeds.invalidate()
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'feeds.db'))
    now = datetime.now(timezone.utc)
    async with engine.begin() as c:
        await c.run_sync(m.Base.metadata.create_all)
        base = dict(description=None, brand_id=None, name_lower='', is_active=True, photo_url='/media/a.jpg')
        for row in (dict(id=7, name='Aventus & Co', brand='Creed', sku='CRD-0007', price=Decimal('450'), stock=2,
                         volume_ml=5, concentration='edp', gender='male'),
                    dict(id=8, name='Aventus & Co 10 мл', brand='Creed', sku='CRD-0008', price=Decimal('800'), stock=0,
                         volume_ml=10, concentration='edp', gender='male'),
                    dict(id=9, name='No photo', brand='X', sku='X-9', price=Decimal('100'), stock=1, photo_url=None),
                    dict(id=10, name='Unpriced', brand='X', sku='X-10', price=Decimal('0'), stock=1),
                    dict(id=11, name='Hidden', brand='X', sku='X-11', price=Decimal('5'), stock=1, is_active=False)):
            await c.execute(insert(m.Product).values(**{**base, **row}))
        post = dict(search_text='', cover_url='', created_by='a', updated_by='a', author_name='Олена', body='Текст',
                    excerpt='')
        for row in (dict(id=1, slug='current', title='Як обрати <аромат>', excerpt='Коротко & ясно', status='published',
                         published_at=now - timedelta(days=1), cover_url='/media/c.jpg'),
                    dict(id=2, slug='hidden', title='Noindex', status='published', noindex=True,
                         published_at=now - timedelta(days=2)),
                    dict(id=3, slug='draft', title='Чернетка', status='draft'),
                    dict(id=4, slug='future', title='Майбутня', status='published', published_at=now + timedelta(days=1))):
            await c.execute(insert(m.BlogPost).values(**{**post, **row}))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlRepository(session)
    await engine.dispose()
    feeds.invalidate()


def items(xml):
    return ET.fromstring(xml).find('channel').findall('item')


@pytest.mark.asyncio
async def test_merchant_feed_has_one_item_per_sellable_sku(repo):
    xml, _ = await feeds.document(repo, 'merchant')
    rows = {item.findtext(G + 'id'): item for item in items(xml)}
    assert set(rows) == {'CRD-0007', 'CRD-0008'}, 'no photo, zero price and hidden products are left out'
    small = rows['CRD-0007']
    assert small.findtext(G + 'title') == 'Creed Aventus & Co EDP 5 мл (розпив)'
    assert small.findtext(G + 'price') == '450.00 UAH'
    assert small.findtext(G + 'availability') == 'in_stock'
    assert rows['CRD-0008'].findtext(G + 'availability') == 'out_of_stock'
    assert small.findtext(G + 'link').startswith('https://accordniche.pp.ua/aroma/7-')
    assert small.findtext(G + 'image_link').startswith('https://accordniche.pp.ua/')
    assert small.findtext(G + 'item_group_id') == rows['CRD-0008'].findtext(G + 'item_group_id')
    assert small.findtext(G + 'identifier_exists') == 'no'
    assert small.findtext(G + 'google_product_category') == '479'
    assert small.findtext(G + 'gender') == 'male' and small.findtext(G + 'condition') == 'new'
    assert small.findtext(G + 'size') == '5 мл' and small.findtext(G + 'unit_pricing_measure') == '5ml'
    assert small.findtext(G + 'description')


@pytest.mark.asyncio
async def test_blog_rss_lists_only_published_indexable_posts(repo):
    xml, _ = await feeds.document(repo, 'rss')
    root = ET.fromstring(xml)
    [item] = items(xml)
    assert item.findtext('title') == 'Як обрати <аромат>'
    assert item.findtext('link') == 'https://accordniche.pp.ua/blog/current'
    assert item.findtext('guid') == item.findtext('link')
    assert item.findtext('description') == 'Коротко & ясно'
    assert item.findtext('{http://purl.org/dc/elements/1.1/}creator') == 'Олена'
    assert item.findtext('pubDate').endswith('GMT')
    assert root.find('channel').findtext('language') == 'uk'


@pytest.mark.asyncio
async def test_feeds_follow_content_changes(repo):
    before, etag = await feeds.document(repo, 'rss')
    repo.s.add(m.BlogPost(id=5, slug='new', title='Нова', body='x', status='published', created_by='a', updated_by='a',
                          published_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await repo.s.commit()
    assert (await feeds.document(repo, 'rss'))[1] == etag, 'cached until content changes'
    seo.invalidate()
    after, new_etag = await feeds.document(repo, 'rss')
    assert new_etag != etag and len(items(after)) == 2


@pytest.mark.asyncio
async def test_endpoints_types_cache_and_etag(repo):
    app = FastAPI()
    app.include_router(seo_router.router, prefix='/api/public/seo')
    app.dependency_overrides[get_repo] = lambda: repo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://accordniche.pp.ua') as http:
        merchant = await http.get('/api/public/seo/merchant.xml')
        assert merchant.headers['content-type'].startswith('application/xml')
        assert merchant.headers['cache-control'] == 'public, max-age=300'
        assert (await http.get('/api/public/seo/merchant.xml',
                               headers={'If-None-Match': merchant.headers['etag']})).status_code == 304
        rss = await http.get('/api/public/seo/blog-rss.xml')
        assert rss.headers['content-type'].startswith('application/rss+xml') and '<rss' in rss.text


@pytest.mark.asyncio
async def test_every_page_advertises_the_blog_feed(repo):
    head = await seo.head_for(repo, '/')
    assert 'type="application/rss+xml"' in head and 'https://accordniche.pp.ua/blog/rss.xml' in head


def test_nginx_routes_feeds_to_the_api():
    from pathlib import Path
    conf = (Path(__file__).resolve().parents[2] / 'deploy/nginx/accord-domain-website.conf').read_text()
    assert 'location = /feeds/google-merchant.xml' in conf and '/api/public/seo/merchant.xml' in conf
    assert 'location = /blog/rss.xml' in conf and '/api/public/seo/blog-rss.xml' in conf
