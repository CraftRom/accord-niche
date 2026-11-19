"""Site integrations moved from .env into the panel: Google sign-in, Twilio
Verify, social and legal links, Search Console, Mini App link, idle timeout.

Contract: panel value wins, an empty panel value means «use .env», secrets
are encrypted at rest and never returned, formats and hosts are validated,
and only the system administrator changes keys and identities.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import settings as settings_api
from api.schemas import ShopSettingsIn
from shop import models as m
from shop.access import ADMIN_FIELDS, INFRA_FIELDS, editable_settings
from shop.config import settings
from shop.entities import OperatorRole as Role
from shop.repo.sql import SqlRepository
from shop.services import seo
from shop.services.shop_settings import (ENV_FALLBACK, SECRET_FIELDS, ShopSettings,
                                         get_shop_settings, invalidate_cache, save_shop_settings)

SID = 'AC' + 'a1' * 16
SERVICE = 'VA' + 'b2' * 16
TOKEN = 'c3' * 16
CLIENT = '123456789012-abcdefgh12345678.apps.googleusercontent.com'


@pytest_asyncio.fixture
async def repo(monkeypatch):
    monkeypatch.setattr(settings, 'data_encryption_key', Fernet.generate_key().decode())
    for name in ENV_FALLBACK.values():
        monkeypatch.delenv(name, raising=False)
    invalidate_cache()
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield SqlRepository(session)
    invalidate_cache()
    await engine.dispose()


@pytest.mark.asyncio
async def test_twilio_token_is_encrypted_at_rest_and_never_returned(repo):
    saved = await save_shop_settings(repo, {'twilio_account_sid': SID, 'twilio_auth_token': TOKEN,
                                            'twilio_verify_service_sid': SERVICE})
    assert 'twilio_auth_token' in SECRET_FIELDS and saved.twilio_ready
    stored = (await repo.s.execute(select(m.Setting.value).where(m.Setting.key == 'twilio_auth_token'))).scalar_one()
    assert stored.startswith('enc:v1:') and TOKEN not in stored
    out = settings_api._out(saved).model_dump()
    assert 'twilio_auth_token' not in out and TOKEN not in str(out)
    assert out['twilio_auth_connected'] is True and out['twilio_account_sid'] == SID
    invalidate_cache()
    assert (await get_shop_settings(repo)).site('twilio_auth_token') == TOKEN


@pytest.mark.asyncio
async def test_empty_panel_value_falls_back_to_env_and_panel_overrides_it(repo, monkeypatch):
    monkeypatch.setenv('ACCORD_GOOGLE_CLIENT_ID', 'env-' + CLIENT)
    monkeypatch.setenv('ACCORD_TWILIO_AUTH_TOKEN', 'from-env')
    shop = await get_shop_settings(repo)
    assert shop.site('google_client_id') == 'env-' + CLIENT
    assert shop.env_defaults == ['google_client_id', 'twilio_auth_token']
    out = settings_api._out(shop).model_dump()
    assert out['google_client_id'] == '' and out['twilio_auth_connected'] is True
    assert 'from-env' not in str(out), '.env values are reported as «set», never sent to the panel'
    shop = await save_shop_settings(repo, {'google_client_id': CLIENT})
    assert shop.site('google_client_id') == CLIENT and shop.site_source('google_client_id') == 'panel'
    assert 'google_client_id' not in shop.env_defaults


@pytest.mark.parametrize('field, value', [
    ('google_client_id', 'not-a-client-id'),
    ('google_client_id', CLIENT + '.evil.com'),
    ('twilio_account_sid', 'AC123'),
    ('twilio_verify_service_sid', 'AC' + 'b2' * 16),
    ('twilio_auth_token', 'x' * 32),
    ('google_site_verification', '"><script>'),
    ('instagram_url', 'https://evil.example/accord'),
    ('instagram_url', 'http://instagram.com/accord'),
    ('tiktok_url', 'https://user:pass@tiktok.com/@a'),
    ('miniapp_url', 'https://example.com/app'),
    ('dashboard_idle_minutes', 2),
])
def test_formats_and_hosts_are_validated(field, value):
    with pytest.raises(ValidationError):
        ShopSettingsIn(**{field: value})


def test_valid_values_and_pasted_spaces_are_accepted():
    data = ShopSettingsIn(google_client_id=f'  {CLIENT} ', twilio_account_sid=SID, twilio_auth_token=TOKEN,
                          twilio_verify_service_sid=SERVICE, instagram_url='https://www.instagram.com/accord',
                          tiktok_url='https://www.tiktok.com/@accord', miniapp_url='https://t.me/bot/app',
                          twilio_auth_connected=True,
                          env_defaults=['google_client_id'])
    assert data.google_client_id == CLIENT
    assert ShopSettingsIn(twilio_auth_token='').twilio_auth_token == '', 'empty clears the panel value'


def test_only_system_administrator_changes_keys_and_identities():
    keys = {'google_client_id', 'google_site_verification', 'twilio_account_sid', 'twilio_auth_token',
            'twilio_verify_service_sid', 'miniapp_url', 'dashboard_idle_minutes'}
    admin = editable_settings(Role.ADMIN, ShopSettingsIn.model_fields)
    assert keys <= INFRA_FIELDS and not keys & admin
    assert keys <= editable_settings(Role.SYSADMIN, ShopSettingsIn.model_fields)
    assert {'instagram_url', 'tiktok_url'} <= ADMIN_FIELDS
    assert not editable_settings(Role.MANAGER, ShopSettingsIn.model_fields)


@pytest.mark.asyncio
async def test_search_console_tag_only_on_home_and_only_valid_tokens(repo, monkeypatch):
    await save_shop_settings(repo, {'google_site_verification': 'abcDEF_123-xyz7890abcd'})
    home = await seo.head_for(repo, '/')
    assert '<meta name="google-site-verification" content="abcDEF_123-xyz7890abcd" />' in home
    assert 'google-site-verification' not in await seo.head_for(repo, '/catalog')
    await save_shop_settings(repo, {'google_site_verification': ''})
    monkeypatch.setenv('ACCORD_GOOGLE_SITE_VERIFICATION', '"><script>alert(1)</script>')
    assert 'google-site-verification' not in await seo.head_for(repo, '/'), 'unvalidated .env value is dropped'


@pytest.mark.asyncio
async def test_website_session_uses_panel_google_client_and_twilio(repo):
    from api.routers import website_shop as web
    from shop.repo.factory import get_repo
    await save_shop_settings(repo, {'google_client_id': CLIENT})
    app = FastAPI()
    app.include_router(web.router, prefix='/api/web')
    app.dependency_overrides[get_repo] = lambda: repo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as http:
        data = (await http.get('/api/web/session')).json()
    assert data['google_client_id'] == CLIENT and data['phone_verification_enabled'] is False
    await save_shop_settings(repo, {'twilio_account_sid': SID, 'twilio_auth_token': TOKEN,
                                    'twilio_verify_service_sid': SERVICE})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as http:
        assert (await http.get('/api/web/session')).json()['phone_verification_enabled'] is True


@pytest.mark.asyncio
async def test_module_status_reads_twilio_from_panel(repo):
    from shop.services.module_status import module_report
    sms = lambda report: next(item for item in report['modules'] if item['key'] == 'sms_verification')
    assert sms(await module_report(repo))['status'] == 'not_configured'
    await save_shop_settings(repo, {'twilio_account_sid': SID, 'twilio_auth_token': TOKEN,
                                    'twilio_verify_service_sid': SERVICE})
    assert sms(await module_report(repo))['status'] == 'ready'


def test_env_fallback_covers_every_site_field():
    names = {f for f in ShopSettings.__dataclass_fields__ if f in ENV_FALLBACK}
    assert names == set(ENV_FALLBACK)
