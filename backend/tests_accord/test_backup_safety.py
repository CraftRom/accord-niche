"""Backup failures never publish a ready file or silently restore a live shop."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock
import stat

import pytest
from fastapi import HTTPException
from shop import backup_files as files
from api.routers import backups
from scheduler import tasks

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('accord_host_backup', ROOT / 'scripts/accord_backup.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
SETTINGS = SimpleNamespace(postgres_host='db', postgres_port=5432, postgres_user='accord',
                           postgres_db='accord', postgres_password='private-dummy')


def fake_dump(monkeypatch, *, failure=None, invalid=False):
    calls = []
    def run(command, **options):
        calls.append((command, options))
        if command[0] == 'pg_dump':
            Path(command[command.index('-f') + 1]).write_bytes(b'PGDMP' + b'x' * 1200)
            if failure == 'timeout':
                raise subprocess.TimeoutExpired(command, 1)
            return SimpleNamespace(returncode=1 if failure else 0)
        return SimpleNamespace(returncode=1 if invalid else 0)
    monkeypatch.setattr(files.subprocess, 'run', run)
    return calls


@pytest.mark.parametrize('failure', ['exit', 'timeout'])
def test_failed_dump_has_no_ready_or_partial_file(tmp_path, monkeypatch, failure):
    fake_dump(monkeypatch, failure=failure)
    with pytest.raises(files.BackupError):
        files.create_backup(tmp_path, SETTINGS)
    assert list(tmp_path.glob('*.dump')) == []
    assert list(tmp_path.glob('*.partial')) == []


def test_invalid_archive_does_not_become_ready(tmp_path, monkeypatch):
    fake_dump(monkeypatch, invalid=True)
    with pytest.raises(files.BackupError):
        files.create_backup(tmp_path, SETTINGS)
    assert not list(tmp_path.glob('*.dump'))


def test_new_files_are_private_unique_and_validated(tmp_path, monkeypatch):
    calls = fake_dump(monkeypatch)
    one = files.create_backup(tmp_path, SETTINGS)
    two = files.create_backup(tmp_path, SETTINGS)
    assert one != two and one.read_bytes() == two.read_bytes()
    assert stat.S_IMODE(one.stat().st_mode) == 0o600
    assert len([c for c, _ in calls if c[0] == 'pg_restore']) == 2
    for command, options in calls:
        assert 'private-dummy' not in command


def test_same_volume_lock_blocks_a_second_writer(tmp_path, monkeypatch):
    calls = fake_dump(monkeypatch)
    with files.backup_lock(tmp_path):
        with pytest.raises(files.BackupBusy):
            files.create_backup(tmp_path, SETTINGS)
    assert not calls


def test_publish_never_overwrites_an_existing_copy(tmp_path):
    target = tmp_path / 'old.dump'; target.write_bytes(b'old')
    with files.staging_file(tmp_path) as temporary:
        temporary.write_bytes(b'new')
        with pytest.raises(FileExistsError):
            files.publish(temporary, target)
    assert target.read_bytes() == b'old'


def test_daily_copy_is_validated_and_not_duplicated(tmp_path, monkeypatch):
    calls = fake_dump(monkeypatch)
    one = files.create_backup(tmp_path, SETTINGS, daily='2026-11-16')
    two = files.create_backup(tmp_path, SETTINGS, daily='2026-11-16')
    assert one == two
    assert len([c for c, _ in calls if c[0] == 'pg_dump']) == 1


def test_old_incomplete_daily_dump_is_quarantined(tmp_path, monkeypatch):
    old = tmp_path / 'elfar-2026-11-16.dump'; old.write_bytes(b'broken')
    fake_dump(monkeypatch)
    result = files.create_backup(tmp_path, SETTINGS, daily='2026-11-16')
    assert result.name.startswith('accord-auto-2026-11-16-')
    assert not old.exists()
    assert len(list(tmp_path.glob('*.invalid-*'))) == 1


@pytest.mark.asyncio
async def test_database_backup_switch_overrides_environment(tmp_path, monkeypatch):
    @asynccontextmanager
    async def repo():
        yield SimpleNamespace()
    monkeypatch.setattr(tasks, 'open_repo', repo)
    monkeypatch.setattr(tasks, 'get_shop_settings', AsyncMock(return_value=SimpleNamespace(backup_enabled=False)))
    monkeypatch.setattr(tasks.settings, 'backup_enabled', True)
    monkeypatch.setattr(tasks, '_backup_dir', lambda: tmp_path)
    mock = AsyncMock()
    monkeypatch.setattr('starlette.concurrency.run_in_threadpool', mock)
    assert await tasks.run_backup_if_due({}) is False
    mock.assert_not_called()


@pytest.mark.asyncio
async def test_enabled_database_switch_can_override_disabled_environment(tmp_path, monkeypatch):
    @asynccontextmanager
    async def repo():
        yield SimpleNamespace()
    monkeypatch.setattr(tasks, 'open_repo', repo)
    monkeypatch.setattr(tasks, 'get_shop_settings', AsyncMock(return_value=SimpleNamespace(
        backup_enabled=True, backup_hour=datetime.now(timezone.utc).hour, tz=timezone.utc)))
    monkeypatch.setattr(tasks.settings, 'backup_enabled', False)
    monkeypatch.setattr(tasks, '_backup_dir', lambda: tmp_path)
    file = tmp_path / 'valid.dump'; file.write_bytes(b'PGDMP')
    mock = AsyncMock(return_value=file)
    monkeypatch.setattr('starlette.concurrency.run_in_threadpool', mock)
    state = {}
    assert await tasks.run_backup_if_due(state) is True
    assert state['last_backup_date'] == datetime.now(timezone.utc).date()
    assert await tasks.run_backup_if_due(state) is False
    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_scheduler_failure_remains_retryable(tmp_path, monkeypatch):
    @asynccontextmanager
    async def repo():
        yield SimpleNamespace()
    monkeypatch.setattr(tasks, 'open_repo', repo)
    monkeypatch.setattr(tasks, 'get_shop_settings', AsyncMock(return_value=SimpleNamespace(
        backup_enabled=True, backup_hour=datetime.now(timezone.utc).hour, tz=timezone.utc)))
    monkeypatch.setattr(tasks, '_backup_dir', lambda: tmp_path)
    monkeypatch.setattr('starlette.concurrency.run_in_threadpool', AsyncMock(side_effect=files.BackupError('timeout')))
    state = {}
    assert await tasks.run_backup_if_due(state) is False
    assert 'last_backup_date' not in state


@pytest.mark.asyncio
async def test_old_browser_restore_cannot_execute_any_command(tmp_path, monkeypatch):
    source = tmp_path / 'source.dump'; source.write_bytes(b'PGDMP')
    monkeypatch.setattr(backups, 'backup_dir', lambda: tmp_path)
    calls = []
    monkeypatch.setattr(files.subprocess, 'run', lambda *a, **kw: calls.append(a))
    with pytest.raises(HTTPException) as error:
        await backups.restore(source.name, confirm=source.name, who=SimpleNamespace(login='audit'))
    assert error.value.status_code == 409
    assert source.read_bytes() == b'PGDMP' and not calls


@pytest.mark.asyncio
async def test_api_backup_does_not_block_the_event_loop(tmp_path, monkeypatch):
    import time
    from shop.services.backup_jobs import JobStore
    store = JobStore(tmp_path / 'jobs', tmp_path / 'backups')
    enqueue = store.enqueue
    def slow(*args):
        time.sleep(.12)
        return enqueue(*args)
    monkeypatch.setattr(store, 'enqueue', slow)
    monkeypatch.setattr(backups, 'configured_store', lambda: store)
    fired = []
    async def heartbeat():
        await asyncio.sleep(.02)
        fired.append('alive')
    operation = asyncio.create_task(backups.enqueue_job(backups.BackupJobIn(client_key='a'*32), who=SimpleNamespace(login='audit')))
    await heartbeat()
    assert fired and not operation.done()
    assert (await operation)['status'] == 'queued'


def bare_host(tmp_path):
    obj = host.HostBackup.__new__(host.HostBackup)
    obj.root = tmp_path; obj.directory = tmp_path / 'backups';obj.directory.mkdir()
    obj.project = 'accord-niche';obj.database = 'accord';obj.db = 'database-owned'
    obj.values = {'POSTGRES_USER': 'accord'}
    obj.compose = ['docker', 'compose', '-p', 'accord-niche']
    obj.env = {}
    return obj


def test_host_inventory_rejects_elfar_before_any_stop(tmp_path):
    import json
    obj = bare_host(tmp_path)
    obj.run = lambda command, **kw: (b'foreign-id' if command[1] == 'ps' else json.dumps([{
        'Id': 'foreign-id', 'Config': {'Labels': {'com.docker.compose.project': 'deploy',
        'com.docker.compose.service': 'db', 'com.docker.compose.project.working_dir': '/opt/elfar/deploy'}}}]).encode())
    with pytest.raises(files.BackupError, match='Належність'):
        obj.inventory()


def test_host_inventory_rejects_wrong_working_directory(tmp_path):
    import json
    obj = bare_host(tmp_path)
    row = {'Id': 'foreign-id', 'Config': {'Labels': {'com.docker.compose.project': obj.project,
        'com.docker.compose.service': 'db', 'com.docker.compose.project.working_dir': '/opt/elfar/deploy',
        'com.docker.compose.project.config_files': str(tmp_path / 'deploy/docker-compose.domains.yml')}}}
    obj.run = lambda command, **kw: b'foreign-id' if command[1] == 'ps' else json.dumps([row]).encode()
    with pytest.raises(files.BackupError):
        obj.inventory()


def setup_restore(tmp_path, monkeypatch):
    obj = bare_host(tmp_path)
    source = tmp_path / 'source.dump';source.write_bytes(b'PGDMP')
    events = []
    obj.validate = lambda handle: events.append('validate')
    obj.stage_archive = lambda handle: events.append('stage')
    rows = {'db': {'Id': obj.db}, 'api': {'Id': 'api-owned', 'State': {'Running': True}},
            'bot': {'Id': 'bot-owned', 'State': {'Running': False}}}
    obj.inventory = lambda: rows
    obj.revisions = lambda: ({'current'}, {'current'})
    def query(db, sql):
        events.append('query')
        return '0' if 'pg_stat_activity' in sql else 'current'
    obj.query = query
    def dump(prefix):
        events.append('safety')
        return tmp_path / 'safety.dump'
    obj.dump = dump
    import json
    def run(command, **kw):
        events.append(command)
        return json.dumps([{'State': {'Running': False}}]).encode() if command[1] == 'inspect' else b''
    obj.run = run
    # The real single-transaction schema replacement is exercised against
    # PostgreSQL in test_backup_postgres.py; here only the ordering matters.
    obj.replace_database = lambda handle: events.append(['replace_database'])
    return obj, source, events


def test_restore_safety_failure_restarts_original_writers_without_restore(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    def failure(prefix):
        raise files.BackupError('safety failed')
    obj.dump = failure
    with pytest.raises(files.BackupError):
        obj.restore(source, source.name)
    assert ['docker', 'start', 'api-owned'] in events
    assert ['replace_database'] not in events


def test_restore_failure_keeps_writers_stopped(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    def replace(handle):
        events.append(['replace_database'])
        raise files.BackupError('restore failed')
    obj.replace_database = replace
    with pytest.raises(files.BackupError):
        obj.restore(source, source.name)
    assert 'safety' in events
    assert ['docker', 'start', 'api-owned'] not in events


def test_successful_restore_is_transactional_and_restarts_only_original_writers(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    obj.restore(source, source.name)
    command = ['replace_database']
    assert command in events
    assert events.index('safety') < events.index(command)
    assert ['docker', 'start', 'api-owned'] in events
    assert not any(isinstance(e, list) and 'bot-owned' in e for e in events)


def test_invalid_archive_never_stops_the_shop(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    obj.stage_archive = lambda handle: (_ for _ in ()).throw(files.BackupError('invalid archive'))
    with pytest.raises(files.BackupError):
        obj.restore(source, source.name)
    assert not any(isinstance(e, list) and 'stop' in e for e in events)


def test_foreign_database_connections_prevent_restore(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    obj.query = lambda *a: '1'
    with pytest.raises(files.BackupError, match='підключення'):
        obj.restore(source, source.name)
    assert 'safety' not in events
    assert ['docker', 'start', 'api-owned'] in events


def test_pending_migration_revision_mismatch_is_not_success(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    original = obj.query
    obj.query = lambda db, sql: 'older' if db == obj.database else original(db, sql)
    with pytest.raises(files.BackupError, match='Ревізія'):
        obj.restore(source, source.name)
    assert ['docker', 'start', 'api-owned'] not in events

@pytest.mark.parametrize('problem', ['namespace', 'volume', 'credentials', 'directory-link'])
def test_host_initialization_refuses_unsafe_targets(tmp_path, monkeypatch, problem):
    from setup_domains import fresh_environment
    from shop.domain_security import ORIGINS, HOSTS
    values = fresh_environment()
    values.update(ORIGINS)
    values.update(TRUSTED_HOSTS=','.join(sorted(HOSTS)), ENABLE_API_DOCS='false', DOMAIN_ONLY='true')
    if problem == 'namespace':
        values['COMPOSE_PROJECT_NAME'] = 'deploy'
    if problem == 'directory-link':
        external = tmp_path / 'external';external.mkdir()
        (tmp_path / 'backups').symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(host, 'parse_env', lambda path: values)
    row = {'Id': 'db-owned', 'State': {'Running': True}, 'Config': {'Env': [k+'='+values[k] for k in ('POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD')]},
           'Mounts': [{'Destination': '/var/lib/postgresql/data', 'Name': values['COMPOSE_PROJECT_NAME']+'_pgdata'}]}
    if problem == 'volume':
        row['Mounts'][0]['Name'] = 'deploy_pgdata'
    elif problem == 'credentials':
        row['Config']['Env'][0] = 'POSTGRES_USER=foreign'
    monkeypatch.setattr(host.HostBackup, 'inventory', lambda self: {'db': row})
    # ELFAR's project name is rejected already by the .env.domains check.
    with pytest.raises(ValueError if problem == 'namespace' else files.BackupError):
        host.HostBackup(tmp_path)


def test_retention_keeps_manual_uploaded_and_safety_files(tmp_path, monkeypatch):
    import os,time
    monkeypatch.setattr(tasks, '_backup_dir', lambda: tmp_path)
    names = ['elfar-2026-01-01.dump', 'accord-auto-2026-01-01-time-random.dump',
             'elfar-manual-2026-01-01.dump', 'elfar-before-restore-20260101.dump',
             'accord-manual-2026-01-01.dump', 'accord-upload-2026-01-01.dump']
    for name in names:
        path = tmp_path/name;path.write_bytes(b'PGDMP');os.utime(path, (time.time()-86400*90,)*2)
    assert tasks.prune_backups(14) == 2
    assert sorted(path.name for path in tmp_path.glob('*.dump')) == sorted(names[2:])


@pytest.mark.asyncio
async def test_api_busy_response_does_not_queue_a_second_copy(tmp_path, monkeypatch):
    from shop.services.backup_jobs import JobStore
    store = JobStore(tmp_path / 'jobs', tmp_path / 'backups')
    monkeypatch.setattr(backups, 'configured_store', lambda: store)
    with files.backup_lock(store.directory), pytest.raises(HTTPException) as error:
        await backups.enqueue_job(backups.BackupJobIn(client_key='b'*32), who=SimpleNamespace(login='audit'))
    assert error.value.status_code == 409
    assert not store.recent()


def test_restore_stops_and_restarts_the_previously_running_maintenance_worker(tmp_path, monkeypatch):
    obj, source, events = setup_restore(tmp_path, monkeypatch)
    rows = obj.inventory()
    rows['maintenance'] = {'Id': 'maintenance-owned', 'State': {'Running': True}}
    obj.restore(source, source.name)
    stop = next(e for e in events if isinstance(e, list) and e[1] == 'stop')
    assert stop[-2:] == ['api-owned', 'maintenance-owned']
    assert events.index(stop) < events.index('safety')
    assert ['docker', 'start', 'api-owned', 'maintenance-owned'] in events
    assert not any(isinstance(e, list) and 'bot-owned' in e for e in events)
