"""Perfume card and SEO fields: validated, shared by every volume, inherited by a new volume."""
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import Principal, require_admin, require_staff
from api.routers import catalog, public_catalog
from shop import models as m
from shop.entities import OperatorRole
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services.aroma_seo import aroma_path, slugify

ADMIN = Principal(login='owner', name='Owner', role=OperatorRole.SYSADMIN, operator_id=0)


@pytest_asyncio.fixture
async def http():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        repo = SqlRepository(session)
        app = FastAPI()
        app.include_router(catalog.router, prefix='/api/catalog')
        app.include_router(public_catalog.router, prefix='/api/public')
        app.dependency_overrides[get_repo] = lambda: repo
        app.dependency_overrides[require_admin] = lambda: ADMIN
        app.dependency_overrides[require_staff] = lambda: ADMIN
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://dashboard.accordniche.pp.ua') as client:
            yield client
    await engine.dispose()


def product(**changes):
    return {'name': 'Aventus 5 мл', 'brand': 'Creed', 'volume_ml': 5, 'price': '450', 'stock': 3, **changes}


def test_slugs_are_latin_and_readable():
    assert slugify('Kilian', 'Angels’ Share') == 'kilian-angels-share'
    assert slugify('Ex Nihilo', 'Fleur Narcotique') == 'ex-nihilo-fleur-narcotique'
    assert slugify('Жозефіна', 'Щастя & Ягоди') == 'zhozefina-shchastia-and-iahody'
    assert aroma_path(7, 'Creed', 'Aventus') == '/aroma/7-creed-aventus'


@pytest.mark.asyncio
async def test_aroma_fields_are_shared_by_volumes_and_inherited(http):
    first = (await http.post('/api/catalog/products', json=product(top_notes='Ананас', concentration='EDP',
                                                                   seo_title='Creed Aventus — розпив'))).json()
    assert first['concentration'] == 'edp' and first['seo_title'] == 'Creed Aventus — розпив'
    second = (await http.post('/api/catalog/products', json=product(name='Aventus 10 мл', volume_ml=10, price='800'))).json()
    assert second['top_notes'] == 'Ананас' and second['seo_title'] == 'Creed Aventus — розпив', 'new volume inherits'
    other = (await http.post('/api/catalog/products', json=product(name='Silver Mountain Water 5 мл'))).json()
    assert other['top_notes'] == ''
    patched = await http.patch(f"/api/catalog/products/{second['id']}", json={'base_notes': 'Мускус', 'release_year': 2010,
                                                                            'perfumer': 'Olivier Creed'})
    assert patched.status_code == 200, patched.text
    again = (await http.get(f"/api/catalog/products/{first['id']}")).json()
    assert again['base_notes'] == 'Мускус' and again['release_year'] == 2010 and again['perfumer'] == 'Olivier Creed'
    assert (await http.get(f"/api/catalog/products/{other['id']}")).json()['base_notes'] == ''
    # Explicit null clears; PUT without the field keeps it.
    await http.patch(f"/api/catalog/products/{first['id']}", json={'perfumer': None})
    assert (await http.get(f"/api/catalog/products/{second['id']}")).json()['perfumer'] == ''
    await http.put(f"/api/catalog/products/{first['id']}", json=product())
    assert (await http.get(f"/api/catalog/products/{first['id']}")).json()['base_notes'] == 'Мускус'
    aroma = (await http.get(f"/api/public/aromas/{second['id']}")).json()['item']
    assert aroma['path'] == f"/aroma/{first['id']}-creed-aventus" and aroma['base_notes'] == 'Мускус'
    assert aroma['concentration'] == 'edp' and 'seo_title' not in aroma


@pytest.mark.asyncio
async def test_invalid_aroma_fields_are_refused(http):
    assert (await http.post('/api/catalog/products', json=product(concentration='perfume-ish'))).status_code == 422
    assert (await http.post('/api/catalog/products', json=product(release_year=1500))).status_code == 422
    assert (await http.post('/api/catalog/products', json=product(seo_title='x' * 121))).status_code == 422
    assert (await http.post('/api/catalog/products', json=product(top_notes='a\x00b'))).status_code == 422


@pytest.mark.asyncio
async def test_indexnow_gets_the_canonical_aroma_address(http, monkeypatch):
    from shop.services import indexnow
    monkeypatch.setenv('ACCORD_INDEXNOW_KEY', 'a1b2c3d4e5f6a7b8')
    seen = []
    monkeypatch.setattr(indexnow, 'notify', lambda *urls: seen.extend(urls))
    first = (await http.post('/api/catalog/products', json=product())).json()
    second = (await http.post('/api/catalog/products', json=product(name='Aventus 10 мл', volume_ml=10))).json()
    await http.patch(f"/api/catalog/products/{second['id']}", json={'top_notes': 'Ананас'})
    assert set(seen) == {f"https://accordniche.pp.ua/aroma/{first['id']}-creed-aventus"}
