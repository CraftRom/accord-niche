"""Site-wide test mode: every visitor sees the sandbox, crawlers the live site; main data untouched."""
import time
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import Principal, require_sysadmin
from api.routers import blog, public_catalog, seo as seo_router, test_mode as test_mode_router, website_shop
from api.test_mode_middleware import SandboxModeMiddleware
from shop import models as m
from shop.entities import OperatorRole
from shop.services import shop_settings, storefront, test_mode

SYSADMIN = Principal(login='root', name='Root', role=OperatorRole.SYSADMIN, operator_id=0)
SITE = 'https://accordniche.pp.ua'


@pytest_asyncio.fixture
async def site(tmp_path, monkeypatch):
    import shop.db
    import shop.paths
    monkeypatch.setattr(shop.paths, 'DATA_ROOT', tmp_path / 'data')
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'main.db'))
    async with engine.begin() as c:
        await c.run_sync(m.Base.metadata.create_all)
        await c.execute(insert(m.Product).values(id=1, name='Main Only', brand='Real', sku='REAL-0001', price=Decimal('100'),
                                                 stock=1, is_active=True, name_lower='main only'))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(shop.db, 'SessionMaker', maker)
    storefront._cache.clear()
    shop_settings.invalidate_cache()
    app = FastAPI()
    app.add_middleware(SandboxModeMiddleware)
    app.include_router(public_catalog.router, prefix='/api/public')
    app.include_router(seo_router.router, prefix='/api/public/seo')
    app.include_router(blog.public, prefix='/api/public/blog')
    app.include_router(website_shop.router, prefix='/api/web')
    app.include_router(test_mode_router.admin, prefix='/api/system/test-mode')
    app.include_router(test_mode_router.public, prefix='/api/public/test-mode')
    app.dependency_overrides[require_sysadmin] = lambda: SYSADMIN
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=SITE) as client:
        yield client, maker
    await test_mode.disable()
    await engine.dispose()


BROWSER = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1'}
GOOGLEBOT = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}


async def enable(client, hours=2):
    info = (await client.post('/api/system/test-mode', json={'hours': hours})).json()
    assert info['active'] and info['aromas'] == 10 and info['products'] == 30 and info['posts'] == 3
    assert info['site_url'] == 'https://accordniche.pp.ua/' and 'enter_url' not in info, 'no link needed'
    return info


@pytest.mark.asyncio
async def test_every_visitor_sees_the_sandbox_as_soon_as_it_is_on(site):
    client, maker = site
    assert [i['name'] for i in (await client.get('/api/public/aromas', headers=BROWSER)).json()['items']] == ['Main Only']
    await enable(client)
    # A fresh visitor: no link, no cookie.
    async with httpx.AsyncClient(transport=client._transport, base_url=SITE) as visitor:
        first = await visitor.get('/api/public/aromas', params={'limit': 30}, headers=BROWSER)
        assert 'accord_test_view=1' in first.headers['set-cookie'], 'the website switches to the test cart'
        sandbox = first.json()
        assert sandbox['total'] == 10 and 'Creed' in sandbox['brands'] and 'Real' not in sandbox['brands']
        aventus = next(item for item in sandbox['items'] if item['name'] == 'Aventus')
        assert aventus['path'] == '/aroma/1-creed-aventus' and aventus['volumes'] == [2, 5, 10]
        assert aventus['top_notes'].startswith('Ананас') and aventus['image'].startswith(test_mode.MEDIA_PREFIX)
        response = await visitor.get('/api/public/blog', headers=BROWSER)
        assert len(response.json()['items']) == 3
        assert response.headers['x-accord-test-mode'] == '1' and 'no-store' in response.headers['cache-control']
        assert 'set-cookie' not in response.headers, 'the marker is set once'
        picture = await visitor.get('/api/public/test-mode/media/creed-aventus.png', headers=BROWSER)
        assert picture.status_code == 200 and picture.headers['content-type'] == 'image/png'
        status = (await visitor.get('/api/public/test-mode/status', headers=BROWSER)).json()
        assert status['active'] is True and status['expires_at']
    # Nothing reached the main database.
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(m.Product)) == 1
        assert await session.scalar(select(func.count()).select_from(m.BlogPost)) == 0


@pytest.mark.asyncio
async def test_crawlers_and_link_previews_keep_the_live_site(site):
    client, _ = site
    await enable(client)
    for agent in (GOOGLEBOT, {'User-Agent': 'TelegramBot (like TwitterBot)'}, {'User-Agent': 'facebookexternalhit/1.1'}):
        live = (await client.get('/api/public/aromas', headers=agent))
        assert [i['name'] for i in live.json()['items']] == ['Main Only'] and 'x-accord-test-mode' not in live.headers
        assert (await client.get('/api/public/test-mode/status', headers=agent)).json()['active'] is False
    head = (await client.get('/api/public/seo/head', headers={**GOOGLEBOT, 'X-Accord-Path': '/catalog'})).text
    assert '[ТЕСТ]' not in head


@pytest.mark.asyncio
async def test_sandbox_pages_are_noindex_and_outside_writes_are_refused(site):
    client, _ = site
    await enable(client)
    head = (await client.get('/api/public/seo/head', headers={**BROWSER, 'X-Accord-Path': '/aroma/1-creed-aventus'})).text
    assert '<title>[ТЕСТ] Creed Aventus EDP' in head and 'noindex, follow' in head
    assert '"@type":"ProductGroup"' in head
    for path in ('/api/web/checkout', '/api/web/auth/google', '/api/web/profile/phone/send'):
        refused = await client.post(path, json={}, headers=BROWSER)
        assert refused.status_code == 403 and 'тест-режимі' in refused.json()['detail']


@pytest.mark.asyncio
async def test_disable_and_expiry_end_the_sandbox_and_clear_the_cart_marker(site):
    client, _ = site
    await enable(client)
    assert any(f.name.startswith('sandbox-') for f in test_mode.root().iterdir())
    assert (await client.delete('/api/system/test-mode')).json() == {'active': False}
    assert not any(f.name.startswith('sandbox-') for f in test_mode.root().iterdir())
    back = await client.get('/api/public/aromas', headers={**BROWSER, 'Cookie': 'g_state={"i_l":0}; accord_test_view=1'})
    assert [i['name'] for i in back.json()['items']] == ['Main Only']
    assert 'accord_test_view=; Max-Age=0' in back.headers['set-cookie'], 'the website drops its test cart'
    assert (await client.get('/api/public/test-mode/media/creed-aventus.png', headers=BROWSER)).status_code == 404
    await enable(client)
    import json
    state = json.loads((test_mode.root() / 'state.json').read_text())
    state['expires'] = int(time.time()) - 1
    (test_mode.root() / 'state.json').write_text(json.dumps(state))
    test_mode._forget_cache()
    assert (await client.get('/api/system/test-mode')).json() == {'active': False}
    assert [i['name'] for i in (await client.get('/api/public/aromas', headers=BROWSER)).json()['items']] == ['Main Only']
    assert list(test_mode.root().iterdir()) == []


@pytest.mark.asyncio
async def test_sandbox_never_fills_the_shared_settings_cache(site):
    client, _ = site
    shop_settings.invalidate_cache()
    await enable(client)
    await client.get('/api/public/site-config', headers=BROWSER)
    assert shop_settings._cache is None, 'live settings are not replaced by sandbox values'


def test_runtime_image_installs_the_sandbox_driver():
    """Production log 26.11: enabling test mode failed with 500, no aiosqlite in the image."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('requirements.txt', 'requirements-lock.txt'):
        lines = [line.split('#')[0].strip().lower() for line in (root / name).read_text().splitlines()]
        assert any(line.startswith('aiosqlite==') for line in lines), name


@pytest.mark.asyncio
async def test_missing_driver_is_a_clear_503_not_a_crash(site, monkeypatch):
    client, _ = site
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name, *a: None if name == 'aiosqlite' else real(name, *a))
    response = await client.post('/api/system/test-mode', json={'hours': 1})
    assert response.status_code == 503 and 'aiosqlite' in response.json()['detail']
    assert (await client.get('/api/system/test-mode')).json() == {'active': False}


def test_runtime_image_installs_the_sandbox_driver():
    """Production log 26.11: enabling test mode failed with 500, no aiosqlite in the image."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ('requirements.txt', 'requirements-lock.txt'):
        lines = [line.split('#')[0].strip().lower() for line in (root / name).read_text().splitlines()]
        assert any(line.startswith('aiosqlite==') for line in lines), name


@pytest.mark.asyncio
async def test_missing_driver_is_a_clear_503_not_a_crash(site, monkeypatch):
    client, _ = site
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name, *a: None if name == 'aiosqlite' else real(name, *a))
    response = await client.post('/api/system/test-mode', json={'hours': 1})
    assert response.status_code == 503 and 'aiosqlite' in response.json()['detail']
    assert (await client.get('/api/system/test-mode')).json() == {'active': False}




def test_reading_the_state_never_needs_a_writable_data_directory(tmp_path, monkeypatch):
    """The state is read on every website API request: a read-only /data must not break the shop."""
    import shop.paths
    readonly = tmp_path / 'ro'
    readonly.mkdir()
    readonly.chmod(0o500)
    monkeypatch.setattr(shop.paths, 'DATA_ROOT', readonly / 'data')
    test_mode._forget_cache()
    try:
        assert test_mode.current() is None and not (readonly / 'data').exists()
    finally:
        readonly.chmod(0o700)
        test_mode._forget_cache()
