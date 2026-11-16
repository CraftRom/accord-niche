"""Exercise the host restore algorithm with real PostgreSQL tools, never Docker/VPS."""
import os
from pathlib import Path
import subprocess
import time
import uuid
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('accord_restore_pg', ROOT / 'scripts/accord_backup.py')
host = importlib.util.module_from_spec(spec);spec.loader.exec_module(host)


@pytest.fixture(scope='module')
def postgres(tmp_path_factory):
    binary = os.environ.get('QA_POSTGRES_BIN')
    port = os.environ.get('QA_BACKUP_POSTGRES_PORT')
    if not binary or not port:
        pytest.skip('Set QA_POSTGRES_BIN and QA_BACKUP_POSTGRES_PORT for disposable PostgreSQL restore tests')
    binary = Path(binary); directory = tmp_path_factory.mktemp('backup-postgres');data = directory / 'data'
    subprocess.run([str(binary/'initdb'), '-D', str(data), '-U', 'postgres', '--no-locale', '--encoding=UTF8', '--auth=trust'],
        capture_output=True, check=True, timeout=30)
    with (directory/'server.log').open('wb') as output:
        process = subprocess.Popen([str(binary/'postgres'), '-D', str(data), '-h', '127.0.0.1', '-p', port,
            '-c', 'unix_socket_directories='], stdout=output, stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    pytest.fail((directory/'server.log').read_text())
                check = subprocess.run([str(binary/'pg_isready'), '-h', '127.0.0.1', '-p', port], capture_output=True)
                if check.returncode == 0:
                    break
                time.sleep(.1)
            else:
                pytest.fail('Temporary PostgreSQL startup timeout')
            # A pre-existing listener must never become our test database.
            identity = subprocess.run([str(binary/'psql'), '-h', '127.0.0.1', '-p', port,
                '-U', 'postgres', '-d', 'postgres', '-X', '-At', '-c', 'SHOW data_directory'],
                capture_output=True, timeout=5)
            assert identity.returncode == 0 and identity.stdout.decode().strip() == str(data.resolve()), 'Port is not owned by this disposable PostgreSQL cluster'
            assert process.poll() is None
            yield binary, port
        finally:
            if process.poll() is None:
                process.terminate();process.wait(timeout=10)


@pytest.fixture
def tool(postgres, tmp_path):
    binary, port = postgres
    obj = host.HostBackup.__new__(host.HostBackup)
    obj.root = tmp_path;obj.directory = tmp_path/'backups';obj.directory.mkdir()
    revisions = tmp_path/'backend/alembic/versions';revisions.mkdir(parents=True)
    (revisions/'current.py').write_text("revision = 'current'\ndown_revision = None\n")
    obj.database = 'accord_test_' + uuid.uuid4().hex
    obj.db = 'isolated-postgres';obj.env = os.environ.copy();obj.compose = ['test-migration-step']
    obj.values = {'POSTGRES_USER': 'postgres'}
    obj.db_command = lambda name, args: [str(binary/name), '-h', '127.0.0.1', '-p', port, '-U', 'postgres', *args]
    real_run = obj.run
    obj.run = lambda command, **kw: b'' if command[0] == 'test-migration-step' else real_run(command, **kw)
    obj.inventory = lambda: {'db': {'Id': obj.db}}
    obj.run(obj.db_command('createdb', ['--maintenance-db=postgres', obj.database]))
    obj.query(obj.database, "CREATE TABLE alembic_version(version_num text);INSERT INTO alembic_version VALUES('current');"
        "CREATE TABLE users(id int primary key);CREATE TABLE products(id int primary key);"
        "CREATE TABLE orders(id int primary key);INSERT INTO users VALUES(1);INSERT INTO orders VALUES(1),(2);")
    try:
        yield obj
    finally:
        obj.run(obj.db_command('dropdb', ['--maintenance-db=postgres', '--if-exists', obj.database]))


def test_real_archive_restores_data_and_safety_preserves_previous_state(tool):
    archive = tool.dump()
    tool.query(tool.database, 'INSERT INTO orders VALUES(3)')
    tool.restore(archive, archive.name)
    assert tool.query(tool.database, 'SELECT count(*) FROM orders') == '2'
    safety = list(tool.directory.glob('accord-before-restore-*.dump'))
    assert len(safety) == 1
    with safety[0].open('rb', buffering=0) as handle:
        tool.validate(handle)
        tool.stage_archive(handle)
    assert not tool.query('postgres', "SELECT datname FROM pg_database WHERE datname LIKE 'accord_check_%'")


def test_real_transaction_rolls_back_drop_failures(tool):
    archive = tool.dump()
    tool.query(tool.database, 'INSERT INTO orders VALUES(3);CREATE TABLE extra(order_id int REFERENCES orders(id));INSERT INTO extra VALUES(3);')
    with pytest.raises(host.BackupError):
        tool.restore(archive, archive.name)
    assert tool.query(tool.database, 'SELECT count(*) FROM orders') == '3'
    assert tool.query(tool.database, 'SELECT count(*) FROM users') == '1'
    assert tool.query(tool.database, 'SELECT count(*) FROM extra') == '1'
    assert list(tool.directory.glob('accord-before-restore-*.dump'))


def test_unknown_revision_is_rejected_before_target_changes(tool):
    tool.query(tool.database, "UPDATE alembic_version SET version_num='unknown'")
    archive = tool.dump()
    tool.query(tool.database, "UPDATE alembic_version SET version_num='current';INSERT INTO orders VALUES(3)")
    with pytest.raises(host.BackupError, match='Ревізія'):
        tool.restore(archive, archive.name)
    assert tool.query(tool.database, 'SELECT count(*) FROM orders') == '3'
    assert not list(tool.directory.glob('accord-before-restore-*.dump'))
    assert not tool.query('postgres', "SELECT datname FROM pg_database WHERE datname LIKE 'accord_check_%'")


def test_durable_job_creates_a_real_restoreable_postgres_dump(tool, postgres, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from shop.services.backup_jobs import JobStore
    binary, port = postgres
    monkeypatch.setenv('PATH', str(binary) + os.pathsep + os.environ['PATH'])
    settings = SimpleNamespace(postgres_host='127.0.0.1', postgres_port=port,
        postgres_user='postgres', postgres_password='', postgres_db=tool.database)
    store = JobStore(tmp_path/'jobs', tmp_path/'job-backups')
    request = store.enqueue('real-postgresql-job-request', 'audit')
    result = store.run_next(settings)
    assert result['status'] == 'succeeded' and result['id'] == request['id']
    archive = store.backups / result['result']['name']
    assert archive.stat().st_size == result['result']['sizeBytes']
    tool.query(tool.database, 'INSERT INTO orders VALUES(3)')
    tool.restore(archive, archive.name)
    assert tool.query(tool.database, 'SELECT count(*) FROM orders') == '2'
    assert store.enqueue('real-postgresql-job-request', 'audit')['id'] == request['id']
    assert store.run_next(settings) is None


def test_complete_bundle_restores_database_and_media_and_safety_can_undo_it(tool,tmp_path):
    from test_recovery_bundle import install_local_media_transport
    from recovery_archive import open_bundle
    operation,root,rows,events=install_local_media_transport(tool,tmp_path)
    configuration=(tool.root/'.env.domains').read_bytes()
    source=operation.bundle()
    assert rows['api']['State']['Running'] and not rows['bot']['State']['Running']
    with open_bundle(source) as (payload, manifest):
        assert manifest['media']['photo.jpg']['size']==len(b'original photo')
        assert (payload/'environment.env').read_bytes()==configuration
    tool.query(tool.database,'INSERT INTO orders VALUES(3)')
    (root/'media/photo.jpg').write_bytes(b'current photo')
    (root/'media/stale.jpg').write_bytes(b'stale')
    operation.restore(source,source.name)
    assert tool.query(tool.database,'SELECT count(*) FROM orders')=='2'
    assert (root/'media/photo.jpg').read_bytes()==b'original photo'
    assert not (root/'media/stale.jpg').exists()
    assert (tool.root/'.env.domains').read_bytes()==configuration
    assert rows['api']['State']['Running'] and not rows['bot']['State']['Running']
    safety=next(p for p in tool.directory.glob('*.tar.gz') if p!=source)
    operation.restore(safety,safety.name)
    assert tool.query(tool.database,'SELECT count(*) FROM orders')=='3'
    assert (root/'media/photo.jpg').read_bytes()==b'current photo'
    assert (root/'media/stale.jpg').read_bytes()==b'stale'
    assert not list(root.glob('.accord-media-*'))


def test_failed_bundle_restore_keeps_writers_stopped_and_can_recover_from_full_safety(tool,tmp_path,monkeypatch):
    from test_recovery_bundle import install_local_media_transport
    from shop.backup_files import BackupError
    operation,root,rows,events=install_local_media_transport(tool,tmp_path)
    source=operation.bundle()
    tool.query(tool.database,'INSERT INTO orders VALUES(3)')
    (root/'media/photo.jpg').write_bytes(b'current photo')
    real_media=operation.media
    def fail(operation,token,**kwargs):
        if operation=='commit':raise BackupError('simulated filesystem failure')
        return real_media(operation,token,**kwargs)
    monkeypatch.setattr(operation,'media',fail)
    with pytest.raises(BackupError):operation.restore(source,source.name)
    assert not rows['api']['State']['Running']
    from recovery_archive import recovery_states
    assert recovery_states(tool.directory)[0]['phase']=='failed_after_change'
    assert recovery_states(tool.directory)[0]['safety']
    assert tool.query(tool.database,'SELECT count(*) FROM orders')=='2'
    assert (root/'media/photo.jpg').read_bytes()==b'current photo'
    safety=next(p for p in tool.directory.glob('*.tar.gz') if p!=source)
    monkeypatch.setattr(operation,'media',real_media)
    operation.restore(safety,safety.name)
    assert tool.query(tool.database,'SELECT count(*) FROM orders')=='3'
    assert (root/'media/photo.jpg').read_bytes()==b'current photo'
    assert not rows['api']['State']['Running']  # only previously running services are restarted


def test_failed_safety_bundle_does_not_change_live_database_or_media(tool,tmp_path,monkeypatch):
    from test_recovery_bundle import install_local_media_transport
    from shop.backup_files import BackupError
    operation,root,rows,events=install_local_media_transport(tool,tmp_path)
    source=operation.bundle()
    tool.query(tool.database,'INSERT INTO orders VALUES(3)')
    (root/'media/photo.jpg').write_bytes(b'current photo')
    def fail(*args):raise BackupError('not enough disk space')
    monkeypatch.setattr(operation,'snapshot',fail)
    with pytest.raises(BackupError):operation.restore(source,source.name)
    assert tool.query(tool.database,'SELECT count(*) FROM orders')=='3'
    assert (root/'media/photo.jpg').read_bytes()==b'current photo'
    assert rows['api']['State']['Running']


def test_wrong_encryption_key_is_rejected_before_stopping_the_store(tool,tmp_path):
    from test_recovery_bundle import install_local_media_transport, write_private
    from setup_domains import fresh_environment, serialize
    from shop.backup_files import BackupError
    operation,root,rows,events=install_local_media_transport(tool,tmp_path)
    source=operation.bundle();events.clear()
    tool.values['DATA_ENCRYPTION_KEY']=fresh_environment()['DATA_ENCRYPTION_KEY']
    write_private(tool.root/'.env.domains',serialize(tool.values))
    with pytest.raises(BackupError,match='DATA_ENCRYPTION_KEY'):operation.restore(source,source.name)
    assert not events
    assert tool.query(tool.database,'SELECT count(*) FROM orders')=='2'
    assert rows['api']['State']['Running']
