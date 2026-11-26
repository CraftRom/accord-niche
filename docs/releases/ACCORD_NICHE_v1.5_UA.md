# ACCORD NICHE v1.5 — доменне розгортання та захист

Адреси: https://accordniche.pp.ua/, https://shop.accordniche.pp.ua/, https://dashboard.accordniche.pp.ua/.

## Зміни

- Вилучено підготовку/Compose/Nginx запуску за зовнішньою IP-адресою, застарілі інструкції та статичний демонстраційний макет. Список видаленого коду використовується тільки в scripts/cleanup_legacy.py для оновлення старої інсталяції.
- setup_domains.py самостійно створює .env.domains зі стійкими випадковими секретами (PostgreSQL, Redis, JWT, пароль панелі, Fernet, webhook/cron). Повторний запуск перевіряє файл без ротації секретів. Явний імпорт чинного env зберігає ключі та namespace БД.
- Перевірки перед записом, права 0600, відмова від symlink/перезапису, буквальне збереження спецсимволів без Compose-інтерполяції.
- deploy/domains.sh перевіряє конфігурацію, прибирає вплив змінних shell на паролі/namespace/порти, не виконує env як shell-код, блокує підміну Compose файлів і видалення томів.
- DOMAIN_ONLY вмикає перевірку HTTPS origins, точних Host/CORS, прихованої API-документації, секретів та локальних DB/Redis адрес при старті API.
- Nginx відхиляє невідомі Host, зокрема зовнішній IP; API окремо відхиляє невідомі API-хости. Локальні API health checks залишені.
- Панель завжди використовує Secure cookies за HTTPS dashboard origin; додано no-store для її відповідей. Telegram menu у доменному режимі відкриває корінь shop.
- Кореневий Compose підключає доменний стек замість старого запуску з публічним портом панелі 80. Доменні listeners залишаються на loopback; API/БД/Redis не мають host ports.
- Прибрано застарілий README і зайві параметри з доменного env-шаблону. Реальні env, кеші й VCS виключені з Docker build contexts. Відновлено executable permissions shell-сценаріїв. Доменні тести включені в CI.

## Перевірки

88 Python-тестів пройдено: налаштування/імпорт, сесії та межі API, сайт/ідентичності, сумісність попередніх доменних функцій і Telegram. 6 Node-тестів каталогу пройдено. Production build магазину з WEBSITE_BASE=/ пройшов. compileall, bash -n та розбір YAML пройшли.

Реальні Docker startup, nginx -t, зовнішні DNS/TLS і Cloudflare Access тут не перевірялися: Docker і Nginx відсутні в середовищі. Тести deploy використовують ізольований Docker stub, а не демон. Налаштування VPS та зовнішніх сервісів цим архівом автоматично не змінені.

## Запуск

Для нової інсталяції:

```bash
python3 scripts/setup_domains.py
bash deploy/domains.sh up -d --build
```

Для оновлення спершу прочитайте README.md та docs/ACCORD_3_DOMAINS_SECURITY_UA.md: збережіть секрети/дані, встановіть DOMAIN_ONLY=true і правильний COMPOSE_PROJECT_NAME чинного стека. Видалені файли з попередньої версії прибирає python3 scripts/cleanup_legacy.py.
