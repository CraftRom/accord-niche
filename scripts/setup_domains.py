#!/usr/bin/env python3
"""Create or validate the HTTPS-only ACCORD environment without a staging step."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from shop.domain_security import DOMAIN, HOSTS, ORIGINS, validate_domain_environment


def parse_env(path: Path) -> dict[str, str]:
    result = {}
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key in result:
            raise ValueError(f'Некоректна або повторна змінна, рядок {number}')
        if value.startswith("'"):
            match = re.fullmatch(r"'((?:\\'|[^'])*)'\s*(?:#.*)?", value)
            if not match:
                raise ValueError(f'Некоректні лапки: {key}')
            value = match[1].replace("\\'", "'")
        elif value.startswith('"'):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                raise ValueError(f'Некоректні подвійні лапки: {key}') from None
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
            if '$' in value:
                raise ValueError(f'{key}: значення з $ потрібно взяти в одинарні лапки')
        result[key] = value
    return result


def serialize(values: dict[str, str]) -> str:
    # Literal single-quoted dotenv values prevent Compose $ interpolation.
    return ''.join(key + "='" + value.replace("'", "\\'") + "'\n" for key, value in values.items())


def fresh_environment() -> dict[str, str]:
    redis_password = secrets.token_hex(32)
    return {
        'COMPOSE_PROJECT_NAME': 'accord-niche',
        'POSTGRES_USER': 'accord', 'POSTGRES_DB': 'accord',
        'POSTGRES_PASSWORD': secrets.token_hex(32),
        'REDIS_PASSWORD': redis_password,
        'REDIS_URL': f'redis://:{redis_password}@redis:6379/0',
        'JWT_SECRET': secrets.token_hex(48),
        'DATA_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'DASHBOARD_LOGIN': 'accordadmin', 'DASHBOARD_PASSWORD': secrets.token_urlsafe(32),
        'JWT_TTL_HOURS': '8', 'DASHBOARD_IDLE_MINUTES': '30',
        'LOGIN_MAX_ATTEMPTS': '5', 'LOGIN_LOCK_MINUTES': '15',
        'WEBHOOK_SECRET': secrets.token_urlsafe(32), 'CRON_SECRET': secrets.token_urlsafe(32),
        'SHOP_NAME': 'ACCORD NICHE', 'BOT_TOKEN': '', 'BOT_USERNAME': '',
        'ADMIN_CHAT_ID': '0', 'ADMIN_IDS': '', 'OPTIONAL_TELEGRAM': 'true',
        'ACCORD_MINIAPP_URL': '', 'MINIAPP_SHORT_NAME': '',
        'ACCORD_GOOGLE_CLIENT_ID': '', 'ACCORD_TWILIO_ACCOUNT_SID': '',
        'ACCORD_TWILIO_AUTH_TOKEN': '', 'ACCORD_TWILIO_VERIFY_SERVICE_SID': '',
        'ACCORD_INSTAGRAM_URL': '', 'ACCORD_TIKTOK_URL': '', 'ACCORD_PHONE': '',
        'SALESDRIVE_ENABLED': 'false', 'AUTO_REPLIES_ENABLED': 'false',
        'REFERRAL_ENABLED': 'false', 'LOG_JSON': '1',
        'ACCORD_SITE_PORT': '18081', 'ACCORD_DASHBOARD_PORT': '18082', 'ACCORD_MINIAPP_PORT': '18083',
    }


def check(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError('Файл налаштувань відсутній або є символічним посиланням')
    if path.stat().st_mode & 0o077:
        raise ValueError('Налаштування доступні іншим користувачам; виконайте chmod 600 для файлу')
    validate_domain_environment(parse_env(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'ACCORD NICHE — HTTPS на {DOMAIN}')
    parser.add_argument('--source', help='Optional existing ACCORD environment; preserve its secrets')
    parser.add_argument('--output', default='.env.domains')
    parser.add_argument('--check', action='store_true', help='Validate without changing any file')
    args = parser.parse_args(argv)
    output = ROOT / args.output
    try:
        if args.check:
            if args.source:
                raise ValueError('--source не використовується разом із --check')
            check(output)
            print('Доменна конфігурація: OK; секрети приховані.')
            return 0
        if output.exists() or output.is_symlink():
            if args.source:
                raise ValueError('Вихідний файл вже існує; імпорт не може його перезаписати')
            check(output)
            print('Конфігурація вже існує та перевірена. Секрети й БД не змінені.')
            return 0
        values = parse_env(ROOT / args.source) if args.source else fresh_environment()
        for retired in ('ACCORD_SITE_BIND', 'ACCORD_DASHBOARD_BIND', 'ACCORD_MINIAPP_BIND'):
            values.pop(retired, None)
        # A source import never generates replacement database/authentication secrets.
        values.update(ORIGINS)
        values.update({'DOMAIN_ONLY': 'true', 'ENABLE_API_DOCS': 'false',
                       'MAIN_DOMAIN_ALIASES': '', 'TRUSTED_HOSTS': ','.join(sorted(HOSTS))})
        if 'REDIS_URL' not in values and values.get('REDIS_PASSWORD'):
            values['REDIS_URL'] = 'redis://:' + quote(values['REDIS_PASSWORD'], safe='') + '@redis:6379/0'
        if args.source:
            # Keep the historical volume namespace unless the operator specifies the existing one.
            values.setdefault('COMPOSE_PROJECT_NAME', 'accord-niche-test')
        validate_domain_environment(values)
        content = serialize(values)  # Complete validation happens before any write.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(output, flags, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            output.unlink(missing_ok=True)
            raise
        print('Створено', output, '(0600). Секрети збережено лише у файлі.')
        print('Магазин: https://' + DOMAIN)
        print('Mini App: https://shop.' + DOMAIN)
        print('Панель: https://dashboard.' + DOMAIN)
        print('Запуск: bash deploy/domains.sh up -d --build')
        return 0
    except (ValueError, OSError):
        # OSError may include sensitive path components; errors never print file contents.
        error = sys.exception()
        parser.error(str(error) if isinstance(error, ValueError) else 'Помилка доступу або запису файлу налаштувань')


if __name__ == '__main__':
    sys.exit(main())
