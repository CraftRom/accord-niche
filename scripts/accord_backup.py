#!/usr/bin/env python3
"""ACCORD-only host operations. Never selects containers by the legacy 'deploy' name."""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))
from setup_domains import parse_env, validate_domain_environment
from shop.backup_files import BackupError, backup_lock, staging_file, unique_name, publish, SIGNATURE

WRITERS = {'api', 'bot', 'scheduler', 'maintenance'}
SERVICES = WRITERS | {'db', 'redis', 'migrate', 'data-init', 'accord-website', 'accord-dashboard', 'accord-miniapp'}


class HostBackup:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.values = parse_env(self.root / '.env.domains')
        validate_domain_environment(self.values)
        self.project = self.values['COMPOSE_PROJECT_NAME']
        if self.project in {'deploy', 'elfar'} or self.project.startswith('elfar-'):
            raise BackupError('Namespace ELFAR заборонений для операцій ACCORD')
        self.directory = self.root / 'backups'
        if self.directory.is_symlink():
            raise BackupError('Каталог копій не може бути символічним посиланням')
        self.env = {k: v for k, v in os.environ.items()
                    if k not in self.values and not k.startswith('COMPOSE_')}
        self.compose = ['docker', 'compose', '--project-name', self.project,
            '--env-file', str(self.root / '.env.domains'),
            '-f', str(self.root / 'deploy/docker-compose.domains.yml'),
            '--profile', 'bot', '--profile', 'workers']
        self.containers = self.inventory()
        db = self.containers.get('db')
        if not db or not db['State'].get('Running'):
            raise BackupError('Контейнер БД ACCORD не запущений')
        self.db = db['Id']
        values = dict(item.split('=', 1) for item in db['Config'].get('Env', []) if '=' in item)
        if any(values.get(k) != self.values[k] for k in ('POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD')):
            raise BackupError('POSTGRES_* контейнера не збігаються з .env.domains; операцію скасовано')
        mounts = [m for m in db.get('Mounts', []) if m.get('Destination') == '/var/lib/postgresql/data']
        if len(mounts) != 1 or mounts[0].get('Name') != self.project + '_pgdata':
            raise BackupError('Том БД не є штатним pgdata цього проєкту ACCORD')
        self.database = self.values['POSTGRES_DB']
        if self.database in {'postgres', 'template0', 'template1'}:
            raise BackupError('Відновлення системної БД заборонено')

    def run(self, command, *, stdin=None, stdout=None, timeout=120):
        try:
            result = subprocess.run(command, stdin=stdin, stdout=stdout or subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=timeout, env=self.env, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise BackupError('Команда не завершилася. Перевірте Docker, диск і доступ до БД.') from None
        if result.returncode:
            # Never print DB credentials, raw provider errors or container Config.Env.
            raise BackupError(f'Команда {command[0]} завершилася помилкою (код {result.returncode})')
        return result.stdout if stdout is None else b''

    def inventory(self):
        ids = self.run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + self.project]).decode().split()
        if not ids:
            raise BackupError('Контейнери цього проєкту ACCORD не знайдено')
        rows = json.loads(self.run(['docker', 'inspect', *ids]))
        found = {}
        for row in rows:
            labels = row.get('Config', {}).get('Labels', {}) or {}
            service = labels.get('com.docker.compose.service')
            if (labels.get('com.docker.compose.project') != self.project
                or labels.get('com.docker.compose.project.working_dir') not in {str(self.root), str(self.root / 'deploy')}
                or str(self.root / 'deploy/docker-compose.domains.yml') not in
                    labels.get('com.docker.compose.project.config_files', '').split(',')
                or service not in SERVICES):
                raise BackupError('Належність контейнера ACCORD не підтверджена')
            if service in found:
                raise BackupError('Виявлено декілька контейнерів сервісу; потрібна ручна перевірка')
            found[service] = row
        if found.get('migrate', {}).get('State', {}).get('Running'):
            raise BackupError('Міграції вже виконуються; повторіть операцію після їх завершення')
        return found

    def db_command(self, tool, args):
        # Password stays in the existing DB container environment, never host argv.
        return ['docker', 'exec', '-i', self.db, 'sh', '-ec',
            'export PGPASSWORD="$POSTGRES_PASSWORD"; exec "$@"', 'accord-pg',
            tool, '-h', '127.0.0.1', '-U', self.values['POSTGRES_USER'], *args]

    def query(self, database, sql):
        return self.run(self.db_command('psql', ['-d', database, '-X', '-At', '-v', 'ON_ERROR_STOP=1', '-c', sql])).decode().strip()

    def validate(self, handle):
        if handle.read(5) != SIGNATURE:
            raise BackupError('Потрібна довірена копія у форматі pg_dump -Fc')
        handle.seek(0)
        self.run(self.db_command('pg_restore', ['--list']), stdin=handle)
        handle.seek(0)

    def dump(self, prefix='accord-host-manual'):
        self.directory.mkdir(parents=True, exist_ok=True)
        with staging_file(self.directory) as temporary:
            with temporary.open('wb') as handle:
                self.run(self.db_command('pg_dump', ['-d', self.database, '-Fc']), stdout=handle, timeout=1800)
            with temporary.open('rb', buffering=0) as handle:
                self.validate(handle)
            return publish(temporary, self.directory / unique_name(prefix))

    def backup(self):
        with backup_lock(self.directory):
            target = self.dump()
        print('Копія БД ACCORD:', target)
        return target

    def stage_archive(self, handle):
        """Actually restore all archive data before taking the shop offline."""
        temporary = 'accord_check_' + uuid.uuid4().hex
        self.run(self.db_command('createdb', ['--maintenance-db=postgres', '-T', 'template0', temporary]))
        try:
            handle.seek(0)
            self.run(self.db_command('pg_restore', ['-d', temporary, '--exit-on-error',
                '--single-transaction', '--no-owner', '--no-privileges']), stdin=handle, timeout=3600)
            revisions = self.query(temporary, 'SELECT version_num FROM alembic_version').splitlines()
            known, _ = self.revisions()
            if len(revisions) != 1 or revisions[0] not in known:
                raise BackupError('Ревізія копії відсутня в цьому коді. БД магазину не змінено.')
            self.query(temporary, 'SELECT count(*) FROM users')
            self.query(temporary, 'SELECT count(*) FROM orders')
            self.query(temporary, 'SELECT count(*) FROM products')
        finally:
            self.run(self.db_command('dropdb', ['--maintenance-db=postgres', '--if-exists', temporary]))
        handle.seek(0)
        return revisions[0]

    def revisions(self):
        known, parents = set(), set()
        for file in (self.root / 'backend/alembic/versions').glob('*.py'):
            for node in ast.parse(file.read_text()).body:
                pairs = []
                if isinstance(node, ast.Assign):
                    pairs = [(t.id, node.value) for t in node.targets if isinstance(t, ast.Name)]
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    pairs = [(node.target.id, node.value)]
                for name, value in pairs:
                    if name == 'revision':
                        known.add(ast.literal_eval(value))
                    elif name == 'down_revision':
                        parent = ast.literal_eval(value)
                        parents.update(parent if isinstance(parent, (tuple, list)) else [parent])
        heads = known - parents
        if len(heads) != 1:
            raise BackupError('Локальний код повинен мати одну ревізію Alembic head')
        return known, heads

    def restore(self, source, confirm):
        source = Path(source).absolute()
        if source.is_symlink() or not source.is_file() or confirm != source.name:
            raise BackupError('Вкажіть звичайний файл копії та точну назву через --confirm')
        # Pin the opened inode for the entire operation, including validation.
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb', buffering=0) as handle, backup_lock(self.directory):
            self.validate(handle)
            self.stage_archive(handle)
            # Refresh ownership and running state immediately before stopping anything.
            self.containers = self.inventory()
            if self.containers.get('db', {}).get('Id') != self.db:
                raise BackupError('Контейнер БД змінився; повторіть перевірку')
            writers = [row['Id'] for name, row in self.containers.items()
                       if name in WRITERS and row['State'].get('Running')]
            changed = False
            stopped = False
            try:
                if writers:
                    stopped = True
                    self.run(['docker', 'stop', '--time', '60', *writers], timeout=240)
                    for row in json.loads(self.run(['docker', 'inspect', *writers])):
                        if row['State'].get('Running'):
                            raise BackupError('Не всі процеси запису зупинені')
                active = self.query('postgres', "SELECT count(*) FROM pg_stat_activity WHERE datname='" + self.database + "'")
                if active != '0':
                    raise BackupError('До БД залишилися сторонні підключення. Відновлення не почалося.')
                safety = self.dump('accord-before-restore')
                print('Перевірена запобіжна копія:', safety, flush=True)
                handle.seek(0)
                changed = True
                self.run(self.db_command('pg_restore', ['-d', self.database, '--clean', '--if-exists',
                    '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges']),
                    stdin=handle, timeout=3600)
                self.run(self.compose + ['run', '--rm', '--no-deps', '--pull', 'never', 'migrate'], timeout=1800)
                _, expected = self.revisions()
                current = set(self.query(self.database, 'SELECT version_num FROM alembic_version').splitlines())
                if current != expected:
                    raise BackupError('Ревізія після міграцій не збігається з поточним кодом')
                self.query(self.database, 'SELECT count(*) FROM orders')
            except BaseException:
                if changed:
                    print('Відновлення не підтверджено. Процеси запису залишено зупиненими; перевірте запобіжну копію.', file=sys.stderr)
                elif stopped:
                    self.run(['docker', 'start', *writers])
                raise
            if stopped:
                self.run(['docker', 'start', *writers])
            print('БД ACCORD відновлено; перевірки завершено. Запущено лише раніше активні процеси ACCORD.')


def main():
    cli = argparse.ArgumentParser(description='Перевірка, backup і контрольоване відновлення БД ACCORD')
    cli.add_argument('operation', choices=['check', 'backup', 'restore'])
    cli.add_argument('file', nargs='?')
    cli.add_argument('--confirm', help='Точна назва файла для заміни БД')
    args = cli.parse_args()
    host = HostBackup()
    if args.operation == 'check':
        print(json.dumps({'project': host.project, 'database': host.database,
            'services': {name: bool(row['State'].get('Running')) for name, row in host.containers.items()},
            'revision': host.query(host.database, 'SELECT version_num FROM alembic_version')}, ensure_ascii=False, indent=2))
    elif args.operation == 'backup':
        host.backup()
    else:
        if not args.file:
            cli.error('Для restore потрібен файл')
        confirm = args.confirm
        if confirm is None and sys.stdin.isatty():
            confirm = input('БД буде замінено. Введіть точну назву файла копії: ').strip()
        host.restore(args.file, confirm)


if __name__ == '__main__':
    try:
        main()
    except (BackupError, OSError, ValueError) as exc:
        print('ПОМИЛКА:', str(exc), file=sys.stderr)
        sys.exit(1)
