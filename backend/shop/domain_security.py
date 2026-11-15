"""Domain deployment policy, shared by the host preflight and API startup.

Standard library only. Validation errors name keys, never credential values.
"""
from __future__ import annotations
import base64
import re
from urllib.parse import unquote, urlsplit

DOMAIN = 'accordniche.pp.ua'
ORIGINS = {
    'PUBLIC_URL': f'https://shop.{DOMAIN}',
    'DASHBOARD_PUBLIC_URL': f'https://dashboard.{DOMAIN}',
    'CORS_ORIGINS': f'https://dashboard.{DOMAIN}',
}
HOSTS = {DOMAIN, f'shop.{DOMAIN}', f'dashboard.{DOMAIN}', 'localhost', '127.0.0.1'}


def validate_domain_environment(values: dict[str, str]) -> None:
    errors = []
    for key, expected in ORIGINS.items():
        actual = values.get(key, '')
        if (actual if key == 'CORS_ORIGINS' else actual.rstrip('/')) != expected:
            errors.append(key)
    hosts = {v.strip().lower() for v in values.get('TRUSTED_HOSTS', '').split(',') if v.strip()}
    if hosts != HOSTS:
        errors.append('TRUSTED_HOSTS')
    if values.get('ENABLE_API_DOCS', '').lower() not in ('false', '0'):
        errors.append('ENABLE_API_DOCS')
    if values.get('DOMAIN_ONLY', '').lower() not in ('true', '1'):
        errors.append('DOMAIN_ONLY')
    if values.get('MAIN_DOMAIN_ALIASES', '').strip():
        errors.append('MAIN_DOMAIN_ALIASES')
    for key, minimum in [('JWT_SECRET', 32), ('DASHBOARD_PASSWORD', 8),
                         ('POSTGRES_PASSWORD', 24), ('REDIS_PASSWORD', 24)]:
        value = values.get(key, '')
        if len(value) < minimum or value.lower().startswith(('change', 'your_', 'example', 'test', 'generate_', 'placeholder')):
            errors.append(key)
    if values.get('POSTGRES_HOST', 'db') != 'db':
        errors.append('POSTGRES_HOST')
    if str(values.get('POSTGRES_PORT', '5432')) != '5432':
        errors.append('POSTGRES_PORT')
    for key in ('POSTGRES_USER', 'POSTGRES_DB'):
        if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', values.get(key, '')):
            errors.append(key)
    try:
        key = values.get('DATA_ENCRYPTION_KEY', '')
        if len(key) != 44 or len(base64.b64decode(key, altchars=b'-_', validate=True)) != 32:
            raise ValueError
    except (ValueError, TypeError):
        errors.append('DATA_ENCRYPTION_KEY')
    project = values.get('COMPOSE_PROJECT_NAME', 'accord-niche-test')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', project):
        errors.append('COMPOSE_PROJECT_NAME')
    ports = []
    for key, default in [('ACCORD_SITE_PORT', '18081'), ('ACCORD_DASHBOARD_PORT', '18082'),
                         ('ACCORD_MINIAPP_PORT', '18083')]:
        try:
            port = int(values.get(key, default))
            if not 1024 <= port <= 65535:
                raise ValueError
            ports.append(port)
        except ValueError:
            errors.append(key)
    if len(set(ports)) != len(ports):
        errors.append('ACCORD_*_PORT (duplicates)')
    for key, host, port, user, password, database in [
        ('DATABASE_URL', 'db', 5432, values.get('POSTGRES_USER'), values.get('POSTGRES_PASSWORD'), values.get('POSTGRES_DB')),
        ('REDIS_URL', 'redis', 6379, None, values.get('REDIS_PASSWORD'), '0'),
    ]:
        raw = values.get(key, '')
        if not raw and key == 'DATABASE_URL':
            continue  # The backend derives DATABASE_URL from POSTGRES_*.
        try:
            url = urlsplit(raw)
            expected_scheme = 'postgresql+asyncpg' if key == 'DATABASE_URL' else 'redis'
            if (url.scheme != expected_scheme or url.hostname != host or url.port not in (None, port)
                    or unquote(url.password or '') != password or unquote(url.path.lstrip('/')) != database
                    or (user is not None and unquote(url.username or '') != user)
                    or url.query or url.fragment):
                raise ValueError
        except ValueError:
            errors.append(key)
    # All values must be representable in the single-line dotenv format.
    for key, value in values.items():
        if any(ord(c) < 32 or ord(c) == 127 for c in str(value)):
            errors.append(key)
    if errors:
        raise ValueError('Небезпечна або несумісна конфігурація: ' + ', '.join(dict.fromkeys(errors)))
