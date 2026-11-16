#!/usr/bin/env python3
"""Attach ACCORD to the observed ELFAR Docker edge, with an isolated certificate.

Run as root on the VPS after DNS is ready. Never changes ELFAR's .env or volumes.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.setup_domains import parse_env

HOSTS = ('accordniche.pp.ua', 'shop.accordniche.pp.ua', 'dashboard.accordniche.pp.ua')
DEFAULT_ORIGIN_DIR = Path('/etc/accord-niche/tls')
NETWORK = 'accord-shared-edge'
ORIGIN_MARKER = '# TLS provider: cloudflare-origin-ca\n'
MARKER = '# Managed by ACCORD NICHE shared-edge installer\n'
MOUNT = './nginx/accord-main.conf:/etc/nginx/conf.d/20-accord.conf:ro'


def patch_compose(text: str) -> str:
    """Edit only the known nginx block and add one external network; reject unknown layouts."""
    match = re.search(r'^  nginx:\n.*?(?=^  [A-Za-z0-9_-]+:|^\S|\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Не знайдено стандартний services.nginx у Compose ELFAR')
    block = match[0]
    if MOUNT not in block:
        if block.count('    volumes:\n') != 1:
            raise ValueError('Нестандартний список volumes у nginx; автоматичну зміну зупинено')
        block = block.replace('    volumes:\n', '    volumes:\n      - ' + MOUNT + '\n', 1)
    if '    networks: [internal, accord_edge]' not in block:
        if block.count('    networks: [internal]') != 1:
            raise ValueError('Нестандартні networks у nginx; автоматичну зміну зупинено')
        block = block.replace('    networks: [internal]', '    networks: [internal, accord_edge]', 1)
    result = text[:match.start()] + block + text[match.end():]
    networks = re.search(r'^networks:\n.*?(?=^\S|\Z)', result, re.M | re.S)
    if not networks:
        raise ValueError('Не знайдено кореневу секцію networks у Compose ELFAR')
    if re.search(r'^  accord_edge:', networks[0], re.M):
        if not re.search(r'^  accord_edge:\s*\n    external: true\s*\n    name: accord-shared-edge\s*$', networks[0], re.M):
            raise ValueError('Мережа accord_edge вже визначена інакше')
    else:
        addition = '  accord_edge:\n    external: true\n    name: accord-shared-edge\n'
        prefix = result[:networks.end()]
        result = prefix + ('' if prefix.endswith('\n') else '\n') + addition + result[networks.end():]
    return result


def bootstrap_config() -> str:
    return MARKER + '''server {
    listen 80;
    server_name accordniche.pp.ua shop.accordniche.pp.ua dashboard.accordniche.pp.ua;
    server_tokens off;
    include /etc/nginx/deny.d/*.conf;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type text/plain;
        try_files $uri =404;
    }
    location / { return 404; }
}
'''


def tls_config(cert_path=None, key_path=None) -> str:
    template = (ROOT / 'deploy/nginx/accord-elfar-docker-edge.conf.template').read_text()
    marker = MARKER + (ORIGIN_MARKER if cert_path else '')
    return marker + template.replace('__ACCORD_CERT__', cert_path or '/etc/letsencrypt/live/accordniche.pp.ua/fullchain.pem').replace('__ACCORD_KEY__', key_path or '/etc/letsencrypt/live/accordniche.pp.ua/privkey.pem')


def run(args, *, capture=False, cwd=None, timeout=None):
    proc = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, timeout=timeout)
    if proc.returncode:
        if capture and proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        raise RuntimeError('Команда завершилася помилкою: ' + ' '.join(args[:5]))
    return proc.stdout if capture else ''


def inspect_container(name):
    fmt = '{"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}}}'
    return json.loads(run(['docker', 'inspect', '--format', fmt, name], capture=True))


def validate_layout(nginx, certbot, elfar):
    labels = nginx['labels']
    if labels.get('com.docker.compose.project') != 'deploy':
        raise ValueError('Очікується чинний Compose project deploy для ELFAR')
    if labels.get('com.docker.compose.project.working_dir') != str(elfar):
        raise ValueError('Каталог ELFAR не збігається з live-контейнером')
    if labels.get('com.docker.compose.project.config_files') != str(elfar / 'docker-compose.prod.yml'):
        raise ValueError('Live Nginx використовує інший набір Compose файлів')
    for destination in ('/etc/letsencrypt', '/var/www/certbot'):
        sources = [{m['Source'] for m in c['mounts'] if m['Destination'] == destination} for c in (nginx, certbot)]
        if len(sources[0]) != 1 or sources[0] != sources[1]:
            raise ValueError('Nginx і Certbot не мають спільного тому: ' + destination)


def peer_certificate(host, *, verified, cafile=None):
    ctx = ssl.create_default_context(cafile=cafile) if verified else ssl._create_unverified_context()
    with socket.create_connection(('127.0.0.1', 443), timeout=5) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as conn:
            return conn.getpeercert(binary_form=True)


def check_local_http(host, *, cafile=None):
    ctx = ssl.create_default_context(cafile=cafile)
    with socket.create_connection(('127.0.0.1', 443), timeout=8) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as connection:
            request = f'GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'
            connection.sendall(request.encode('ascii'))
            with connection.makefile('rb') as stream:
                line = stream.readline(4096).decode('ascii', errors='replace')
            parts = line.split()
            if len(parts) < 2 or not parts[1].isdigit() or not 200 <= int(parts[1]) < 400:
                raise RuntimeError('Публічна сторінка ' + host + ' не готова: ' + line.strip())


def probe_http():
    token = secrets.token_hex(20)
    path = '/var/www/certbot/.well-known/acme-challenge/accord-' + token
    run(['docker', 'exec', 'deploy-certbot-1', 'sh', '-ec',
         'mkdir -p /var/www/certbot/.well-known/acme-challenge; printf "%s" "$1" > "$2"', 'sh', token, path])
    try:
        for host in HOSTS:
            try:
                with urlopen('http://' + host + '/.well-known/acme-challenge/accord-' + token, timeout=12) as response:
                    if response.read(1024).decode() != token:
                        raise ValueError('Інша відповідь на ACME probe')
            except Exception:
                raise RuntimeError('ACME HTTP недоступний для ' + host +
                    '. Перевірте DNS @/shop, тимчасовий DNS only, IPv6 і доступність порту 80.') from None
    finally:
        run(['docker', 'exec', 'deploy-certbot-1', 'rm', '-f', path])


def prepare_origin_roots(destination, source=None):
    """Use the shipped public roots, or an explicitly supplied local trust file."""
    source = source if source is not None else ROOT / 'deploy/tls/cloudflare-origin-ca.pem'
    if source.is_symlink() or not source.is_file():
        raise ValueError('Відсутній звичайний CA-файл ' + str(source) +
                         '; оновіть збірку або вкажіть локальний PEM через --origin-ca')
    with source.open('rb') as stream:
        data = stream.read(131073)
    if len(data) > 131072 or b'PRIVATE KEY' in data:
        raise ValueError('CA-файл має містити лише публічні PEM-сертифікати, до 128 KiB')
    # Load explicit local trust without calling load_default_certs().
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    existing_ca = context.cert_store_stats()['x509_ca']
    context.load_verify_locations(cadata=data.decode('ascii'))
    if context.cert_store_stats()['x509_ca'] <= existing_ca:
        raise ValueError('CA-файл не містить кореневих CA-сертифікатів')
    destination.write_bytes(data)


def validate_origin_files(cert, key, cafile):
    for path in (cert, key):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Потрібні звичайні PEM-файли сертифіката і приватного ключа')
    if key.stat().st_mode & 0o077:
        raise ValueError('Приватний ключ доступний іншим користувачам; встановіть chmod 600')
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key), password=b'')  # Match the pair; never prompt for a password.
    for host in HOSTS:
        try:
            run(['openssl', 'verify', '-CAfile', str(cafile), '-purpose', 'sslserver',
                 '-verify_hostname', host, str(cert)], capture=True)
        except RuntimeError as exc:
            raise ValueError('Origin CA не пройшов перевірку для ' + host +
                             '. Сертифікат має бути чинним і покривати accordniche.pp.ua та *.accordniche.pp.ua '
                             '(або всі три домени окремо).') from exc


def import_origin_files(cert, key):
    # Content-addressed storage preserves the old certificate/key for rollback.
    digest = hashlib.sha256(cert.read_bytes()).hexdigest()[:32]
    directory = '/etc/letsencrypt/accord-origin/' + digest
    run(['docker', 'exec', 'deploy-certbot-1', 'sh', '-ec', 'umask 077; mkdir -p "$1"', 'sh', directory])
    run(['docker', 'cp', str(cert), 'deploy-certbot-1:' + directory + '/origin.pem'])
    run(['docker', 'cp', str(key), 'deploy-certbot-1:' + directory + '/origin.key'])
    run(['docker', 'exec', 'deploy-certbot-1', 'chmod', '600', directory + '/origin.pem', directory + '/origin.key'])
    return directory + '/origin.pem', directory + '/origin.key'


def issue_certificate(email=''):
    args = ['docker', 'exec', 'deploy-certbot-1', 'certbot', 'certonly', '--non-interactive',
            '--agree-tos', '--webroot', '-w', '/var/www/certbot', '--cert-name', HOSTS[0],
            '--keep-until-expiring', '--expand']
    args += ['--email', email] if email else ['--register-unsafely-without-email']
    for host in HOSTS:
        args += ['-d', host]
    run(args, timeout=240)


def main(argv=None):
    parser = argparse.ArgumentParser(description='ACCORD + ELFAR: спільний Docker Nginx і окремий TLS')
    parser.add_argument('--elfar-dir', type=Path, default=Path('/opt/elfar/deploy'))
    parser.add_argument('--email', default='', help='Optional Let’s Encrypt contact email')
    parser.add_argument('--origin-cert', type=Path, help='Cloudflare Origin CA certificate (PEM)')
    parser.add_argument('--origin-key', type=Path, help='Matching private key, permissions 0600')
    parser.add_argument('--origin-ca', type=Path, help='Local trusted CA PEM; defaults to bundled Cloudflare RSA/ECC roots')
    args = parser.parse_args(argv)
    if args.origin_cert is None and args.origin_key is None and not args.email:
        default_cert, default_key = DEFAULT_ORIGIN_DIR / 'origin.pem', DEFAULT_ORIGIN_DIR / 'origin.key'
        if default_cert.exists() or default_key.exists():
            if not default_cert.is_file() or not default_key.is_file():
                parser.error('У /etc/accord-niche/tls потрібні обидва файли: origin.pem і origin.key')
            args.origin_cert, args.origin_key = default_cert, default_key
            print('Використовую наявний Origin CA із /etc/accord-niche/tls.', flush=True)
    if bool(args.origin_cert) != bool(args.origin_key):
        parser.error('--origin-cert і --origin-key потрібно вказати разом')
    origin_mode = args.origin_cert is not None
    if args.origin_ca is not None and not origin_mode:
        parser.error('--origin-ca використовується лише разом із --origin-cert і --origin-key')
    if origin_mode and args.email:
        parser.error('--email використовується лише для Let’s Encrypt')
    if os.geteuid() != 0:
        parser.error('Запустіть сценарій від root: він змінює лише nginx-конфігурацію ELFAR')
    elfar = args.elfar_dir.resolve()
    compose_path = elfar / 'docker-compose.prod.yml'
    edge_path = elfar / 'nginx/accord-main.conf'
    if compose_path.is_symlink() or edge_path.is_symlink():
        parser.error('Символічні посилання замість керованих конфігурацій не підтримуються')
    nginx = inspect_container('deploy-nginx-1')
    validate_layout(nginx, inspect_container('deploy-certbot-1'), elfar)
    for mount in nginx.get('mounts', []):
        if mount['Destination'] == '/etc/nginx/conf.d/20-accord.conf' and mount['Source'] != str(edge_path):
            parser.error('Mount 20-accord.conf уже використовується іншим файлом')
    values = parse_env(ROOT / '.env.domains')
    if values.get('COMPOSE_PROJECT_NAME') != 'accord-niche':
        parser.error('Очікується окремий COMPOSE_PROJECT_NAME=accord-niche; namespace ELFAR не змінюється')
    original = compose_path.read_text()
    patched = patch_compose(original)
    old_edge = edge_path.read_text() if edge_path.exists() else None
    if MOUNT in original and old_edge is None:
        parser.error('У Compose вже є mount ACCORD, але його файл відсутній; потрібне відновлення конфігурації')
    if old_edge and ORIGIN_MARKER in old_edge and not origin_mode:
        parser.error('Чинний TLS використовує Origin CA; вкажіть --origin-cert і --origin-key')
    if old_edge is not None and not old_edge.startswith(MARKER):
        parser.error('accord-main.conf уже існує й не належить цьому сценарію')
    active = run(['docker', 'exec', 'deploy-nginx-1', 'nginx', '-T'], capture=True)
    for section in re.split(r'# configuration file ', active):
        if re.search(r'server_name\s+[^;]*\baccordniche\.pp\.ua\b', section) and not section.startswith('/etc/nginx/conf.d/20-accord.conf:'):
            parser.error('Інший live-конфіг уже містить домен ACCORD; автоматичне підключення зупинено')
    before = hashlib.sha256(peer_certificate('elfar.pp.ua', verified=False)).hexdigest()
    backup = ROOT / '.edge-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(compose_path, backup / 'docker-compose.prod.yml')
    if edge_path.exists(): shutil.copy2(edge_path, backup / 'accord-main.conf')
    print('Резервна копія конфігурацій:', backup, flush=True)
    verification = {}
    selected_tls = None
    if origin_mode:
        ca_file = backup / 'cloudflare-origin-roots.pem'
        prepare_origin_roots(ca_file, args.origin_ca)
        validate_origin_files(args.origin_cert, args.origin_key, ca_file)
        cert_path, key_path = import_origin_files(args.origin_cert.resolve(), args.origin_key.resolve())
        selected_tls = tls_config(cert_path, key_path)
        verification = {'cafile': str(ca_file)}
    compose = ['docker', 'compose', '-p', 'deploy', '--env-file', str(elfar.parent / '.env'), '-f', str(compose_path)]
    # No build/pull or other ELFAR services are selected by the edge operation.
    restart = compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', 'nginx', 'promo-controller']
    changed = False
    live_changed = False
    recreated = False
    try:
        if subprocess.run(['docker', 'network', 'inspect', NETWORK], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            run(['docker', 'network', 'create', NETWORK])
        run(['bash', str(ROOT / 'deploy/domains.sh'), '--docker-edge', 'up', '-d', '--build'], cwd=ROOT)
        changed = True
        compose_path.write_text(patched)
        # Preserve the mounted inode when re-running after a completed installation.
        edge_path.write_text(selected_tls or (old_edge if old_edge and 'listen 443 ssl;' in old_edge else bootstrap_config()))
        run(compose + ['config', '--quiet'], cwd=elfar)
        run(compose + ['run', '--rm', '--no-deps', '--pull', 'never', 'nginx', 'nginx', '-t'], cwd=elfar)
        if patched != original or not old_edge:
            live_changed = True
            recreated = True
            run(restart, cwd=elfar)
            for attempt in range(15):
                try:
                    peer_certificate('elfar.pp.ua', verified=False)
                    break
                except OSError:
                    if attempt == 14: raise
                    time.sleep(1)
        if not origin_mode:
            probe_http()
            issue_certificate(args.email)
        edge_path.write_text(selected_tls or tls_config())
        run(['docker', 'exec', 'deploy-nginx-1', 'nginx', '-t'])
        live_changed = True
        run(['docker', 'exec', 'deploy-nginx-1', 'nginx', '-s', 'reload'])
        for attempt in range(8):
            try:
                for host in HOSTS: peer_certificate(host, verified=True, **verification)
                break
            except (OSError, ssl.SSLError):
                if attempt == 7: raise
                time.sleep(1)
        for host in HOSTS: check_local_http(host, **verification)
        # Certificate equality alone cannot detect a wrong Docker upstream.
        check_local_http('elfar.pp.ua')
        after = hashlib.sha256(peer_certificate('elfar.pp.ua', verified=False)).hexdigest()
        if before != after:
            raise RuntimeError('Сертифікат ELFAR змінився під час операції; потрібна перевірка')
        print('Готово: TLS і публічні сторінки ACCORD перевірено; сертифікат ELFAR збережений.')
        print('Магазин, Mini App і панель працюють через спільний HTTPS Nginx.')
        print('Залиште @, shop і dashboard у Proxied на цей VPS; SSL/TLS Cloudflare — Full (strict).')
        if origin_mode:
            print('Origin CA встановлено. Його заміна після закінчення строку виконується окремо від Certbot renew.')
        return 0
    except BaseException:
        if changed:
            compose_path.write_text(original)
            if old_edge is None: edge_path.unlink(missing_ok=True)
            else: edge_path.write_text(old_edge)
            if live_changed:
                print('Відновлюю попередню конфігурацію проксі ELFAR.', file=sys.stderr)
                try:
                    if recreated:
                        run(restart, cwd=elfar)
                    else:
                        run(['docker', 'exec', 'deploy-nginx-1', 'nginx', '-t'])
                        run(['docker', 'exec', 'deploy-nginx-1', 'nginx', '-s', 'reload'])
                except Exception: print('Автоматичний відкат не завершився; резервна копія: ' + str(backup), file=sys.stderr)
        raise


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print('ПОМИЛКА:', str(exc), file=sys.stderr)
        sys.exit(1)
