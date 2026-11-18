from pathlib import Path

root = Path(__file__).resolve().parents[2]
config = (root / 'backend/shop/config.py').read_text()
sd = (root / 'backend/shop/services/salesdrive.py').read_text()
env = (root / '.env.example').read_text()
compose = (root / 'deploy/docker-compose.domains.yml').read_text()
checks = {
    'панель має salesdrive_telegram_form_id': 'salesdrive_telegram_form_id: int | None' in (root / 'backend/api/schemas.py').read_text(),
    # ACCORD keeps its own database name from .env.domains; CRM never replaces it.
    'локальна БД лишилась власною': 'POSTGRES_DB=accord' in env and '${POSTGRES_DB:?Missing POSTGRES_DB}' in compose,
    'конфіг має form id': 'salesdrive_telegram_form_id: int = 0' in config,
    'відправка fail-closed без form id': 'Не вказано ID форми SalesDrive' in sd,
    'webhook звіряє formId': 'int(data.get("formId")) == expected' in sd,
    'webhook звіряє account': ('def _webhook_account_matches' in sd and 'expected_account = (shop.salesdrive_domain or "").strip().lower()' in sd and 'account == expected_account' in sd),
}
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items(): print(('✓' if ok else '✗'), name)
raise SystemExit(1 if failed else 0)
