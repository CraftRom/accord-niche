"""A07: first-party main-website visits form the conversion denominator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routers import website_shop as web
from shop import models as m
from shop.repo.sql import SqlRepository
from shop.services import analytics

ORIGIN = 'https://accordniche.pp.ua'


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'funnel.db'))
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def request(origin=ORIGIN, agent='Mozilla/5.0 (iPhone)'):
    headers = [(b'host', b'accordniche.pp.ua'), (b'user-agent', agent.encode())]
    if origin:
        headers.append((b'origin', origin.encode()))
    return Request({'type': 'http', 'method': 'POST', 'scheme': 'https', 'path': '/api/web/analytics/visit',
                    'headers': headers, 'server': ('accordniche.pp.ua', 443), 'query_string': b''})


async def visit(session, sid, **kw):
    body = web.WebsiteVisitIn(session_id=sid, attribution={'source': 'instagram', 'campaign': 'autumn'})
    return await web.website_visit(body, request(**kw), SqlRepository(session))


def order(oid, user, sid, created, channel='accord_website'):
    return m.Order(id=oid, user_id=user, status=m.OrderStatus.NEW, business_state='open', created_at=created,
                   total=Decimal(100), payment_method='cod',
                   attribution={'source': 'instagram', 'channel': channel, 'session_id': sid})


def report_window(now):
    tz = ZoneInfo('Europe/Kyiv')
    return {'since': now - timedelta(days=1), 'until': now + timedelta(days=1), 'tz': tz}


@pytest.mark.asyncio
async def test_ten_visits_two_checkouts_is_twenty_percent_and_replays_do_not_count(db):
    ids = [f'visit{n:02d}-abcdefghijk' for n in range(10)]
    for sid in ids:
        assert (await visit(db, sid)).status_code == 204
    for sid in ids[:3]:  # network retries / reopened tab
        await visit(db, sid)
    assert await db.scalar(select(func.count()).select_from(m.AnalyticsSession)) == 10
    stored = (await db.scalars(select(m.AnalyticsSession))).all()
    assert all(row.user_id is None and row.channel == m.WEBSITE_CHANNEL for row in stored)
    assert stored[0].attribution['source'] == 'instagram'
    now = datetime.now(timezone.utc)
    db.add_all([m.User(id=1, tg_id=-1, referral_code='G1'), m.User(id=2, tg_id=-2, referral_code='G2')])
    # Guest checkout and the same visitor after Google sign-in: still one visit.
    db.add_all([order(1, 1, ids[0], now + timedelta(minutes=5)), order(2, 2, ids[0], now + timedelta(minutes=9)),
                order(3, 2, ids[1], now + timedelta(minutes=6))])
    # A Mini App order reusing a website id must not convert the website visit.
    db.add(order(4, 1, ids[2], now + timedelta(minutes=7), channel='telegram_miniapp'))
    await db.commit()
    data = await analytics.aggregate(db, report_window(now))
    website = next(c for c in data['channels'] if c['channel'] == m.WEBSITE_CHANNEL)
    assert website == {'channel': m.WEBSITE_CHANNEL, 'sessions': 10, 'converted_sessions': 2, 'conversion': 20.0}
    miniapp = next(c for c in data['channels'] if c['channel'] == m.MINIAPP_CHANNEL)
    assert miniapp['sessions'] == 0 and miniapp['conversion'] is None  # no data, not 0%
    assert data['website_visits_since']


@pytest.mark.asyncio
async def test_foreign_origin_is_refused_and_bots_are_not_counted(db):
    with pytest.raises(HTTPException) as error:
        await visit(db, 'foreign-origin-visit-01', origin='https://evil.example')
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        await visit(db, 'no-origin-visit-000001', origin='')
    assert (await visit(db, 'crawler-visit-0000001', agent='Googlebot/2.1')).status_code == 204
    assert await db.scalar(select(func.count()).select_from(m.AnalyticsSession)) == 0


@pytest.mark.asyncio
async def test_checkout_links_only_a_recorded_visit(db):
    await visit(db, 'recorded-visit-000001')
    assert await analytics.website_checkout_session(db, 'recorded-visit-000001') == 'recorded-visit-000001'
    assert await analytics.website_checkout_session(db, 'never-recorded-00001') is None
    assert await analytics.website_checkout_session(db, None) is None


@pytest.mark.asyncio
async def test_website_visits_have_a_bounded_retention(db):
    old = datetime.now(timezone.utc) - timedelta(days=analytics.WEBSITE_VISIT_RETENTION_DAYS + 1)
    db.add(m.User(id=1, tg_id=5, referral_code='T1'))
    db.add(m.AnalyticsSession(user_id=None, channel=m.WEBSITE_CHANNEL, session_id='ancient-visit-000001',
                              started_at=old, attribution={'source': 'direct'}))
    db.add(m.AnalyticsSession(user_id=1, channel=m.MINIAPP_CHANNEL, session_id='miniapp-visit-000001',
                              started_at=old, attribution={'source': 'direct'}))
    await db.commit()
    await visit(db, 'fresh-visit-00000001')
    removed = await SqlRepository(db).prune_website_visits(
        datetime.now(timezone.utc) - timedelta(days=analytics.WEBSITE_VISIT_RETENTION_DAYS))
    assert removed == 1
    left = {row.session_id for row in (await db.scalars(select(m.AnalyticsSession))).all()}
    assert left == {'miniapp-visit-000001', 'fresh-visit-00000001'}


async def app_visit(session, sid):
    body = web.WebsiteVisitIn(session_id=sid, attribution={'source': 'accord_android', 'medium': 'app'})
    return await web.website_visit(body, request(agent='AccordNicheAndroid/1.3.0 (Android 15)'), SqlRepository(session))


@pytest.mark.asyncio
async def test_android_app_is_its_own_channel_and_never_mixes_with_the_website(db):
    for sid in ['app-launch-0001-abcdef', 'app-launch-0002-abcdef']:
        assert (await app_visit(db, sid)).status_code == 204
    await app_visit(db, 'app-launch-0001-abcdef')  # retried POST of the same launch
    await visit(db, 'site-visit-0001-abcdef')
    rows = (await db.scalars(select(m.AnalyticsSession).order_by(m.AnalyticsSession.id))).all()
    assert [r.channel for r in rows] == [m.APP_CHANNEL, m.APP_CHANNEL, m.WEBSITE_CHANNEL]
    # An app visit id is not a website visit and the other way round.
    assert await analytics.website_checkout_session(db, 'app-launch-0001-abcdef') is None
    assert await analytics.website_checkout_session(db, 'app-launch-0001-abcdef', m.APP_CHANNEL) == 'app-launch-0001-abcdef'
    now = datetime.now(timezone.utc)
    db.add(m.User(id=1, tg_id=-1, referral_code='G1'))
    db.add(order(1, 1, 'app-launch-0001-abcdef', now + timedelta(minutes=3), channel=m.APP_CHANNEL))
    # A website order carrying an app id converts neither.
    db.add(order(2, 1, 'app-launch-0002-abcdef', now + timedelta(minutes=4)))
    await db.commit()
    data = await analytics.aggregate(db, report_window(now))
    channels = {c['channel']: c for c in data['channels']}
    assert channels[m.APP_CHANNEL] == {'channel': m.APP_CHANNEL, 'sessions': 2, 'converted_sessions': 1, 'conversion': 50.0}
    assert channels[m.WEBSITE_CHANNEL]['sessions'] == 1 and channels[m.WEBSITE_CHANNEL]['converted_sessions'] == 0


def test_client_channel_from_attribution():
    assert web._client_channel({'source': 'accord_android'}) == m.APP_CHANNEL
    assert web._client_channel({'source': 'ACCORD_ANDROID '}) == m.APP_CHANNEL
    for other in [None, {}, {'source': 'instagram'}, {'source': 'accord_website'}]:
        assert web._client_channel(other) == m.WEBSITE_CHANNEL
