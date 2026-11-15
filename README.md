# ACCORD NICHE

Публічний магазин: **https://accordniche.pp.ua/**. Telegram Mini App: **https://shop.accordniche.pp.ua/**. Панель: **https://dashboard.accordniche.pp.ua/**.

## Перший запуск

Потрібні Python 3.11+, Docker Engine та Compose v2. У каталозі ACCORD:

```bash
python3 scripts/setup_domains.py
bash deploy/domains.sh check
bash deploy/domains.sh up -d --build
bash deploy/domains.sh ps
```

Генератор створює `.env.domains` із випадковими секретами та правами `0600`. Повторний запуск лише перевіряє файл. Пароль `accordadmin` зберігається у `DASHBOARD_PASSWORD`; відкрийте файл локально через редактор, не надсилайте його в чат.

Compose запускає PostgreSQL, Redis, міграції, API, магазин, Mini App і панель. Зовнішні адреси потребують DNS, HTTPS edge та Cloudflare Tunnel/Access для панелі. **Підняття контейнерів саме по собі не налаштовує DNS і сертифікати.**

## Оновлення

Зробіть резервну копію поточної бази та медіа. Розпакуйте архів у каталог ACCORD, зберігши `.env.domains`. Приберіть вилучені з проєкту файли:

```bash
python3 scripts/cleanup_legacy.py
bash deploy/domains.sh check
bash deploy/domains.sh up -d --build
```

Збережіть назву Compose проєкту, поточні паролі та ключ шифрування. Не видаляйте томи. Для імпорту наявного ACCORD env у **ще не створений** `.env.domains`:

```bash
python3 scripts/setup_domains.py --source /absolute/path/to/current-accord.env
```

Подробиці налаштувань, збереження томів і підключення доменів: [інструкція розгортання](docs/ACCORD_3_DOMAINS_SECURITY_UA.md).

## Журнали та додаткові сервіси

```bash
bash deploy/domains.sh logs --tail=100 api migrate
# Після заповнення власного BOT_TOKEN:
bash deploy/domains.sh --profile bot up -d --build
# Фонові завдання та резервні копії за розкладом:
bash deploy/domains.sh --profile workers up -d --build
```

Для edge Nginx у Docker використовуйте `bash deploy/domains.sh --docker-edge ...` після підключення мережі за інструкцією. Публічні порти контейнерів залишаються прив'язаними до loopback.

## Системні групи

- **Системний адміністратор** — усі розділи, інфраструктура й керування адміністративними обліковими записами.
- **Адміністратор** — модулі, налаштування магазину, продажі та облікові записи менеджерів.
- **Менеджер** — клієнти й продажі; читання/зміна налаштувань і керування доступом закриті.

Матриця доступу та оновлення: [docs/SYSTEM_GROUPS_UA.md](docs/SYSTEM_GROUPS_UA.md).

## Перевірки

```bash
PYTHONPATH=backend python3 -m pytest backend/tests_accord backend/qa/qa_accord_domain_split.py -q
node --test website/tests/*.test.mjs dashboard/tests/roles.mjs
```

`docker-compose.yml` тепер підключає той самий доменний стек (для цього entrypoint потрібен Compose 2.20+). Для ACCORD використовуйте `deploy/domains.sh`: він перевіряє конфігурацію та блокує видалення томів. `deploy/docker-compose.prod.yml` належить попередній спільній інфраструктурі; доменний сценарій його не використовує.
