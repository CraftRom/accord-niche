"""WebP copies of uploaded images for srcset: made once, cached, never for animations."""
import io
import os

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import public_catalog
from shop import models as m
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services import image_variants


@pytest.fixture
def media(tmp_path, monkeypatch):
    import shop.paths
    monkeypatch.setattr(shop.paths, 'DATA_ROOT', tmp_path)
    directory = tmp_path / 'media'
    directory.mkdir()
    Image.new('RGB', (2400, 1600), (180, 40, 40)).save(directory / 'bottle-0123456789ab.jpg', quality=95)
    frames = [Image.new('RGBA', (300, 300), c) for c in ('red', 'blue')]
    frames[0].save(directory / 'spin-0123456789ab.gif', save_all=True, append_images=frames[1:], duration=100, loop=0)
    return directory


def test_copy_is_a_smaller_webp_of_the_requested_width_and_cached(media):
    path = image_variants.variant('bottle-0123456789ab.jpg', 640)
    with Image.open(path) as image:
        assert image.format == 'WEBP' and image.size == (640, 427)
    assert path.parent.name == '.variants', 'nginx never serves dot directories directly'
    assert path.stat().st_size < (media / 'bottle-0123456789ab.jpg').stat().st_size / 5
    stamp = path.stat().st_mtime_ns
    assert image_variants.variant('bottle-0123456789ab.jpg', 640) == path and path.stat().st_mtime_ns == stamp
    os.utime(media / 'bottle-0123456789ab.jpg', None)  # the original changed: the copy is redone
    os.utime(path, (1, 1))
    image_variants.variant('bottle-0123456789ab.jpg', 640)
    assert path.stat().st_mtime > 1


def test_no_copy_for_animations_unknown_widths_or_bad_names(media):
    assert image_variants.variant('spin-0123456789ab.gif', 640) is None
    assert image_variants.variant('bottle-0123456789ab.jpg', 500) is None
    for name in ('../secret.jpg', '.variants', 'missing-0123.jpg', 'x.svg'):
        assert image_variants.variant(name, 640) is None


def test_deleted_media_loses_its_copies(media):
    for width in (320, 960):
        image_variants.variant('bottle-0123456789ab.jpg', width)
    assert len(list((media / '.variants').iterdir())) == 2
    image_variants.forget('bottle-0123456789ab.jpg')
    assert list((media / '.variants').iterdir()) == []


@pytest_asyncio.fixture
async def http(media):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as c:
        await c.run_sync(m.Base.metadata.create_all)
        await c.execute(insert(m.Product).values(id=5, name='Aventus 5 мл', brand='Creed', sku='CRD-0005', price=100,
                                                 stock=1, is_active=True, name_lower='', photo_url='/media/bottle-0123456789ab.jpg'))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        app = FastAPI()
        app.include_router(public_catalog.router, prefix='/api/public')
        app.dependency_overrides[get_repo] = lambda: SqlRepository(session)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://accordniche.pp.ua') as client:
            yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_product_photo_and_media_routes_serve_widths(http):
    small = await http.get('/api/public/catalog/5/photo', params={'w': 320})
    assert small.status_code == 200 and small.headers['content-type'] == 'image/webp'
    assert Image.open(io.BytesIO(small.content)).width == 320 and small.headers['cache-control'] == 'public, max-age=3600'
    original = await http.get('/api/public/catalog/5/photo')
    assert original.headers['content-type'] == 'image/jpeg' and len(original.content) > len(small.content)
    assert (await http.get('/api/public/catalog/5/photo', params={'w': 123})).status_code == 422
    cover = await http.get('/api/public/media/bottle-0123456789ab.jpg', params={'w': 960})
    assert cover.headers['content-type'] == 'image/webp' and 'immutable' in cover.headers['cache-control']
    animated = await http.get('/api/public/media/spin-0123456789ab.gif', params={'w': 640})
    assert animated.headers['content-type'] == 'image/gif', 'animation served as uploaded'
    for bad in ('../media/x.jpg', '.variants', 'nope-0123.jpg'):
        assert (await http.get('/api/public/media/' + bad)).status_code == 404
