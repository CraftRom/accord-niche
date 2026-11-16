#!/usr/bin/env python3
"""Coherent ACCORD database/media snapshots. Never exports ELFAR volumes or keys."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import uuid

from accord_backup import HostBackup, ROOT, WRITERS
from setup_domains import parse_env, validate_domain_environment
from shop.backup_files import BackupError, backup_lock
from shop.build import BUILD
from recovery_archive import (open_bundle, private_copy, inspect_media, make_bundle,
                              write_state, recovery_states)

DEFAULT_TLS = Path('/etc/accord-niche/tls')


class Recovery:
    def __init__(self, host, tls_dir=DEFAULT_TLS):
        self.host = host
        self.tls_dir = Path(tls_dir)
        self.boundary()
        self.journal = None

    def record(self, phase, **fields):
        self.journal.update(phase=phase, updated_at=time.time(), **fields)
        return write_state(self.host.directory, self.journal)

    def begin(self, operation, writers, token):
        self.journal = {'id':token, 'operation':operation, 'writers':writers,
                        'project':self.host.project, 'safety':None, 'created_at':time.time()}
        return self.record('stopping')

    def boundary(self):
        h = self.host
        rows = h.inventory()
        if rows.get('db', {}).get('Id') != h.db:
            raise BackupError('Контейнер БД змінився; повторіть перевірку')
        api = rows.get('api')
        if not api: raise BackupError('Потрібен створений контейнер API ACCORD із томом appdata')
        mounts = [m for m in api.get('Mounts', []) if m.get('Destination') == '/data']
        if (len(mounts) != 1 or mounts[0].get('Type') != 'volume'
            or mounts[0].get('Name') != h.project + '_appdata'
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', api.get('Image', ''))):
            raise BackupError('Належність образу або тому appdata ACCORD не підтверджена')
        self.rows = rows; self.api = api
        self.volume = mounts[0]['Name']; self.image = api['Image']

    def media(self, operation, token, *, stdin=None, stdout=None):
        mode = 'readonly' if operation == 'export' else 'volume-nocopy'
        command = ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
                   '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--user', '1000:1000',
                   '--mount', f'type=volume,source={self.volume},target=/data,{mode}', '-i',
                   self.image, 'python', '-c', (ROOT/'scripts/recovery_media.py').read_text(), operation, token]
        return self.host.run(command, stdin=stdin, stdout=stdout, timeout=3600)

    def config(self, destination):
        h = self.host
        private_copy(h.root/'.env.domains', destination/'environment.env', 256*1024)
        values = parse_env(destination/'environment.env'); validate_domain_environment(values)
        if values != h.values: raise BackupError('Конфігурація змінилася після перевірки; повторіть операцію')
        runtime = dict(item.split('=',1) for item in self.api['Config'].get('Env', []) if '=' in item)
        for key in ('DATA_ENCRYPTION_KEY', 'JWT_SECRET', 'DASHBOARD_PASSWORD', 'DASHBOARD_LOGIN'):
            if not values.get(key) or runtime.get(key) != values[key]:
                raise BackupError('Ключі або облікові дані API не збігаються з конфігурацією: '+key)
        cert, key = self.tls_dir/'origin.pem', self.tls_dir/'origin.key'
        self.tls_included = False
        if cert.exists() or key.exists() or cert.is_symlink() or key.is_symlink():
            private_copy(cert, destination/'tls/origin.pem', 512*1024, secret=False)
            private_copy(key, destination/'tls/origin.key', 128*1024)
            self.validate_tls(destination)
            self.tls_included = True
        return values

    def validate_tls(self, directory):
        h = self.host; cert = directory/'tls/origin.pem'; key = directory/'tls/origin.key'
        for name in ('accordniche.pp.ua','shop.accordniche.pp.ua','dashboard.accordniche.pp.ua'):
            h.run(['openssl','x509','-in',str(cert),'-noout','-checkhost',name])
        public_cert = h.run(['openssl','x509','-in',str(cert),'-pubkey','-noout'])
        public_key = h.run(['openssl','pkey','-in',str(key),'-passin','pass:','-pubout'])
        if public_cert != public_key: raise BackupError('TLS-сертифікат та приватний ключ не утворюють пару')

    def writers(self):
        return [row['Id'] for name,row in self.rows.items() if name in WRITERS and row['State'].get('Running')]

    def stop(self, writers):
        h = self.host
        if writers:
            h.run(['docker','stop','--time','60',*writers], timeout=240)
            for row in json.loads(h.run(['docker','inspect',*writers])):
                if row['State'].get('Running'): raise BackupError('Не всі процеси запису ACCORD зупинені')
        active = h.query('postgres', "SELECT count(*) FROM pg_stat_activity WHERE datname='"+h.database+"'")
        if active != '0': raise BackupError('Залишилися сторонні підключення до БД; операцію скасовано')

    def start(self, writers):
        if writers: self.host.run(['docker','start',*writers])

    def snapshot(self, directory):
        """Caller holds the host lock and has stopped all known writers."""
        h = self.host
        with tempfile.TemporaryDirectory(prefix='.accord-snapshot-', dir=directory) as tmp:
            payload = Path(tmp); self.config(payload)
            with (payload/'database.dump').open('xb') as output:
                os.chmod(output.name, 0o600)
                h.run(h.db_command('pg_dump', ['-d', h.database, '-Fc']), stdout=output, timeout=1800)
            with (payload/'database.dump').open('rb', buffering=0) as handle: h.validate(handle)
            with (payload/'media.tar').open('xb') as output:
                os.chmod(output.name, 0o600)
                self.media('export', uuid.uuid4().hex, stdout=output)
            media = inspect_media(payload/'media.tar')
            revision = h.query(h.database, 'SELECT version_num FROM alembic_version')
            known,_ = h.revisions()
            if revision not in known: raise BackupError('Ревізія БД відсутня в поточному коді')
            # Detect configuration edits made during the snapshot window.
            if parse_env(h.root/'.env.domains') != h.values:
                raise BackupError('Конфігурація змінилася під час копіювання')
            return make_bundle(directory, payload, project=h.project, revision=revision, build=BUILD, media=media)

    def bundle(self):
        h = self.host
        with backup_lock(h.directory):
            self.boundary(); writers = self.writers()
            journal = self.begin('bundle', writers, uuid.uuid4().hex)
            print('Журнал операції:', journal, flush=True)
            success = False
            try:
                self.stop(writers); self.record('capturing')
                target = self.snapshot(h.directory)
                self.record('captured', result=target.name); success = True
            finally:
                self.start(writers)
                self.record('finished' if success else 'failed_before_change')
        print('Узгоджений комплект ACCORD:', target)
        print('Файл містить секрети. Збережіть його поза VPS з обмеженим доступом.')
        if not self.tls_included:
            print('TLS-пара не включена: під час нового розгортання потрібно перевипустити сертифікат або вказати --tls-dir.')
        return target

    def restore(self, source, confirm):
        h = self.host; source = Path(source)
        if confirm != source.name: raise BackupError('Для відновлення потрібна точна назва комплекту через --confirm')
        with backup_lock(h.directory), open_bundle(source, h.directory) as (payload, manifest):
            if manifest['project'] != h.project: raise BackupError('Namespace комплекту не збігається з ACCORD')
            values = parse_env(payload/'environment.env'); validate_domain_environment(values)
            if values.get('DATA_ENCRYPTION_KEY') != h.values.get('DATA_ENCRYPTION_KEY'):
                raise BackupError('DATA_ENCRYPTION_KEY відрізняється. Спочатку підготуйте конфігурацію з комплекту; БД не змінено.')
            with (payload/'database.dump').open('rb', buffering=0) as handle:
                h.validate(handle); revision = h.stage_archive(handle)
                if revision != manifest['revision']:
                    raise BackupError('Ревізія SQL не збігається з описом комплекту; БД не змінено')
            self.boundary(); writers = self.writers(); changed = False; token = uuid.uuid4().hex
            journal = self.begin('restore', writers, token)
            print('Журнал операції:', journal, flush=True)
            try:
                self.stop(writers); self.record('capturing_safety')
                safety = self.snapshot(h.directory)
                self.record('preparing_media', safety=safety.name)
                print('Запобіжний комплект БД, медіа та конфігурації:', safety, flush=True)
                with (payload/'media.tar').open('rb', buffering=0) as handle:
                    staged = json.loads(self.media('stage', token, stdin=handle))
                if staged != manifest['media']: raise BackupError('Контрольні суми підготовлених медіа не збігаються')
                if parse_env(h.root/'.env.domains') != h.values: raise BackupError('Конфігурація змінилася до відновлення')
                with (payload/'database.dump').open('rb', buffering=0) as handle:
                    self.record('changing_database')
                    changed = True
                    h.run(h.db_command('pg_restore', ['-d',h.database,'--clean','--if-exists','--exit-on-error',
                          '--single-transaction','--no-owner','--no-privileges']), stdin=handle, timeout=3600)
                h.run(h.compose+['run','--rm','--no-deps','--pull','never','migrate'], timeout=1800)
                _,expected = h.revisions()
                if set(h.query(h.database,'SELECT version_num FROM alembic_version').splitlines()) != expected:
                    raise BackupError('Ревізія після міграцій не збігається з кодом')
                h.query(h.database,'SELECT count(*) FROM orders')
                self.record('committing_media')
                self.media('commit', token)
                self.record('restored')
            except BaseException:
                try: self.media('cleanup-stage', token)
                except BackupError: print('Незавершений каталог медіа потребує прибирання: '+token, file=sys.stderr)
                if changed:
                    self.record('failed_after_change')
                    print('Відновлення не підтверджено. Процеси ACCORD залишено зупиненими; використайте запобіжний комплект.', file=sys.stderr)
                else:
                    self.start(writers)
                    self.record('failed_before_change')
                raise
            # The live DB/media pair is verified. Old files are redundant with the safety bundle.
            try: self.media('cleanup-old', token)
            except BackupError:
                print('Попередній каталог медіа залишено в томі для ручного прибирання: '+token, file=sys.stderr)
            self.start(writers)
            self.record('finished')
        print('БД та медіа ACCORD відновлено разом. Конфігурацію й TLS автоматично не перезаписано.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Узгоджений аварійний комплект ACCORD')
    parser.add_argument('operation', choices=['bundle','verify','unpack','restore','status'])
    parser.add_argument('file', nargs='?')
    parser.add_argument('--output', type=Path, help='Новий приватний каталог для unpack')
    parser.add_argument('--work-dir', type=Path, help='Каталог для тимчасових даних offline verify/unpack; типово системний tmp')
    parser.add_argument('--confirm', help='Точна назва комплекту для заміни БД та медіа')
    parser.add_argument('--tls-dir', type=Path, default=DEFAULT_TLS, help='Каталог Origin CA; типово /etc/accord-niche/tls')
    args = parser.parse_args(argv)
    if args.operation == 'status':
        print(json.dumps(recovery_states(ROOT/'backups'), ensure_ascii=False, indent=2))
        return 0
    if args.operation in {'verify','unpack'}:
        if not args.file: parser.error('Потрібен файл комплекту')
        with open_bundle(args.file, args.work_dir) as (payload, manifest):
            if args.operation == 'unpack':
                if not args.output: parser.error('Потрібен новий каталог --output')
                args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
                try:
                    for name in ['manifest.json', *manifest['files']]:
                        private_copy(payload/name, args.output/name, 64*1024**3)
                except BaseException:
                    shutil.rmtree(args.output); raise
                print('Комплект розпаковано у приватний каталог:', args.output)
            print(json.dumps({'format':manifest['format'],'project':manifest['project'],'revision':manifest['revision'],
                  'media_files':len(manifest['media']),'tls_included':manifest['tls_included'],'checksums':'OK'},ensure_ascii=False))
        return 0
    recovery = Recovery(HostBackup(), args.tls_dir)
    if args.operation == 'bundle': recovery.bundle()
    else:
        if not args.file: parser.error('Потрібен файл комплекту')
        confirm = args.confirm
        if confirm is None and sys.stdin.isatty():
            confirm = input('БД та медіа ACCORD буде замінено. Введіть точну назву комплекту: ').strip()
        recovery.restore(args.file, confirm)
    return 0


if __name__ == '__main__':
    try: sys.exit(main())
    except (BackupError, OSError, ValueError):
        error = sys.exception()
        print('ПОМИЛКА:', str(error) if isinstance(error, BackupError) else 'Операцію не завершено; перевірте файл, диск і права доступу.', file=sys.stderr)
        sys.exit(1)
