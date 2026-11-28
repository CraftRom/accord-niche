from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import require_admin
from api.routers import store_audit
from shop.models import StoreAuditEvent
from shop.repo.factory import get_repo
from shop.services.store_checks import public_probe


@pytest.mark.asyncio
async def test_versions_retests_history_and_environment_isolation():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(StoreAuditEvent.__table__.create)
    maker = async_sessionmaker(engine)
    async def repository():
        async with maker() as session:
            yield SimpleNamespace(s=session)
    app = FastAPI()
    app.include_router(store_audit.router)
    app.dependency_overrides[get_repo] = repository
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(login="tester")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), follow_redirects=True, base_url="http://test/api/store-audit/") as client:
        assert not (await client.get("?environment=local")).json()["ready"]
        path = "cart/test?environment=local"
        body = dict(version=0, outcome="pass", actual="Контрольне замовлення", log="qa-1")
        first = await client.post(path, json=body)
        assert first.json()["status"] == "retest"
        assert (await client.post(path, json=body)).status_code == 409
        body["version"] = 1
        assert (await client.post(path, json=body)).status_code == 422
        body.update(outcome="fail", log="qa-2")
        assert (await client.post(path, json=body)).json()["status"] == "failed"
        body.update(outcome="pass", log="qa-3", version=2)
        assert (await client.post(path, json=body)).json()["status"] == "fixed"
        assert len((await client.get("cart/history?environment=local")).json()) == 3
        assert (await client.get("cart/history?environment=production")).json() == []
        assert (await client.post("api/test?environment=production", json={**body,"version":0})).status_code == 422
        assert "cart" not in (await client.get("?environment=local")).json()["blockers"]
        assert "cart" in (await client.get("?environment=production")).json()["blockers"]
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("urls,expected", [([], "fail"), (["https://accordniche.pp.ua/aroma/1-test"], "pass"),
                                          (["https://elfar.pp.ua/aroma/1-test"], "fail")])
async def test_sitemap_requires_actual_product_urls(urls, expected):
    xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(
        f'<url><loc>{u}</loc></url>' for u in urls) + '</urlset>'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,text=xml))) as client:
        assert (await public_probe("sitemap",client))[0] == expected
