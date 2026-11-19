"""Server-side SEO head tags and sitemap for the main website."""
from __future__ import annotations

import json
import re
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
from shop.services import seo


@pytest_asyncio.fixture
async def repo(tmp_path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'seo.db'))
    now = datetime.now(timezone.utc)
    async with engine.begin() as c:
        await c.run_sync(m.Base.metadata.create_all)
        await c.execute(insert(m.Brand), [dict(id=1, name='Hidden', name_key='hidden', is_active=False)])
        base = dict(volume_ml=None, description=None, photo_url=None, brand_id=None, name_lower='')
        for row in (dict(id=7, name='Aventus </script>', brand='Creed', sku='CRD-0007', price=Decimal('450'), stock=0,
                         is_active=True, volume_ml=5, description='**Ананас** і [берёза](https://x) & "лапки"',
                         photo_url='javascript:alert(1)'),
                    dict(id=8, name='In hidden group', brand='X', sku='HID-0008', price=Decimal('10'), stock=1,
                         is_active=True, brand_id=1),
                    dict(id=9, name='Unpriced', brand='X', sku='UNP-0009', price=Decimal('0'), stock=1, is_active=True)):
            await c.execute(insert(m.Product).values(**{**base, **row}))
        post = dict(excerpt='', search_text='', cover_url='', created_by='a', updated_by='a', author_name='Редакція ACCORD NICHE',
                    published_at=None)
        for row in (dict(id=1, slug='current', title='Як обрати', body='## Заголовок\nТекст ![img](/media/a.jpg)',
                         cover_url='//evil.example/x.jpg', status='published', published_at=now - timedelta(days=1),
                         author_name='Олена'),
                    dict(id=2, slug='draft', title='Чернетка', body='x', status='draft'),
                    dict(id=3, slug='future', title='Майбутня', body='x', status='published', published_at=now + timedelta(days=1))):
            await c.execute(insert(m.BlogPost).values(**{**post, **row}))
        await c.execute(insert(m.BlogSlug), [dict(slug='current', post_id=1), dict(slug='old', post_id=1),
                                             dict(slug='draft', post_id=2), dict(slug='future', post_id=3)])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlRepository(session)
    await engine.dispose()


def ld(head):
    return [json.loads(raw) for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', head)]


@pytest.mark.asyncio
async def test_product_head_is_escaped_structured_and_honest_about_stock(repo):
    head = await seo.head_for(repo, '/aroma/7?utm_source=ig')
    assert '<title>Creed Aventus &lt;/script&gt;, 5 мл — 450.00 ₴ | ACCORD NICHE</title>' in head
    assert head.count('</script>') == len(ld(head)) == 1
    data = ld(head)[0]
    assert data['@type'] == 'Product' and data['offers']['availability'].endswith('OutOfStock')
    assert data['offers']['price'] == '450.00' and data['offers']['priceCurrency'] == 'UAH'
    assert 'javascript:' not in head, 'unsafe image URLs are never emitted'
    assert 'Ананас і берёза &amp; &quot;лапки&quot;' in head and '**' not in head
    assert 'rel="canonical" href="https://accordniche.pp.ua/aroma/7"' in head


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/aroma/8', '/aroma/9', '/aroma/404', '/blog/draft', '/blog/future', '/blog/none',
                                  '/checkout', '/profile', '/order/success', '/unknown/page'])
async def test_hidden_private_and_unknown_pages_are_generic_and_noindex(repo, path):
    head = await seo.head_for(repo, path)
    assert 'name="robots" content="noindex, follow"' in head
    assert 'In hidden group' not in head and 'Чернетка' not in head and 'Майбутня' not in head
    assert 'canonical' not in head


@pytest.mark.asyncio
async def test_old_blog_slug_points_to_the_current_canonical_and_drops_protocol_relative_images(repo):
    head = await seo.head_for(repo, '/blog/old')
    assert 'href="https://accordniche.pp.ua/blog/current"' in head
    data = ld(head)[0]
    assert data['@type'] == 'BlogPosting' and data['author'] == {'@type': 'Person', 'name': 'Олена'}
    assert 'evil.example' not in head and 'og:image' not in head
    assert 'Заголовок Текст' in head and '##' not in head and 'img' not in head.split('<script')[0]


@pytest.mark.asyncio
async def test_static_pages_have_their_own_titles_and_canonicals(repo):
    assert 'href="https://accordniche.pp.ua"' in await seo.head_for(repo, '/')
    catalog = await seo.head_for(repo, '/catalog/')
    assert 'Каталог нішевих ароматів' in catalog and 'href="https://accordniche.pp.ua/catalog"' in catalog


@pytest.mark.asyncio
async def test_sitemap_lists_only_published_content(repo):
    xml = await seo.sitemap(repo)
    assert '<loc>https://accordniche.pp.ua/aroma/7</loc>' in xml
    for hidden in ('/aroma/8<', '/aroma/9<', '/blog/draft', '/blog/future', '/blog/old'):
        assert hidden not in xml
    assert '<loc>https://accordniche.pp.ua/blog/current</loc><lastmod>' in xml


def test_absolute_urls_accept_only_same_site_paths_or_https():
    assert seo.absolute('/media/a.jpg') == 'https://accordniche.pp.ua/media/a.jpg'
    assert seo.absolute('https://cdn.example/a.jpg') == 'https://cdn.example/a.jpg'
    for bad in ('//evil.example/a.jpg', 'http://x/a.jpg', 'javascript:alert(1)', 'https://u:p@x/a', '', None):
        assert seo.absolute(bad) is None


@pytest.mark.asyncio
async def test_endpoint_prefers_the_nginx_original_uri_header(repo):
    app = FastAPI()
    app.include_router(seo_router.router, prefix='/api/public/seo')
    app.dependency_overrides[get_repo] = lambda: repo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://accordniche.pp.ua') as http:
        response = await http.get('/api/public/seo/head', headers={'X-Accord-Path': '/aroma/7'})
        assert response.status_code == 200 and response.headers['content-type'].startswith('text/html')
        assert 'Creed Aventus' in response.text
        sitemap = await http.get('/api/public/seo/sitemap.xml')
        assert sitemap.headers['content-type'].startswith('application/xml')
