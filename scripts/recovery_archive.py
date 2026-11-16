"""Bounded, non-executing recovery archive format. Only trusted admins restore SQL."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from setup_domains import parse_env, validate_domain_environment
import shutil
import stat
import tarfile
import tempfile

from shop.backup_files import BackupError, SIGNATURE, staging_file, publish, unique_name

MAX_TOTAL = 64 * 1024**3
MAX_FILE = 1024**3
MAX_ENTRIES = 100000
MAX_MANIFEST = 32 * 1024**2
PAYLOADS = {'database.dump', 'environment.env', 'media.tar', 'tls/origin.pem', 'tls/origin.key'}
REQUIRED = {'database.dump', 'environment.env', 'media.tar'}


def safe_path(name):
    if (not isinstance(name, str) or not name or len(name) > 512 or '\\' in name
        or name.startswith('/') or any(p in {'', '.', '..'} for p in name.split('/'))
        or any(ord(c) < 32 for c in name)):
        raise BackupError('Архів містить небезпечний шлях')
    return PurePosixPath(name)


def digest(handle, limit=MAX_TOTAL):
    h = hashlib.sha256(); size = 0
    while chunk := handle.read(1024 * 1024):
        size += len(chunk)
        if size > limit: raise BackupError('Перевищено ліміт архіву')
        h.update(chunk)
    return {'size': size, 'sha256': h.hexdigest()}


def file_digest(path):
    with Path(path).open('rb') as handle: return digest(handle)


def inspect_media(path):
    result = {}; total = 0; seen = set(); required_dirs = set(); files = set()
    with tarfile.open(path, 'r|') as archive:
        for member in archive:
            name = str(safe_path(member.name))
            if name in seen or len(seen) >= MAX_ENTRIES:
                raise BackupError('Повторні або надмірні записи медіа')
            parents = [str(p) for p in PurePosixPath(name).parents if str(p) != '.']
            if any(parent in files for parent in parents) or (member.isfile() and name in required_dirs):
                raise BackupError('Конфлікт файлів і каталогів медіа')
            required_dirs.update(parents); seen.add(name)
            if member.isdir(): continue
            files.add(name)
            if not member.isfile() or member.size > MAX_FILE:
                raise BackupError('У медіа дозволені лише звичайні файли та каталоги')
            total += member.size
            if total > MAX_TOTAL: raise BackupError('Медіа перевищують 64 ГіБ')
            with archive.extractfile(member) as handle: info = digest(handle, MAX_FILE)
            if info['size'] != member.size: raise BackupError('Обрізаний файл медіа')
            result[name] = info
    return result


def private_copy(source, target, limit, *, secret=True):
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as src:
        if not stat.S_ISREG(os.fstat(src.fileno()).st_mode):
            raise BackupError('Для конфігурації потрібен звичайний файл')
        if secret and os.fstat(src.fileno()).st_mode & 0o077:
            raise BackupError('Конфігурація або приватний ключ доступні іншим користувачам; потрібні права 0600')
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd_out = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd_out, 'wb') as output:
            total = 0
            while chunk := src.read(1024*1024):
                total += len(chunk)
                if total > limit: raise BackupError('Файл конфігурації завеликий')
                output.write(chunk)
            output.flush(); os.fsync(output.fileno())


def make_bundle(directory, payload_dir, *, project, revision, build, media):
    directory.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in sorted(PAYLOADS):
        path = payload_dir / name
        if path.exists(): files[name] = file_digest(path)
    if not REQUIRED <= files.keys(): raise BackupError('Неповний комплект відновлення')
    tls = {'tls/origin.pem', 'tls/origin.key'} & files.keys()
    if tls and len(tls) != 2: raise BackupError('Неповна пара TLS')
    manifest = {'format': 'accord-recovery', 'version': 1, 'project': project,
                'revision': revision, 'build': build, 'created_at': datetime.now(timezone.utc).isoformat(),
                'files': files, 'media': media, 'tls_included': len(tls) == 2}
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    if sum(info['size'] for info in files.values()) + len(raw) > MAX_TOTAL:
        raise BackupError('Комплект перевищує 64 ГіБ')
    if len(raw) > MAX_MANIFEST: raise BackupError('Опис комплекту завеликий')
    with staging_file(directory) as temporary:
        with tarfile.open(temporary, 'w:gz') as archive:
            import io
            info = tarfile.TarInfo('manifest.json'); info.size = len(raw); info.mode = 0o600
            archive.addfile(info, io.BytesIO(raw))
            for name in sorted(files): archive.add(payload_dir/name, arcname=name, recursive=False)
        name = unique_name('accord-recovery').removesuffix('.dump') + '.tar.gz'
        return publish(temporary, directory/name)


@contextmanager
def open_bundle(source, workspace=None):
    source = Path(source)
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle, tempfile.TemporaryDirectory(prefix='.accord-recovery-', dir=workspace) as tmp:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode): raise BackupError('Потрібен звичайний файл комплекту')
        directory = Path(tmp); total = 0; seen = set(); manifest = None
        try:
            with tarfile.open(fileobj=handle, mode='r|gz') as archive:
                for member in archive:
                    name = member.name
                    if name not in PAYLOADS | {'manifest.json'} or name in seen or not member.isfile():
                        raise BackupError('Недопустимий або повторний запис комплекту')
                    seen.add(name)
                    limit = {'manifest.json': MAX_MANIFEST, 'environment.env':256*1024,
                             'tls/origin.pem':512*1024, 'tls/origin.key':128*1024}.get(name, MAX_TOTAL)
                    if member.size > limit: raise BackupError('Файл комплекту завеликий')
                    total += member.size
                    if total > MAX_TOTAL: raise BackupError('Комплект перевищує 64 ГіБ')
                    path = directory/name; path.parent.mkdir(mode=0o700, exist_ok=True)
                    fd_out = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd_out, 'wb') as output, archive.extractfile(member) as entry:
                        shutil.copyfileobj(entry, output, 1024*1024)
                    if path.stat().st_size != member.size: raise BackupError('Обрізаний комплект')
            if 'manifest.json' not in seen: raise BackupError('Відсутній опис комплекту')
            manifest = json.loads((directory/'manifest.json').read_text())
            if (not isinstance(manifest, dict) or manifest.get('format') != 'accord-recovery' or manifest.get('version') != 1
                or not isinstance(manifest.get('files'), dict) or not isinstance(manifest.get('media'), dict)
                or set(manifest['files']) != seen - {'manifest.json'} or not REQUIRED <= manifest['files'].keys()
                or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,127}', str(manifest.get('project', '')))
                or manifest.get('project') in {'deploy', 'elfar'} or str(manifest.get('project','')).startswith('elfar-')):
                raise BackupError('Некоректний опис комплекту')
            if ('tls/origin.pem' in seen) != ('tls/origin.key' in seen): raise BackupError('Неповна пара TLS')
            for name, expected in manifest['files'].items():
                if file_digest(directory/name) != expected: raise BackupError('Контрольна сума комплекту не збігається')
            with (directory/'database.dump').open('rb') as dump:
                if dump.read(5) != SIGNATURE: raise BackupError('Некоректний формат дампа')
            values = parse_env(directory/'environment.env'); validate_domain_environment(values)
            if values.get('COMPOSE_PROJECT_NAME') != manifest['project']:
                raise BackupError('Namespace конфігурації не збігається з описом комплекту')
            if manifest.get('tls_included') != ('tls/origin.pem' in seen):
                raise BackupError('Некоректний опис TLS комплекту')
            if not isinstance(manifest.get('revision'), str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', manifest['revision']):
                raise BackupError('Некоректна ревізія комплекту')
            if inspect_media(directory/'media.tar') != manifest['media']:
                raise BackupError('Склад або контрольні суми медіа не збігаються')
            yield directory, manifest
        except (tarfile.TarError, EOFError, json.JSONDecodeError, UnicodeError, KeyError, TypeError, ValueError) as exc:
            raise BackupError('Пошкоджений або несумісний комплект відновлення') from None


def write_state(directory, row):
    if not re.fullmatch(r'[a-f0-9]{32}', row['id']): raise BackupError('Некоректний ID операції')
    path = directory/('.recovery-state-'+row['id']+'.json')
    with staging_file(directory) as temporary:
        with temporary.open('w') as output:
            json.dump(row, output, ensure_ascii=False); output.flush(); os.fsync(output.fileno())
        os.replace(temporary,path)
        fd = os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    return path


def recovery_states(directory):
    result=[]
    for path in directory.glob('.recovery-state-*.json'):
        if path.is_symlink() or path.stat().st_size>64*1024:continue
        try:row=json.loads(path.read_text())
        except (ValueError, OSError):continue
        if not isinstance(row,dict) or not isinstance(row.get('updated_at'),(int,float)):continue
        result.append({k:row.get(k) for k in ('id','operation','phase','project','writers','safety','result','updated_at')})
    return sorted(result,key=lambda row:row.get('updated_at') or 0,reverse=True)[:20]
