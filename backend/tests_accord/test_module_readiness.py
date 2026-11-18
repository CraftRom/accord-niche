"""Stage 3/4: worker heartbeats, module states, release readiness, token cleanup (A04/A11/A13)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.auth import create_token
from api.routers import system
from shop import models as m
from shop import worker_health
from shop.config import settings
from shop.entities import OperatorRole as Role
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services import module_status, shop_settings


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'readiness.db'))
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    shop_settings.invalidate_cache()
    async with factory() as session:
        yield session, factory
    shop_settings.invalidate_cache()
    await engine.dispose()


# ---------------------------------------------------------------- heartbeats

def test_heartbeat_reports_fresh_stale_missing_and_refuses_links(tmp_path):
    now = time.time()
    worker_health.beat('scheduler', directory=tmp_path, now=now)
    assert worker_health.state('scheduler', directory=tmp_path, now=now + 5)['running'] is True
    assert worker_health.state('scheduler', directory=tmp_path, now=now + 3600)['running'] is False
    assert worker_health.state('bot', directory=tmp_path, now=now)['running'] is False
    data = json.loads((tmp_path / 'scheduler.json').read_text())
    assert set(data) == {'service', 'build', 'pid', 'at'}  # nothing sensitive
    (tmp_path / 'bot.json').symlink_to(tmp_path / 'scheduler.json')
    assert worker_health.state('bot', directory=tmp_path, now=now)['running'] is False
    with pytest.raises(ValueError):
        worker_health.beat('../escape', directory=tmp_path)


@pytest.mark.asyncio
async def test_pulse_writes_until_stopped(tmp_path):
    import asyncio
    stop = asyncio.Event()
    task = asyncio.create_task(worker_health.pulse('maintenance', stop, directory=tmp_path))
    for _ in range(50):
        if (tmp_path / 'maintenance.json').exists():
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, 2)
    assert worker_health.state('maintenance', directory=tmp_path)['running']


# ------------------------------------------------------------- module states

@pytest.mark.asyncio
async def test_enabled_module_without_worker_is_not_reported_ready(db, tmp_path, monkeypatch):
    session, _ = db
    repo = SqlRepository(session)
    monkeypatch.setattr(settings, 'bot_token', '')
    report = await module_status.module_report(repo, heartbeat_directory=tmp_path)
    states = {item['key']: item['status'] for item in report['modules']}
    assert states['scheduled_broadcasts'] == 'no_worker'
    assert states['backup_jobs'] == 'no_worker'
    assert states['telegram_bot'] == 'not_configured'
    assert 'promo_domains' not in states, 'promo pages were removed from ACCORD'
    assert states['salesdrive'] in {'disabled', 'not_configured'}
    for service in ('scheduler', 'maintenance'):
        worker_health.beat(service, directory=tmp_path)
    monkeypatch.setattr(settings, 'bot_token', '777001:TESTTOKEN')
    report = await module_status.module_report(repo, heartbeat_directory=tmp_path)
    states = {item['key']: item['status'] for item in report['modules']}
    assert states['scheduled_broadcasts'] == 'ready' and states['backup_jobs'] == 'ready'
    assert states['telegram_bot'] == 'no_worker'  # token alone does not mean the bot runs
    assert all(item['status'] in module_status.STATES for item in report['modules'])


@pytest.mark.asyncio
async def test_disabled_backups_are_disabled_not_missing(db, tmp_path):
    session, _ = db
    repo = SqlRepository(session)
    await repo.save_settings_map({'backup_enabled': 'false'})
    shop_settings.invalidate_cache()
    report = await module_status.module_report(repo, heartbeat_directory=tmp_path)
    assert {i['key']: i['status'] for i in report['modules']}['auto_backups'] == 'disabled'


# ------------------------------------------------------- readiness endpoints

@pytest.mark.asyncio
async def test_readiness_is_sysadmin_only_and_compares_migrations(db, monkeypatch, tmp_path):
    session, _ = db
    repo = SqlRepository(session)
    monkeypatch.setattr(settings, 'jwt_secret', 'readiness-signing-secret-' * 3)
    monkeypatch.setattr(settings, 'dashboard_login', 'root')
    session.add(m.Operator(id=1, login='manager', name='M', role=Role.MANAGER.value, password_hash='x', auth_version=0, is_active=True))
    session.add(m.Operator(id=2, login='shopadmin', name='A', role=Role.ADMIN.value, password_hash='x', auth_version=0, is_active=True))
    await session.commit()
    monkeypatch.setattr(worker_health, 'heartbeat_dir', lambda: tmp_path)
    heads = system.code_heads()
    assert len(heads) == 1

    async def database():
        return {'ok': True, 'revisions': ['older'], 'latency_ms': 1.0}

    async def redis():
        return {'configured': False, 'ok': None}

    monkeypatch.setattr(system, '_database', database)
    monkeypatch.setattr(system, '_redis', redis)
    app = FastAPI()
    app.include_router(system.router, prefix='/api/system')
    app.dependency_overrides[get_repo] = lambda: repo
    token = lambda login, role, oid: {'Authorization': 'Bearer ' + create_token(login, role, oid)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://dashboard.test') as http:
        assert (await http.get('/api/system/modules', headers=token('manager', Role.MANAGER, 1))).status_code == 403
        assert (await http.get('/api/system/modules', headers=token('shopadmin', Role.ADMIN, 2))).status_code == 200
        assert (await http.get('/api/system/readiness', headers=token('shopadmin', Role.ADMIN, 2))).status_code == 403
        response = await http.get('/api/system/readiness', headers=token('root', Role.SYSADMIN, 0))
    assert response.status_code == 200
    data = response.json()
    assert data['ready'] is False and data['migrations']['current'] is False
    assert data['migrations']['code_heads'] == heads
    assert any('Ревізія БД' in problem for problem in data['problems'])
    assert any('Планувальник' in problem for problem in data['problems'])
    assert 'password' not in json.dumps(data).lower()


def test_code_heads_follow_the_shipped_revision_files(tmp_path):
    (tmp_path / 'a.py').write_text("revision = 'a'\ndown_revision = None\n")
    (tmp_path / 'b.py').write_text("revision = 'b'\ndown_revision = 'a'\n")
    assert system.code_heads(tmp_path) == ['b']


# ------------------------------------------------------- A11 token cleanup

@pytest.mark.asyncio
async def test_only_expired_tokens_are_pruned_in_batches(db):
    session, _ = db
    repo = SqlRepository(session)
    now = datetime.now(timezone.utc)
    session.add(m.User(id=1, tg_id=-1, referral_code='R1'))
    session.add(m.WebsiteAccount(id=1, user_id=1, google_sub='sub'))
    for i in range(5):
        session.add(m.WebsiteSession(account_id=1, token_hash=f'old{i}', expires_at=now - timedelta(days=1)))
    session.add(m.WebsiteSession(account_id=1, token_hash='live', expires_at=now + timedelta(days=1)))
    session.add(m.WebsiteTelegramLink(tg_user_id=1, code_hash='oldcode', expires_at=now - timedelta(minutes=1)))
    session.add(m.WebsiteTelegramLink(tg_user_id=1, code_hash='livecode', expires_at=now + timedelta(minutes=5)))
    for digest, delta in (('dash-old', -1), ('dash-live', 1)):
        session.add(m.DashboardSession(id=digest, operator_id=0, login='root', csrf_token='c', auth_version=0,
                                       created_at=now, last_seen_at=now, expires_at=now + timedelta(hours=delta)))
    await session.commit()
    removed = await repo.prune_expired_tokens(now, batch=2)
    assert removed == {'website_sessions': 5, 'website_telegram_links': 1, 'dashboard_sessions': 1}
    from sqlalchemy import func, select
    assert await session.scalar(select(func.count()).select_from(m.WebsiteSession)) == 1
    assert await session.scalar(select(func.count()).select_from(m.WebsiteAccount)) == 1
    assert await session.scalar(select(func.count()).select_from(m.User)) == 1
    assert await repo.get_dashboard_session('dash-live')
    assert (await repo.prune_expired_tokens(now)) == {'website_sessions': 0, 'website_telegram_links': 0, 'dashboard_sessions': 0}


# ------------------------------------------------------- A13 release id

def test_release_id_follows_code_content_not_only_the_manual_label(tmp_path):
    from shop import build
    for name in ('shop', 'alembic/versions'):
        (tmp_path / name).mkdir(parents=True)
    (tmp_path / 'shop/a.py').write_text('x = 1\n')
    (tmp_path / 'alembic/versions/r.py').write_text("revision = 'r'\n")
    (tmp_path / 'shop/__pycache__').mkdir()
    (tmp_path / 'shop/__pycache__/a.pyc').write_bytes(b'cache')
    first = build.source_digest(tmp_path)
    (tmp_path / 'shop/__pycache__/a.pyc').write_bytes(b'other cache')
    (tmp_path / 'shop/notes.txt').write_text('not code')
    assert build.source_digest(tmp_path) == first, 'caches and non-code files do not change the release'
    (tmp_path / 'shop/a.py').write_text('x = 2\n')
    assert build.source_digest(tmp_path) != first, 'a code change always changes the release'
    rid = build.release_id()
    assert rid.startswith(build.BUILD + '+') and len(rid.split('+')[1]) == 12


def test_release_file_from_the_image_is_used_only_for_the_same_label(tmp_path, monkeypatch):
    from shop import build
    target = tmp_path / 'release.json'
    monkeypatch.setattr(build, 'RELEASE_FILE', target)
    build.release.cache_clear()
    try:
        target.write_text(json.dumps({'label': build.BUILD, 'digest': 'a' * 64, 'built_at': '2026-11-18T00:00:00+00:00'}))
        assert build.release()['id'] == build.BUILD + '+aaaaaaaaaaaa'
        assert build.release()['built_at'].startswith('2026-11-18')
        build.release.cache_clear()
        target.write_text(json.dumps({'label': 'older-label', 'digest': 'b' * 64}))
        assert 'bbbb' not in build.release()['id'], 'a stale file from another label is ignored'
    finally:
        build.release.cache_clear()


@pytest.mark.asyncio
async def test_readiness_flags_a_worker_still_running_an_older_release(db, monkeypatch, tmp_path):
    session, _ = db
    repo = SqlRepository(session)
    monkeypatch.setattr(settings, 'jwt_secret', 'readiness-signing-secret-' * 3)
    monkeypatch.setattr(settings, 'dashboard_login', 'root')
    monkeypatch.setattr(worker_health, 'heartbeat_dir', lambda: tmp_path)
    worker_health.beat('maintenance', directory=tmp_path)
    data = json.loads((tmp_path / 'maintenance.json').read_text())
    data['build'] = 'previous-release+000000000000'
    (tmp_path / 'maintenance.json').write_text(json.dumps(data))
    worker_health.beat('scheduler', directory=tmp_path)

    async def database():
        return {'ok': True, 'revisions': system.code_heads(), 'latency_ms': 1.0}

    async def redis():
        return {'configured': False, 'ok': None}
    monkeypatch.setattr(system, '_database', database)
    monkeypatch.setattr(system, '_redis', redis)
    app = FastAPI()
    app.include_router(system.router, prefix='/api/system')
    app.dependency_overrides[get_repo] = lambda: repo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://dashboard.test') as http:
        data = (await http.get('/api/system/readiness', headers={'Authorization': 'Bearer ' + create_token('root', Role.SYSADMIN, 0)})).json()
    from shop.build import release_id
    assert data['release']['id'] == release_id() == data['build']
    stale = [p for p in data['problems'] if 'іншій збірці' in p]
    assert len(stale) == 1 and 'previous-release' in stale[0] and 'резервних копій' in stale[0]
