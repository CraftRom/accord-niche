#!/usr/bin/env python3
"""Remove retired shipped files left behind by extracting an update over old code."""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
RETIRED = (
    'scripts/setup_ip_test.py',
    'deploy/docker-compose.ip-test.yml',
    'deploy/nginx/accord-ip-dashboard.conf',
    'deploy/nginx/accord-ip-website.conf',
    'docs/IP_TEST_DEPLOY_UA.md',
    'ACCORD_NICHE_IP_TEST_RELEASE_UA.md',
    'ACCORD_NICHE_RELEASE_UA.md',
    'ACCORD_NICHE_FULL_SHOP_RELEASE_UA.md',
    'ACCORD_NICHE_DB_RECONCILIATION_v1.3_UA.md',
    'ACCORD_NICHE_3_DOMAINS_SECURITY_v1.4_UA.md',
    'ACCORD_DOMAIN_PP_UA.md',
    'website/reference-preview.html',
)

def main():
    count = 0
    for relative in RETIRED:
        target = ROOT / relative
        if not target.parent.resolve().is_relative_to(ROOT.resolve()):
            raise SystemExit('Refusing a path outside the ACCORD project')
        if target.is_file() or target.is_symlink():
            target.unlink()
            count += 1
    print(f'Прибрано застарілих файлів: {count}. Налаштування й дані збережені.')

if __name__ == '__main__':
    main()
