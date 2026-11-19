"""Free phone verification without Twilio.

* SMS: the shop generates the code, stores only its HMAC bound to the account
  and the number, limits attempts and expiry; the SMS Gateway for Android only
  delivers the text.
* Telegram: the bot confirms the number from the user's own contact through
  a single-use, expiring link opened from the website profile.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import website_shop as web
from bot.handlers import start as bot_start
from bot.states import PhoneConfirm
from shop import models as m
from shop.config import settings
from shop.repo.sql import SqlRepository
from shop.services import phone_verification as pv
from shop.services.shop_settings import ENV_FALLBACK, invalidate_cache

PHONE = '+380671234567'
GATEWAY = {'ACCORD_SMS_GATEWAY_URL': 'https://gateway.example/3rdparty/v1/messages',
           'ACCORD_SMS_GATEWAY_LOGIN': 'shop', 'ACCORD_SMS_GATEWAY_TOKEN': 'qa-gateway-value'}


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    for name in ENV_FALLBACK.values():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, 'bot_token', '1:test')
    monkeypatch.setattr(settings, 'bot_username', 'accord_shop_bot')
    invalidate_cache()
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'phone.db'))
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([m.User(id=1, tg_id=-1, referral_code='WEB'), m.User(id=2, tg_id=555, referral_code='TG'),
                         m.User(id=3, tg_id=777, referral_code='TG3')])
        session.add(m.WebsiteAccount(id=1, user_id=1, google_sub='g-1'))
        await session.commit()
        monkeypatch.setattr(web, '_require_csrf', lambda r: None)

        async def account(_request, repo):
            return await repo.s.get(m.WebsiteAccount, 1)
        monkeypatch.setattr(web, '_required_account', account)
        yield session, factory
    invalidate_cache()
    await engine.dispose()


def request():
    return Request({'type': 'http', 'method': 'POST', 'scheme': 'https', 'path': '/',
                    'headers': [], 'server': ('accordniche.pp.ua', 443), 'query_string': b''})


def gateway_env(monkeypatch):
    for name, value in GATEWAY.items():
        monkeypatch.setenv(name, value)
    invalidate_cache()


# ------------------------------------------------------------------ SMS codes

@pytest.mark.asyncio
async def test_sms_code_is_generated_by_the_shop_and_only_its_hmac_is_stored(db, monkeypatch):
    session, factory = db
    gateway_env(monkeypatch)
    texts = []

    async def deliver(shop, phone, text):
        texts.append((phone, text))
    monkeypatch.setattr(pv, 'send_sms', deliver)
    async with factory() as s:
        assert await web.phone_send(web.PhoneIn(phone='067 123 45 67'), request(), SqlRepository(s)) == {'sent': True}
    (phone, text), = texts
    code = text.split('код підтвердження ')[1][:6]
    assert phone == PHONE and code.isdigit() and len(code) == 6
    async with factory() as s:
        row = await s.get(m.WebsiteAccount, 1)
        assert row.phone_code_phone == PHONE and code not in (row.phone_code_hash or '') and len(row.phone_code_hash) == 64
        assert row.phone_window_count == 1
    async with factory() as s:
        result = await web.phone_check(web.PhoneCheckIn(phone=PHONE, code=code), request(), SqlRepository(s))
    assert result['phone_verified'] is True
    async with factory() as s:
        row = await s.get(m.WebsiteAccount, 1)
        assert row.verified_phone == PHONE and row.phone_code_hash is None, 'the code is single use'
        with pytest.raises(HTTPException) as again:
            await web.phone_check(web.PhoneCheckIn(phone=PHONE, code=code), request(), SqlRepository(s))
        assert again.value.status_code == 422


@pytest.mark.asyncio
async def test_wrong_codes_are_counted_and_the_sixth_attempt_is_refused(db):
    session, factory = db
    account = await session.get(m.WebsiteAccount, 1)
    code = pv.issue_code(account, PHONE)
    await session.commit()
    wrong = '000000' if code != '000000' else '111111'
    for _ in range(pv.CODE_ATTEMPTS):
        async with factory() as s:
            with pytest.raises(HTTPException) as error:
                await web.phone_check(web.PhoneCheckIn(phone=PHONE, code=wrong), request(), SqlRepository(s))
            assert error.value.status_code == 422
    async with factory() as s:
        with pytest.raises(HTTPException) as error:
            await web.phone_check(web.PhoneCheckIn(phone=PHONE, code=code), request(), SqlRepository(s))
        assert error.value.status_code == 429, 'even the right code is refused after five wrong ones'
        assert (await s.get(m.WebsiteAccount, 1)).verified_phone is None


@pytest.mark.asyncio
async def test_code_is_bound_to_the_number_and_expires(db):
    session, factory = db
    account = await session.get(m.WebsiteAccount, 1)
    code = pv.issue_code(account, PHONE)
    assert pv.check_code(account, '+380991112233', code) == 'expired', 'a code for another number is useless'
    account.phone_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert pv.check_code(account, PHONE, code) == 'expired'
    code = pv.issue_code(account, PHONE)
    assert pv.check_code(account, PHONE, code) == 'ok' and account.phone_code_hash is None


@pytest.mark.asyncio
async def test_sms_send_is_refused_without_a_gateway(db):
    _, factory = db
    async with factory() as s:
        with pytest.raises(HTTPException) as error:
            await web.phone_send(web.PhoneIn(phone=PHONE), request(), SqlRepository(s))
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_gateway_failure_points_to_telegram(db, monkeypatch):
    _, factory = db
    gateway_env(monkeypatch)

    async def down(*args):
        raise pv.GatewayError('unreachable')
    monkeypatch.setattr(pv, 'send_sms', down)
    async with factory() as s:
        with pytest.raises(HTTPException) as error:
            await web.phone_send(web.PhoneIn(phone=PHONE), request(), SqlRepository(s))
    assert error.value.status_code == 502 and 'Telegram' in error.value.detail


# --------------------------------------------------------------- the gateway

_REAL_CLIENT = httpx.AsyncClient


class _Client:
    """httpx.AsyncClient with a mock transport, keeping the caller's options."""
    calls = []

    def __init__(self, status):
        self.status = status

    def __call__(self, **kwargs):
        assert kwargs.get('follow_redirects') is False
        def handler(req):
            _Client.calls.append(req)
            return httpx.Response(self.status, json={'id': 'msg'})
        return _REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.asyncio
async def test_gateway_request_follows_sms_gateway_for_android_api(monkeypatch):
    gateway_env(monkeypatch)
    from shop.services.shop_settings import ShopSettings
    shop = ShopSettings.from_env()
    _Client.calls = []
    monkeypatch.setattr(pv.httpx, 'AsyncClient', _Client(202))
    await pv.send_sms(shop, PHONE, 'ACCORD: код 123456')
    call, = _Client.calls
    assert str(call.url) == GATEWAY['ACCORD_SMS_GATEWAY_URL'] and call.method == 'POST'
    assert json.loads(call.content) == {'textMessage': {'text': 'ACCORD: код 123456'}, 'phoneNumbers': [PHONE]}
    assert call.headers['authorization'].startswith('Basic ')
    monkeypatch.setattr(pv.httpx, 'AsyncClient', _Client(401))
    with pytest.raises(pv.GatewayError) as error:
        await pv.send_sms(shop, PHONE, 'x')
    assert pv.gateway_problem(error.value) == 'SMS-шлюз відхилив логін або пароль'
    monkeypatch.setenv('ACCORD_SMS_GATEWAY_URL', 'http://gateway.example/messages')
    with pytest.raises(pv.GatewayError):
        await pv.send_sms(ShopSettings.from_env(), PHONE, 'x')


# ------------------------------------------------------------------ Telegram

async def _telegram_link(factory):
    async with factory() as s:
        result = await web.phone_via_telegram(request(), SqlRepository(s))
    assert result['url'].startswith('https://t.me/accord_shop_bot?start=vp_')
    return pv.token_from_start(result['url'].split('start=')[1])


@pytest.mark.asyncio
async def test_telegram_confirms_the_phone_and_links_the_profile_once(db):
    _, factory = db
    token = await _telegram_link(factory)
    assert token and len(token) == 32
    async with factory() as s:
        assert (await s.scalar(select(m.WebsitePhoneConfirmation.token_hash))) != token, 'only a hash is stored'
        assert await pv.confirm_with_telegram(s, token, 2, PHONE) == 'ok_linked'
    async with factory() as s:
        row = await s.get(m.WebsiteAccount, 1)
        assert row.verified_phone == PHONE and row.linked_telegram_user_id == 2
        assert await pv.confirm_with_telegram(s, token, 2, PHONE) == 'expired', 'single use'


@pytest.mark.asyncio
async def test_telegram_link_expires_and_a_new_one_replaces_the_old(db):
    session, factory = db
    first = await _telegram_link(factory)
    async with factory() as s:
        with pytest.raises(HTTPException) as burst:
            await web.phone_via_telegram(request(), SqlRepository(s))
        assert burst.value.status_code == 429, 'links are not issued in a burst'
        row = await s.scalar(select(m.WebsitePhoneConfirmation))
        row.expires_at -= timedelta(seconds=6)
        await s.commit()
    second = await _telegram_link(factory)
    async with factory() as s:
        assert await pv.confirm_with_telegram(s, first, 2, PHONE) == 'expired'
        row = await s.scalar(select(m.WebsitePhoneConfirmation))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.commit()
        assert await pv.confirm_with_telegram(s, second, 2, PHONE) == 'expired'
        assert (await s.get(m.WebsiteAccount, 1)).verified_phone is None


@pytest.mark.asyncio
async def test_telegram_cannot_confirm_for_a_profile_linked_to_another_account(db):
    session, factory = db
    account = await session.get(m.WebsiteAccount, 1)
    account.linked_telegram_user_id = 3
    await session.commit()
    token = await _telegram_link(factory)
    async with factory() as s:
        assert await pv.confirm_with_telegram(s, token, 2, PHONE) == 'other_telegram'
        assert (await s.get(m.WebsiteAccount, 1)).verified_phone is None


@pytest.mark.asyncio
async def test_telegram_already_linked_elsewhere_confirms_phone_without_moving_the_link(db):
    session, factory = db
    session.add_all([m.User(id=4, tg_id=-4, referral_code='WEB4'),
                     m.WebsiteAccount(id=2, user_id=4, google_sub='g-2', linked_telegram_user_id=2)])
    await session.commit()
    token = await _telegram_link(factory)
    async with factory() as s:
        assert await pv.confirm_with_telegram(s, token, 2, PHONE) == 'ok'
        row = await s.get(m.WebsiteAccount, 1)
        assert row.verified_phone == PHONE and row.linked_telegram_user_id is None


@pytest.mark.asyncio
async def test_telegram_button_needs_a_configured_bot(db, monkeypatch):
    _, factory = db
    monkeypatch.setattr(settings, 'bot_username', 'your_shop_bot')
    async with factory() as s:
        with pytest.raises(HTTPException) as error:
            await web.phone_via_telegram(request(), SqlRepository(s))
    assert error.value.status_code == 503


def test_start_payload_is_strictly_parsed():
    assert pv.token_from_start('vp_' + 'a' * 32) == 'a' * 32
    for bad in (None, '', 'REF123', 'vp_short', 'vp_' + 'a' * 31 + '!', 'vp_' + 'a' * 60):
        assert pv.token_from_start(bad) is None


# ---------------------------------------------------------------- bot handlers

def _message(user_id, contact=None, text=None):
    return SimpleNamespace(answer=AsyncMock(), from_user=SimpleNamespace(id=user_id), contact=contact, text=text)


@pytest.mark.asyncio
async def test_bot_flow_asks_for_own_contact_and_rejects_a_foreign_one(db):
    _, factory = db
    token = await _telegram_link(factory)
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=555, user_id=555))
    async with factory() as s:
        repo = SqlRepository(s)
        start = _message(555)
        await bot_start._start_phone_confirmation(start, state, repo, token)
        assert await state.get_state() == PhoneConfirm.waiting.state
        assert 'Надіслати номер' in start.answer.call_args.args[0]
        user = SimpleNamespace(id=2)
        foreign = _message(555, SimpleNamespace(user_id=999, phone_number=PHONE))
        await bot_start.phone_confirmation_contact(foreign, state, repo, user)
        assert 'свій номер' in foreign.answer.call_args.args[0]
        assert (await s.get(m.WebsiteAccount, 1)).verified_phone is None
        own = _message(555, SimpleNamespace(user_id=555, phone_number='380671234567'))
        await bot_start.phone_confirmation_contact(own, state, repo, user)
        assert '✅' in own.answer.call_args.args[0] and await state.get_state() is None
    async with factory() as s:
        assert (await s.get(m.WebsiteAccount, 1)).verified_phone == PHONE


@pytest.mark.asyncio
async def test_bot_rejects_foreign_numbers_and_stale_links(db):
    _, factory = db
    token = await _telegram_link(factory)
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=555, user_id=555))
    async with factory() as s:
        repo = SqlRepository(s)
        stale = _message(555)
        await bot_start._start_phone_confirmation(stale, state, repo, 'b' * 32)
        assert 'застаріло' in stale.answer.call_args.args[0] and await state.get_state() is None
        await bot_start._start_phone_confirmation(_message(555), state, repo, token)
        polish = _message(555, SimpleNamespace(user_id=555, phone_number='+48501234567'))
        await bot_start.phone_confirmation_contact(polish, state, repo, SimpleNamespace(id=2))
        assert '+380' in polish.answer.call_args.args[0]
        assert (await s.get(m.WebsiteAccount, 1)).verified_phone is None
