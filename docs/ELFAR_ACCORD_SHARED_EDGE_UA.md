# ELFAR і ACCORD паралельно на VPS

Сценарій підготовлено для підтвердженої конфігурації:

- ELFAR: Compose project `deploy`, `/opt/elfar/deploy/docker-compose.prod.yml`.
- Публічний проксі: `deploy-nginx-1`, порти 80/443.
- Certbot: `deploy-certbot-1`, спільні з Nginx томи `/etc/letsencrypt` і `/var/www/certbot`.
- ACCORD: `/opt/accord-niche`, `COMPOSE_PROJECT_NAME='accord-niche'`.

Використовуйте v1.8.1 або новішу: frontend-сервіси ACCORD мають імена `accord-website`, `accord-miniapp`, `accord-dashboard`. Це запобігає конфлікту з неявними Docker DNS aliases ELFAR. При оновленні `domains.sh` одноразово замінює тільки старі frontend-контейнери ACCORD, зберігаючи дані; подробиці — [v1.8.1](../ACCORD_NICHE_v1.8.1_UA.md).

## Простий запуск із наявним Origin CA

Оновіть файли проєкту зі збірки v1.7.0, збережіть `.env.domains` і `/etc/accord-niche/tls`. Від root:

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py
```

Наявні `origin.pem` і `origin.key` беруться автоматично. Сценарій збирає та запускає ACCORD і налаштовує всі три домени у чинному HTTPS Nginx: магазин, Mini App та dashboard. Вхід у dashboard використовує наявні облікові записи. Tunnel для цього не потрібний.

Для Origin CA DNS `@`, `shop`, `dashboard` має вести на VPS у Proxied; SSL/TLS — Full (strict). Стандартний сертифікат Cloudflare з коренем та `*.accordniche.pp.ua` підходить. Якщо використано окремий список SAN без wildcard, у ньому мають бути всі три домени; скрипт перевіряє це до зміни Nginx.

## Уже створений Cloudflare Origin CA

Для цього способу DNS-записи ACCORD `@`, `shop` і `dashboard` залишаються **Proxied**, SSL/TLS — **Full (strict)**. Origin CA перевіряє Cloudflare; у звичайному прямому підключенні браузер не довіряє цьому CA. Сертифікат повинен містити корінь і `*.accordniche.pp.ua`, або всі три домени: корінь, shop і dashboard.

Встановіть збірку v1.7.0 або новішу зі збереженням `.env.domains`. Від root створіть файли поза Git:

```bash
umask 077
install -d -m 700 /etc/accord-niche/tls
nano /etc/accord-niche/tls/origin.pem
nano /etc/accord-niche/tls/origin.key
chmod 600 /etc/accord-niche/tls/origin.pem /etc/accord-niche/tls/origin.key
```

У `origin.pem` вставте **повний Origin Certificate**, включно з BEGIN/END CERTIFICATE. У `origin.key` — **повний Private Key**, включно з BEGIN/END PRIVATE KEY. Користуйтеся кнопкою копіювання Cloudflare; приватний ключ зберігається тільки на вашому сервері.

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py \
  --origin-cert /etc/accord-niche/tls/origin.pem \
  --origin-key /etc/accord-niche/tls/origin.key
```

Сценарій використовує офіційні публічні RSA/ECC кореневі CA, включені до збірки у `deploy/tls/cloudflare-origin-ca.pem`. Завантаження CA із сайту Cloudflare під час встановлення не виконується. Перед зміною проксі перевіряє пару cert/key, строк дії, ланцюжок і усі три hostname. Потім копіює пару в окремий каталог `accord-origin/<digest>` спільного TLS-тома Nginx/Certbot; файли ELFAR та попередні пари не перезаписуються. Certbot issuance і HTTP-01 probe у цьому режимі не виконуються. Локальна перевірка TLS використовує явний trust bundle Origin CA із перевіркою hostname; глобальне системне сховище CA не змінюється.

### Якщо попередній запуск повернув HTTP Error 403

У v1.6.3 запит до сайту документації Cloudflare міг отримати 403 під час завантаження CA. На цьому етапі конфігурація Nginx ще не змінювалася. Із v1.6.4 цей зовнішній запит видалено.

Для виправлення достатньо оновити два файли зі збірки в `/opt/accord-niche`: `scripts/connect_elfar_edge.py` та `deploy/tls/cloudflare-origin-ca.pem` (створіть каталог `deploy/tls`, якщо його немає). Збережіть наявний `.env.domains` і файли `/etc/accord-niche/tls/origin.pem`, `origin.key`. Повторіть ту саму команду з `--origin-cert` та `--origin-key`. Відкат через цю помилку не потрібний.

За потреби можна передати власну локальну копію довірених Cloudflare Origin CA через `--origin-ca /path/to/cloudflare-origin-ca.pem`. Це файл **кореневих публічних CA**, а не ваш серверний `origin.pem` і не приватний ключ. Невідомим CA-файлам довіряти не слід. Без цього аргумента використовується файл зі збірки; системне сховище довіри не змінюється.

Origin CA замінюється вручну після закінчення його строку або відкликання; Certbot renew його не подовжує. Повторний запуск такого встановлення потребує тих самих `--origin-cert`/`--origin-key`, щоб випадково не змінити постачальника сертифіката.

## Якщо migrate завершується з помилкою ACCEPTED

Якщо журнал `docker logs --tail 200 accord-niche-migrate-1` містить `UnsafeNewEnumValueUsageError: unsafe use of new value "ACCEPTED"`, оновіть `backend/alembic/env.py` зі збірки v1.6.5 або новішої. Потім від root:

```bash
cd /opt/accord-niche
bash deploy/domains.sh --docker-edge build migrate api
python3 scripts/connect_elfar_edge.py \
  --origin-cert /etc/accord-niche/tls/origin.pem \
  --origin-key /etc/accord-niche/tls/origin.key
```

Причина — нове значення PostgreSQL ENUM використовувалося до commit. Виправлення задає окрему транзакцію на кожну ревізію. Базу видаляти або виконувати `alembic stamp` не потрібно. Збережіть `.env.domains`, томи й приватний ключ. У режимі Let's Encrypt повторюйте сценарій зі своїми початковими аргументами замість Origin CA.

## Підготовка для Let's Encrypt

1. Розпакуйте оновлену повну збірку в `/opt/accord-niche`, зберігши `.env.domains`. Скрипт не генерує й не змінює паролі.
2. У Cloudflare DNS для **зони ACCORD** переконайтеся, що `@`, `shop` і `dashboard` ведуть на цей VPS. На час першого випуску сертифіката встановіть для цих трьох записів **DNS only** (сіра хмаринка) та дочекайтеся оновлення DNS. Записи ELFAR залишаються поточними. Якщо AAAA заданий, його IPv6 теж має вести на цей VPS.
3. Порт 80 має приймати HTTP-перевірку Let's Encrypt. Сценарій перевірить усі три hostname контрольним файлом перед зверненням до Certbot. За недоступності зупиниться й відновить конфігурацію проксі.
4. Зробіть звичну резервну копію даних обох проєктів перед інфраструктурними змінами. Сам сценарій окремо копіює змінювані конфігурації в `.edge-backups`.

## Запуск від root

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py
```

Можна вказати власну контактну адресу Let's Encrypt:

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py --email YOUR_EMAIL
```

Якщо зараз працюєте під `shop` після `su - shop`, команда `exit` поверне до попередньої root-сесії. Якщо входили напряму, увійдіть під адміністративним користувачем і перейдіть у root звичним способом.

## Дії сценарію

1. Перевіряє live-мітки Compose, шляхи та спільні томи Nginx/Certbot. Відмовляється працювати з іншим namespace, невідомою структурою YAML або стороннім конфігом ACCORD.
2. Створює зовнішню мережу `accord-shared-edge` і піднімає ACCORD через `deploy/domains.sh --docker-edge up -d --build`. До цієї мережі зі сторони ACCORD підключаються тільки accord-website, accord-miniapp і accord-dashboard.
3. Зберігає копію Compose ELFAR, додає до **його nginx** спільну мережу та mount окремого `nginx/accord-main.conf`. Нові налаштування постійні й застосовуються стандартним деплоєм ELFAR.
4. Перевіряє Compose та Nginx у helper-контейнері без публікації портів. Для застосування mounts/networks коротко перестворює **тільки nginx і promo-controller** ELFAR. Controller перестворюється разом із проксі, бо ділить із ним PID namespace. Використовує `--no-deps --no-build --pull never`; інші сервіси ELFAR командою не вибираються.
5. Тимчасовий HTTP-vhost ACCORD віддає тільки ACME challenge, решта HTTP-запитів отримує 404.
6. Certbot отримує окремий сертифікат із cert-name `accordniche.pp.ua`, SAN: `accordniche.pp.ua`, `shop.accordniche.pp.ua` і `dashboard.accordniche.pp.ua`. Сертифікат ELFAR не розширюється й не замінюється.
7. Сценарій підключає TLS-vhost ACCORD, виконує `nginx -t`, потім reload. Перевіряє TLS з SNI й hostname validation, відповідь усіх трьох публічних сторінок і незмінність сертифіката ELFAR.

На час перестворення проксі очікуйте коротку перерву публічних HTTP/HTTPS-з'єднань. Бази, API, бот і scheduler ELFAR цим сценарієм не перезапускаються. Дані й `.env` ELFAR не змінюються. При помилці після внесення змін сценарій намагається відновити попередні конфігурації та проксі; резервна копія залишається для ручного відновлення.

## Після успіху

Поверніть `@`, `shop` та `dashboard` ACCORD у **Proxied** (помаранчева хмаринка). Режим SSL/TLS — **Full (strict)**.

```bash
curl -I https://accordniche.pp.ua/
curl -I https://shop.accordniche.pp.ua/
curl -I https://elfar.pp.ua/
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Панель `dashboard.accordniche.pp.ua` обслуговує цей самий Nginx через alias `accord-dashboard`. Доступ потребує входу в панель; перевірки ролей, CSRF, cookies і rate limits збережені. Окремий Tunnel не потрібний. Із v1.7.0 запуск без аргументів автоматично використовує наявні файли `/etc/accord-niche/tls/origin.pem` і `origin.key`. Сертифікат перевіряється для всіх трьох доменів до зміни Nginx.

Подовження сертифіката використовує чинний renew-loop promo-controller, який читає спільний `/etc/letsencrypt`. ACME location додана також у HTTPS-vhost ACCORD, щоб перевірка працювала при перенаправленні HTTP→HTTPS на Cloudflare. Після інсталяції варто окремо перевірити renew dry-run у погодженому режимі обслуговування.

Подальші оновлення ACCORD виконуйте з `--docker-edge`. Зміни `deploy/docker-compose.prod.yml` та новий `deploy/nginx/accord-main.conf` у репозиторії ELFAR потрібно зберегти як власні інфраструктурні зміни, щоб наступне оновлення вихідних файлів їх не затерло.

## Межі перевірки збірки

Локальні тести перевіряють внесення змін, межі двох проєктів, команди Certbot, успішний сценарій і відкат через Docker stub. Реальний Docker/Nginx/Certbot, DNS та випуск сертифіката перевіряються тільки під час виконання на VPS. Повні приватні ключі, env-файли та Docker inspect Env сценарій не виводить.
