# Розгортання ACCORD NICHE на accordniche.pp.ua

| Адреса | Сервіс | Внутрішній upstream |
| --- | --- | --- |
| `https://accordniche.pp.ua/` | Магазин, профіль, оформлення | `127.0.0.1:18081` |
| `https://shop.accordniche.pp.ua/` | Telegram Mini App | `127.0.0.1:18083` |
| `https://dashboard.accordniche.pp.ua/` | Панель через Cloudflare Tunnel + Access/MFA | `127.0.0.1:18082` |

IP-адреса VPS потрібна тільки в DNS та для SSH. Публічного запуску застосунку за IP немає. API, PostgreSQL та Redis не публікуються. Внутрішній HTTP працює за HTTPS edge, а панель доступна лише через захищений Tunnel.

## Перша інсталяція

Потрібні Python 3.11+, Docker Engine та Compose v2. Розпакуйте архів в окремий каталог `/opt/accord-niche`, не в каталог ELFAR:

```bash
cd /opt/accord-niche
umask 077
python3 scripts/setup_domains.py
bash deploy/domains.sh check
bash deploy/domains.sh up -d --build
bash deploy/domains.sh ps
```

Скрипт сам створює `.env.domains`: випадкові паролі PostgreSQL/Redis/панелі, JWT, Fernet і секрети webhook. Права — `0600`; секрети не виводяться в термінал. Повторний запуск не перезаписує файл. Новий стек має Compose namespace `accord-niche`.

Для входу логін `accordadmin`, пароль у полі `DASHBOARD_PASSWORD` файлу `.env.domains`. Відкривайте його через редактор на сервері; не публікуйте й не передавайте стороннім.

## Оновлення чинного ACCORD

1. Збережіть `.env.domains`, зробіть дамп PostgreSQL і копію медіа. За допомогою поточного Compose стека:

```bash
umask 077
bash deploy/domains.sh exec -T db sh -c \
 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "accord-backup-$(date +%F-%H%M).sql"
```

Якщо оновлений preflight ще не пропускає стару конфігурацію, зробіть резервну копію за допомогою попередньої встановленої версії до заміни файлів.

2. Розпакуйте нові вихідні файли поверх **тільки каталогу ACCORD**. Архів не містить реальних `.env` або даних БД. Приберіть старі файли з відомого списку:

```bash
python3 scripts/cleanup_legacy.py
```

Ця команда видаляє тільки перелічені застарілі скрипти/конфігурації/інструкції. Вона не видаляє env-файли, секрети, медіа чи Docker volumes.

3. У чинному `.env.domains` додайте або звірте:

```dotenv
DOMAIN_ONLY=true
PUBLIC_URL=https://shop.accordniche.pp.ua
DASHBOARD_PUBLIC_URL=https://dashboard.accordniche.pp.ua
TRUSTED_HOSTS=accordniche.pp.ua,shop.accordniche.pp.ua,dashboard.accordniche.pp.ua,localhost,127.0.0.1
CORS_ORIGINS=https://dashboard.accordniche.pp.ua
ENABLE_API_DOCS=false
MAIN_DOMAIN_ALIASES=
```

**COMPOSE_PROJECT_NAME має збігатися з назвою чинного стека.** Для попередньої збірки з цієї розмови це `accord-niche-test`. Додайте `COMPOSE_PROJECT_NAME=accord-niche-test`, якщо саме так запускався ваш ACCORD. Назва збережена тільки для доступу до існуючих томів; вона не вмикає жодного тестового режиму. Перевірити назви можна через `docker compose ls`. Для нової інсталяції генератор ставить `accord-niche`.

Не генеруйте новий ключ шифрування або паролі БД для вже наявних томів. Якщо немає `.env.domains`, але є чинний ACCORD env, імпортуйте його без створення нових секретів:

```bash
python3 scripts/setup_domains.py --source /absolute/path/to/current-accord.env
```

Імпорт відмовляється перезаписувати файл. Несумісні/слабкі значення потрібно виправити вручну. Мінімум: JWT — 32 символи, пароль панелі — 8, PostgreSQL/Redis — 24; Fernet — чинний ключ із 32 байтів. Для вже налаштованих БД зміну пароля треба узгодити з реальною БД, одного редагування env недостатньо.

```bash
chmod 600 .env.domains
bash deploy/domains.sh check
bash deploy/domains.sh up -d --build
```

Не використовуйте `down -v`. Сценарій `deploy/domains.sh` блокує видалення томів і підміну Compose файлів/namespace через аргументи.

## DNS і HTTPS edge

Для `@` та `shop` створіть A-записи на фактичну IPv4-адресу VPS. AAAA використовуйте лише за наявності справного IPv6. Спершу перевірте власника портів:

```bash
sudo ss -ltnp '( sport = :80 or sport = :443 )'
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Не запускайте ще один публічний Nginx на зайнятих портах.

**Якщо 80/443 обслуговує системний Nginx:** використовуйте `deploy/nginx/accord-public-edge.conf.template`. Замініть `__ACCORD_CERT__` і `__ACCORD_KEY__` фактичними шляхами чинного сертифіката з SAN для `accordniche.pp.ua` та `shop.accordniche.pp.ua`. Підключіть отриманий конфіг окремим файлом; перед reload виконайте `nginx -t`. Зберігайте резервну копію чинного конфіга.

**Якщо 80/443 обслуговує Nginx у Docker ELFAR:** створіть зовнішню мережу `accord-shared-edge` один раз, додайте до неї тільки чинний ELFAR Nginx через його Compose конфіг. Для ACCORD запускайте:

```bash
docker network inspect accord-shared-edge >/dev/null 2>&1 || docker network create accord-shared-edge
bash deploy/domains.sh --docker-edge up -d --build
```

Змонтуйте в edge конфіг із `deploy/nginx/accord-elfar-docker-edge.conf.template` після підстановки шляхів сертифіката. Він використовує DNS aliases `accord-website` і `accord-miniapp`. `dashboard`, API, PostgreSQL і Redis до edge-мережі не підключайте. Надалі використовуйте `--docker-edge` при кожному запуску/оновленні цього варіанта.

Обидва шаблони містять редирект HTTP → HTTPS. За Cloudflare використовуйте Full (strict) із чинним сертифікатом origin. Не відкривайте порти 18081–18083 в інтернет.

## Панель

Cloudflare Tunnel для `dashboard.accordniche.pp.ua` направте на `http://127.0.0.1:18082`, якщо cloudflared встановлений на хості. Якщо cloudflared працює в окремому контейнері, його `127.0.0.1` не є loopback VPS — мережеве підключення треба налаштувати окремо. Додайте Cloudflare Access із доступом тільки для адміністраторів та обов'язковим MFA; перевірте перевірку Access на Tunnel. Публічного vhost панелі у шаблонах немає.

Cookies сесій панелі та магазину окремі, HttpOnly/Secure, без спільного Domain. Запити панелі приймаються тільки зі свого Origin. Невідомі хости відхиляються і в Nginx, і на межі API; локальні API health checks залишені.

## Додаткові інтеграції

- Google: задайте `ACCORD_GOOGLE_CLIENT_ID`; дозволений JavaScript origin — `https://accordniche.pp.ua`.
- Telegram: використовуйте власні `BOT_TOKEN`/`BOT_USERNAME`, Web App URL — `https://shop.accordniche.pp.ua/`. `ACCORD_MINIAPP_URL` має бути справжнім `https://t.me/<bot>/<app>`.
- `PUBLIC_URL` — Telegram/webhook origin, тому вказує на `shop`, а не на корінь магазину. Якщо адреса вже збережена в налаштуваннях БД через панель, оновіть її там також.
- Бот: `bash deploy/domains.sh --profile bot up -d --build`.
- Планувальник і налаштовані резервні копії: `bash deploy/domains.sh --profile workers up -d --build`.

## Перевірка після запуску

```bash
bash deploy/domains.sh ps
bash deploy/domains.sh logs --tail=100 api migrate
curl -sI https://accordniche.pp.ua/
curl -sI https://shop.accordniche.pp.ua/
curl -sI https://dashboard.accordniche.pp.ua/
curl -si https://accordniche.pp.ua/api/auth/session
curl -si https://shop.accordniche.pp.ua/api/orders
```

Без сесії Access панель має спрямовувати на автентифікацію. Два останні API запити мають повертати 404. Окремо перевірте checkout, логін/вихід, відновлення бекапу й неможливість прямого доступу до локальних портів із зовнішньої мережі.
