#!/usr/bin/env python3
"""Migrate only stateless ACCORD frontends to namespaced Compose service names.

Old service names register implicit Docker DNS aliases that collide with ELFAR.
Never stops database/API containers and never deletes volumes or user files.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.setup_domains import parse_env

FRONTENDS = ('website', 'miniapp', 'dashboard')


def run(args, capture=False):
    result = subprocess.run(args, text=True, capture_output=capture)
    if result.returncode:
        raise RuntimeError('Не вдалося виконати: ' + ' '.join(args[:3]))
    return result.stdout if capture else ''


def migrate(*, edge=False, build=False):
    project = parse_env(ROOT / '.env.domains').get('COMPOSE_PROJECT_NAME', 'accord-niche-test')
    if project == 'deploy':
        raise ValueError('Namespace ELFAR deploy не можна використовувати для ACCORD')
    old_ids = []
    allowed = {str(ROOT / 'deploy/docker-compose.domains.yml'), str(ROOT / 'deploy/docker-compose.edge-network.yml')}
    for service in FRONTENDS:
        ids = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project,
                   '--filter', 'label=com.docker.compose.service=' + service], capture=True).split()
        for cid in ids:
            raw = run(['docker', 'inspect', '--format',
                       '{"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}}}', cid], capture=True)
            item = json.loads(raw)
            labels = item['labels']
            files = set(labels.get('com.docker.compose.project.config_files', '').split(','))
            if (labels.get('com.docker.compose.project') != project or
                    labels.get('com.docker.compose.service') != service or
                    str(ROOT / 'deploy/docker-compose.domains.yml') not in files or not files <= allowed):
                raise ValueError('Невідомий контейнер; автоматичну міграцію frontend зупинено')
            if any(m.get('RW') and m.get('Type') == 'volume' and
                   m.get('Destination') not in ('/var/cache/nginx', '/var/run', '/tmp') for m in item.get('mounts', [])):
                raise ValueError('Frontend має writable data volume; автоматичне видалення заборонено')
            old_ids.append(cid)
    if not old_ids:
        return
    compose = ['docker', 'compose', '--env-file', str(ROOT / '.env.domains'),
               '-f', str(ROOT / 'deploy/docker-compose.domains.yml')]
    if edge:
        compose += ['-f', str(ROOT / 'deploy/docker-compose.edge-network.yml')]
    # Build successfully before releasing the old listeners. The old image tags
    # are preserved, so callers explicitly using --no-build can reuse them.
    if build:
        run(compose + ['build'])
    else:
        for service in FRONTENDS:
            run(['docker', 'image', 'inspect', '--format', '{{.Id}}', project + '-' + service], capture=True)
    print('Міграція трьох frontend ACCORD на окремі Docker-імена; дані та ELFAR збережені.', flush=True)
    run(['docker', 'stop', *old_ids])
    run(['docker', 'rm', *old_ids])


if __name__ == '__main__':
    try:
        migrate(edge=sys.argv[1:2] == ['1'], build='--build' in sys.argv[2:])
    except (ValueError, RuntimeError, OSError) as exc:
        print('ПОМИЛКА:', exc, file=sys.stderr)
        sys.exit(1)
