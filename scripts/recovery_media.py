"""Executed in a scoped ephemeral container without network, on the ACCORD volume.
The host passes this source via python -c; it also runs unchanged in QA.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tarfile


def checked(name):
    if (not name or len(name)>512 or name.startswith('/') or '\\' in name
        or any(p in {'', '.', '..'} for p in name.split('/')) or any(ord(c)<32 for c in name)):
        raise ValueError('Unsafe media path')
    return name


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def export(root, output):
    source = root/'media'
    if source.is_symlink() or not source.is_dir(): raise ValueError('Missing regular media directory')
    with tarfile.open(fileobj=output, mode='w|', dereference=False) as archive:
        for parent, dirs, files in os.walk(source, followlinks=False):
            for name in sorted(dirs+files):
                path = Path(parent)/name
                mode = path.lstat().st_mode
                if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)): raise ValueError('Special media file')
                relative = checked(path.relative_to(source).as_posix())
                archive.add(path, arcname=relative, recursive=False)


def stage(root, token, source):
    target = root/('.accord-media-stage-'+token)
    target.mkdir(mode=0o700)
    result = {}; seen = set(); total = 0
    try:
        with tarfile.open(fileobj=source, mode='r|') as archive:
            for member in archive:
                name = checked(member.name)
                if name in seen or len(seen)>=100000: raise ValueError('Duplicate or excessive media')
                seen.add(name); path = target/name
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if member.isdir(): path.mkdir(mode=0o755, exist_ok=True); continue
                if not member.isfile() or member.size > 1024**3: raise ValueError('Special or oversized media file')
                total += member.size
                if total>64*1024**3: raise ValueError('Excessive media size')
                h = hashlib.sha256(); size = 0
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
                with os.fdopen(fd, 'wb') as output, archive.extractfile(member) as entry:
                    while chunk := entry.read(1024*1024):
                        h.update(chunk); size += len(chunk); output.write(chunk)
                    output.flush(); os.fsync(output.fileno())
                os.chmod(path, 0o644)
                if size != member.size: raise ValueError('Truncated media file')
                result[name] = {'size':size, 'sha256':h.hexdigest()}
        # Make the complete staged tree readable by the frontend Nginx workers.
        for parent, dirs, files in os.walk(target, topdown=False):
            os.chmod(parent, 0o755); fsync_dir(parent)
        fsync_dir(root)
        return result
    except BaseException:
        shutil.rmtree(target)
        raise


def commit(root, token):
    stage_path = root/('.accord-media-stage-'+token)
    old = root/('.accord-media-old-'+token); live = root/'media'
    if stage_path.is_symlink() or not stage_path.is_dir() or live.is_symlink() or not live.is_dir() or old.exists():
        raise ValueError('Invalid media swap state')
    os.rename(live, old)
    try: os.rename(stage_path, live)
    except BaseException:
        os.rename(old, live); raise
    fsync_dir(root)


def cleanup(root, token, kind):
    target = root/('.accord-media-'+kind+'-'+token)
    if target.is_symlink(): raise ValueError('Refusing linked cleanup target')
    if target.exists(): shutil.rmtree(target); fsync_dir(root)


def main():
    operation, token = sys.argv[1:]
    if not re.fullmatch(r'[a-f0-9]{32}', token): raise ValueError('Invalid operation token')
    root = Path('/data')
    if operation == 'export': export(root, sys.stdout.buffer)
    elif operation == 'stage': print(json.dumps(stage(root, token, sys.stdin.buffer)))
    elif operation == 'commit': commit(root, token)
    elif operation in {'cleanup-stage', 'cleanup-old'}: cleanup(root, token, operation.split('-')[1])
    else: raise ValueError('Invalid operation')


if __name__ == '__main__': main()
