"""HTTP authorization checks and real SQLite session revocation for fixed groups."""
from __future__ import annotations
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api import auth
from api.browser_sessions import profile
from api.routers import settings as settings_api, operators, blog, store_audit
from api.schemas import ShopSettingsIn
from shop.access import MODULE_FIELDS, INFRA_FIELDS
from shop.config import settings
from shop.entities import Operator, OperatorRole as Role
from shop.repo.factory import get_repo
from shop.services.shop_settings import ShopSettings


class Repo:
    def __init__(self):
        self.operators = {i: Operator(i, name, name, role, True) for i, name, role in [
            (1, 'administrator', Role.ADMIN), (2, 'manager', Role.MANAGER), (3, 'otheradmin', Role.ADMIN)]}
        self.changed = []
    async def get_operator(self, oid): return self.operators.get(oid)
    async def get_operator_by_login(self, login): return next((o for o in self.operators.values() if o.login == login), None)
    async def list_operators(self): return list(self.operators.values())
    async def create_operator(self, data):
        self.changed.append(('create', data))
        row = Operator(4, data['login'], data['name'], Role(data['role']), True)
        self.operators[4] = row
        return row
    async def update_operator(self, oid, data):
        self.changed.append(('update', data))
        row = self.operators[oid]
        for key, value in data.items(): setattr(row, key, Role(value) if key == 'role' else value)
        return row
    async def delete_operator(self, oid): self.changed.append(('disable', oid)); return True
    async def purge_operator(self, oid): self.changed.append(('purge', oid)); return True



@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings, 'jwt_secret', 'unit-test-secret-' * 4)
    monkeypatch.setattr(settings, 'dashboard_login', 'root')
    repo = Repo()
    snapshot = ShopSettings.from_env()
    writes = []
    async def read(_repo): return snapshot
    async def save(_repo, payload):
        nonlocal snapshot
        writes.append(payload)
        snapshot = replace(snapshot, **payload)
        return snapshot
    monkeypatch.setattr(settings_api, 'get_shop_settings', read)
    monkeypatch.setattr(settings_api, 'save_shop_settings', save)
    app = FastAPI()
    app.include_router(store_audit.router)
    app.include_router(settings_api.router, prefix='/api/settings')
    app.include_router(operators.router, prefix='/api/operators')
    app.include_router(blog.admin, prefix='/api/blog')
    app.dependency_overrides[get_repo] = lambda: repo
    from shop.db import get_session
    app.dependency_overrides[get_session] = lambda: None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        yield SimpleNamespace(http=http, repo=repo, writes=writes)


def headers(role):
    login, oid = {Role.SYSADMIN: ('root', 0), Role.ADMIN: ('administrator', 1), Role.MANAGER: ('manager', 2)}[role]
    return {'Authorization': 'Bearer ' + auth.create_token(login, role, oid)}


@pytest.mark.asyncio
@pytest.mark.parametrize('field', sorted(ShopSettingsIn.model_fields))
async def test_manager_cannot_write_any_settings_field(client, field):
    result = await client.http.put('/api/settings', json={field: None}, headers=headers(Role.MANAGER))
    assert result.status_code == 403, (field, result.text)
    assert not client.writes


@pytest.mark.asyncio
async def test_manager_cannot_read_settings_even_with_ui_permission_forgery(client):
    result = await client.http.get('/api/settings', headers={**headers(Role.MANAGER), 'X-Role': 'admin'})
    assert result.status_code == 403
    assert (await client.http.put('/api/settings', json={}, headers=headers(Role.MANAGER))).status_code == 403
    assert (await client.http.get('/api/operators', headers=headers(Role.MANAGER))).status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_manage_blog_with_a_valid_staff_token(client):
    for method,path in [('GET','/api/blog/posts'),('GET','/api/blog/posts/1'),('POST','/api/blog/posts'),
                        ('PUT','/api/blog/posts/1'),('GET','/api/blog/comments'),
                        ('POST','/api/blog/comments/1/moderate'),('POST','/api/blog/posts/1/reply')]:
        result=await client.http.request(method,path,headers=headers(Role.MANAGER),json={})
        assert result.status_code==403,(method,path,result.text)
    for role in [Role.ADMIN,Role.SYSADMIN]:
        result=await client.http.post('/api/blog/posts',headers=headers(role),json={})
        assert result.status_code==422


@pytest.mark.asyncio
@pytest.mark.parametrize('field', sorted(MODULE_FIELDS))
async def test_administrator_can_toggle_existing_modules(client, field):
    result = await client.http.put('/api/settings', json={field: True}, headers=headers(Role.ADMIN))
    assert result.status_code == 200, (field, result.text)
    assert client.writes[-1] == {field: True}


@pytest.mark.asyncio
@pytest.mark.parametrize('field', sorted(INFRA_FIELDS))
async def test_administrator_cannot_write_infrastructure_fields(client, field):
    result = await client.http.put('/api/settings', json={field: None}, headers=headers(Role.ADMIN))
    assert result.status_code == 403, (field, result.text)
    assert not client.writes


@pytest.mark.asyncio
async def test_mixed_allowed_and_forbidden_settings_are_rejected_atomically(client):
    result = await client.http.put('/api/settings', json={'bonus_enabled': True, 'jwt_ttl_hours': 24}, headers=headers(Role.ADMIN))
    assert result.status_code == 403
    assert not client.writes
    assert (await client.http.put('/api/settings', json={'jwt_ttl_hours': 24}, headers=headers(Role.SYSADMIN))).status_code == 200
    assert (await client.http.get('/api/settings/environment', headers=headers(Role.ADMIN))).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_manage_managers_but_cannot_assign_or_modify_administrators(client):
    payload = {'login': 'newstaff', 'password': 'Safe-new-password-123', 'role': Role.ADMIN.value}
    assert (await client.http.post('/api/operators', json=payload, headers=headers(Role.ADMIN))).status_code == 403
    assert not client.repo.changed
    for method, path, body in [('PUT', '/api/operators/3', {'password': 'Reset-new-password-123'}),
                               ('DELETE', '/api/operators/3', None), ('DELETE', '/api/operators/3/purge', None),
                               ('PUT', '/api/operators/2', {'role': Role.ADMIN.value})]:
        result = await client.http.request(method, path, json=body, headers=headers(Role.ADMIN))
        assert result.status_code == 403, result.text
    assert not client.repo.changed
    payload['role'] = Role.MANAGER.value
    assert (await client.http.post('/api/operators', json=payload, headers=headers(Role.ADMIN))).status_code == 201


@pytest.mark.asyncio
async def test_sysadmin_manages_admin_accounts_and_reserved_login_cannot_be_shadowed(client):
    payload = {'login': 'anotheradmin', 'password': 'Safe-new-password-123', 'role': Role.ADMIN.value}
    assert (await client.http.post('/api/operators', json=payload, headers=headers(Role.SYSADMIN))).status_code == 201
    assert (await client.http.put('/api/operators/3', json={'name': 'Renamed admin'}, headers=headers(Role.SYSADMIN))).status_code == 200
    payload['login'] = 'ROOT'
    assert (await client.http.post('/api/operators', json=payload, headers=headers(Role.SYSADMIN))).status_code == 409
    payload['role'] = Role.SYSADMIN.value
    payload['login'] = 'superuser'
    assert (await client.http.post('/api/operators', json=payload, headers=headers(Role.ADMIN))).status_code == 422


@pytest.mark.parametrize('role', list(Role))
def test_session_profile_reports_the_actual_group_capabilities(role):
    data = profile(auth.Principal('name', 'Name', role, 1), 'csrf')
    assert data['role_title']
    if role == Role.MANAGER:
        assert data['editable_settings'] == []
        assert data['assignable_roles'] == []
        assert 'settings.manage' not in data['permissions']
    else:
        assert MODULE_FIELDS <= set(data['editable_settings'])
    if role == Role.ADMIN:
        assert set(data['editable_settings']).isdisjoint(INFRA_FIELDS)
        assert data['assignable_roles'] == ['operator']
    if role == Role.SYSADMIN:
        assert set(data['editable_settings']) == set(ShopSettingsIn.model_fields)


@pytest.mark.asyncio
async def test_role_change_revokes_existing_bearer_and_cookie_principals():
    from shop import models
    from shop.repo.sql import SqlRepository
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.run_sync(models.Operator.__table__.create)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            repo = SqlRepository(session)
            row = await repo.create_operator({'login': 'changing', 'name': 'Changing', 'role': Role.ADMIN.value,
                                              'password_hash': 'not-used', 'is_active': True})
            before = row.auth_version
            row = await repo.update_operator(row.id, {'name': 'Unchanged group'})
            assert row.auth_version == before
            row = await repo.update_operator(row.id, {'role': Role.MANAGER.value})
            assert row.auth_version == before + 1
            # Both the signed token and browser cookie load this same principal check.
            old = auth.Principal(row.login, row.name, Role.ADMIN, row.id, before)
            with pytest.raises(HTTPException) as error:
                await auth._live(old, repo)
            assert error.value.status_code == 401
            current = await auth._live(auth.Principal(row.login, row.name, Role.MANAGER, row.id, row.auth_version), repo)
            assert not current.is_admin
    finally:
        await engine.dispose()


def test_future_settings_are_not_automatically_granted_to_administrators():
    from shop.access import editable_settings
    assert editable_settings(Role.ADMIN, {'future_security_setting'}) == frozenset()
    assert editable_settings(Role.SYSADMIN, {'future_security_setting'}) == {'future_security_setting'}


@pytest.mark.asyncio
async def test_sysadmin_can_edit_existing_highest_group_without_reassigning_it(client):
    client.repo.operators[3].role = Role.SYSADMIN
    assert (await client.http.put('/api/operators/3', json={'name': 'Existing system account'}, headers=headers(Role.ADMIN))).status_code == 403
    result = await client.http.put('/api/operators/3', json={'name': 'Existing system account'}, headers=headers(Role.SYSADMIN))
    assert result.status_code == 200
    assert result.json()['role'] == Role.SYSADMIN.value

@pytest.mark.asyncio
async def test_store_audit_requires_administrative_role(client):
    for method, path in [("GET", ""), ("POST", ""), ("PUT", "/cart"),
                         ("POST", "/cart/test"), ("GET", "/cart/history")]:
        url = "/api/store-audit" + path + "?environment=local"
        assert (await client.http.request(method, url, json={})).status_code == 401
        result = await client.http.request(method, url, json={}, headers=headers(Role.MANAGER))
        assert result.status_code == 403
    for role in (Role.ADMIN, Role.SYSADMIN):
        # A missing form field is validated after the administrative guard succeeds.
        response = await client.http.post("/api/store-audit?environment=local", json={}, headers=headers(role))
        assert response.status_code == 422
