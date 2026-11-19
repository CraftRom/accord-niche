"""Публічна оферта й політика конфіденційності: сторінки, які редагуються
в панелі, з початковими шаблонами за законодавством України."""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api import auth
from api.routers import legal as legal_router
from shop import models as m
from shop.config import settings
from shop.entities import OperatorRole as Role
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services import legal, seo
from shop.services.shop_settings import invalidate_cache


@pytest_asyncio.fixture
async def env(monkeypatch):
    monkeypatch.setattr(settings, 'jwt_secret', 'unit-test-secret-' * 4)
    monkeypatch.setattr(settings, 'dashboard_login', 'root')
    invalidate_cache()
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add(m.Operator(id=2, login='manager', name='M', password_hash='x', role='operator', is_active=True))
        session.add(m.Operator(id=1, login='administrator', name='A', password_hash='x', role='shop_admin', is_active=True))
        await session.commit()
        repo = SqlRepository(session)
        app = FastAPI()
        app.include_router(legal_router.admin, prefix='/api/legal')
        app.include_router(legal_router.public, prefix='/api/public')
        app.include_router(legal_router.public, prefix='/api/shop')
        app.dependency_overrides[get_repo] = lambda: repo
        from shop.db import get_session
        app.dependency_overrides[get_session] = lambda: session
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
            yield http, repo
    invalidate_cache()
    await engine.dispose()


def headers(role):
    login, oid = {Role.SYSADMIN: ('root', 0), Role.ADMIN: ('administrator', 1), Role.MANAGER: ('manager', 2)}[role]
    return {'Authorization': 'Bearer ' + auth.create_token(login, role, oid)}


def test_default_terms_follow_ukrainian_law_for_perfume():
    text = legal.DEFAULTS['terms']
    for reference in ('статей 633 і 641 Цивільного кодексу', 'статті 642', '«Про електронну комерцію»',
                      '«Про захист прав споживачів»', 'від 19.03.1994 № 172', 'статтею 8'):
        assert reference in text, reference
    assert 'Розпив' in text and 'атомайзер' in text
    assert 'нікотин' not in text.lower() and 'повнолітн' not in text.lower()


def test_default_privacy_names_rights_bases_and_regulator():
    text = legal.DEFAULTS['privacy']
    for reference in ('статтею 11', 'статті 8', 'статті 29', 'Уповноваженого Верховної Ради України з прав людини',
                      'не отримуємо й не зберігаємо дані платіжних карток'):
        assert reference in text, reference


def test_fill_leaves_no_placeholders_or_dangling_labels():
    values = {'SELLER_NAME': 'ФОП Тест', 'SELLER_CODE': '', 'SELLER_ADDRESS': 'м. Київ', 'SELLER_EMAIL': '',
              'SELLER_PHONE': '+380501234567', 'SITE': 'https://accordniche.pp.ua', 'UPDATED': '19.11.2026'}
    for key in legal.KEYS:
        out = legal.fill(legal.DEFAULTS[key], values)
        assert '{{' not in out and 'РНОКПП/код ЄДРПОУ:' not in out and 'Email:' not in out
        assert 'ФОП Тест' in out
    assert 'Телефон: +380501234567' in legal.fill(legal.DEFAULTS['terms'], values)


@pytest.mark.asyncio
async def test_public_pages_render_requisites_on_site_and_mini_app(env):
    http, repo = env
    await repo.save_settings_map({'seller_name': 'ФОП Галицький', 'seller_address': 'м. Хмельницький',
                                  'seller_email': 'shop@example.test'})
    invalidate_cache()
    for prefix in ('/api/public', '/api/shop'):
        page = (await http.get(prefix + '/legal/terms')).json()
        assert page['title'] == 'Публічна оферта' and 'ФОП Галицький' in page['body'] and page['seller_ready'] is True
    privacy = await http.get('/api/public/legal/privacy')
    assert privacy.json()['title'] == 'Політика конфіденційності' and 'shop@example.test' in privacy.json()['body']
    assert (await http.get('/api/public/legal/secret')).status_code == 422


@pytest.mark.asyncio
async def test_admin_edits_and_resets_a_document(env):
    http, _ = env
    saved = await http.put('/api/legal/terms', json={'body': '## Умови\n\nПродавець — {{SELLER_NAME}}.'}, headers=headers(Role.ADMIN))
    assert saved.status_code == 200 and saved.json()['is_default'] is False and saved.json()['updated_by'] == 'administrator'
    assert (await http.get('/api/public/legal/terms')).json()['body'].startswith('## Умови')
    reset = await http.put('/api/legal/terms', json={'body': '  '}, headers=headers(Role.ADMIN))
    assert reset.json()['is_default'] is True and 'публічною офертою' in reset.json()['body']
    assert '641' in (await http.get('/api/public/legal/terms')).json()['body']
    preview = await http.post('/api/legal/privacy/preview', json={'body': 'Володілець: {{SELLER_NAME}}'}, headers=headers(Role.ADMIN))
    assert preview.status_code == 200 and '{{' not in preview.json()['body']


@pytest.mark.asyncio
async def test_only_administrators_change_documents_and_size_is_limited(env):
    http, _ = env
    assert (await http.put('/api/legal/terms', json={'body': 'x'}, headers=headers(Role.MANAGER))).status_code == 403
    assert (await http.put('/api/legal/terms', json={'body': 'x'})).status_code in (401, 403)
    assert (await http.get('/api/legal', headers=headers(Role.MANAGER))).status_code == 403
    too_long = await http.put('/api/legal/terms', json={'body': 'x' * (legal.MAX_BODY + 1)}, headers=headers(Role.ADMIN))
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_documents_are_indexed_public_pages(env):
    _, repo = env
    head = await seo.head_for(repo, '/terms')
    assert 'Публічна оферта' in head and 'noindex' not in head
    assert '/privacy</loc>' in await seo.sitemap(repo)
