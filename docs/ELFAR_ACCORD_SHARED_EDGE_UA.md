# ELFAR і ACCORD паралельно на VPS

Сценарій підготовлено для підтвердженої конфігурації:

- ELFAR: Compose project `deploy`, `/opt/elfar/deploy/docker-compose.prod.yml`.
- Публічний проксі: `deploy-nginx-1`, порти 80/443.
- Certbot: `deploy-certbot-1`, спільні з Nginx томи `/etc/letsencrypt` і `/var/www/certbot`.
- ACCORD: `/opt/accord-niche`, `COMPOSE_PROJECT_NAME='accord-niche'`.

## Уже створений Cloudflare Origin CA

Для цього способу DNS-записи ACCORD `@` і `shop` залишаються **Proxied**, SSL/TLS — **Full (strict)**. Origin CA перевіряє Cloudflare; у звичайному прямому підключенні браузер не довіряє цьому CA. Сертифікат повинен містити `accordniche.pp.ua` і `shop.accordniche.pp.ua`, або `accordniche.pp.ua` та `*.accordniche.pp.ua`.

Встановіть збірку v1.6.3 або новішу зі збереженням `.env.domains`. Від root створіть файли поза Git:

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

Сценарій завантажує публічні RSA/ECC кореневі CA з офіційних HTTPS-адрес Cloudflare. Перед зміною проксі перевіряє пару cert/key, строк дії, ланцюжок і обидва hostname. Потім копіює пару в окремий каталог `accord-origin/<digest>` спільного TLS-тома Nginx/Certbot; файли ELFAR та попередні пари не перезаписуються. Certbot issuance і HTTP-01 probe у цьому режимі не виконуються. Локальна перевірка TLS використовує явний trust bundle Origin CA із перевіркою hostname; глобальне системне сховище CA не змінюється.

Origin CA замінюється вручну після закінчення його строку або відкликання; Certbot renew його не подовжує. Повторний запуск такого встановлення потребує тих самих `--origin-cert`/`--origin-key`, щоб випадково не змінити постачальника сертифіката.

## Підготовка для Let's Encrypt

1. Розпакуйте оновлену повну збірку в `/opt/accord-niche`, зберігши `.env.domains`. Скрипт не генерує й не змінює паролі.
2. У Cloudflare DNS для **зони ACCORD** переконайтеся, що `@` і `shop` ведуть на цей VPS. На час першого випуску сертифіката встановіть для цих двох записів **DNS only** (сіра хмаринка) та дочекайтеся оновлення DNS. Записи ELFAR залишаються поточними. Якщо AAAA заданий, його IPv6 теж має вести на цей VPS.
3. Порт 80 має приймати HTTP-перевірку Let's Encrypt. Сценарій перевірить обидва hostname контрольним файлом перед зверненням до Certbot. За недоступності зупиниться й відновить конфігурацію проксі.
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
2. Створює зовнішню мережу `accord-shared-edge` і піднімає ACCORD через `deploy/domains.sh --docker-edge up -d --build`. До цієї мережі зі сторони ACCORD підключаються тільки website і miniapp.
3. Зберігає копію Compose ELFAR, додає до **його nginx** спільну мережу та mount окремого `nginx/accord-main.conf`. Нові налаштування постійні й застосовуються стандартним деплоєм ELFAR.
4. Перевіряє Compose та Nginx у helper-контейнері без публікації портів. Для застосування mounts/networks коротко перестворює **тільки nginx і promo-controller** ELFAR. Controller перестворюється разом із проксі, бо ділить із ним PID namespace. Використовує `--no-deps --no-build --pull never`; інші сервіси ELFAR командою не вибираються.
5. Тимчасовий HTTP-vhost ACCORD віддає тільки ACME challenge, решта HTTP-запитів отримує 404.
6. Certbot отримує окремий сертифікат із cert-name `accordniche.pp.ua`, SAN: `accordniche.pp.ua` і `shop.accordniche.pp.ua`. Сертифікат ELFAR не розширюється й не замінюється.
7. Сценарій підключає TLS-vhost ACCORD, виконує `nginx -t`, потім reload. Перевіряє TLS з SNI й hostname validation, відповідь обох публічних сторінок і незмінність сертифіката ELFAR.

На час перестворення проксі очікуйте коротку перерву публічних HTTP/HTTPS-з'єднань. Бази, API, бот і scheduler ELFAR цим сценарієм не перезапускаються. Дані й `.env` ELFAR не змінюються. При помилці після внесення змін сценарій намагається відновити попередні конфігурації та проксі; резервна копія залишається для ручного відновлення.

## Після успіху

Поверніть `@` та `shop` ACCORD у **Proxied** (помаранчева хмаринка). Режим SSL/TLS — **Full (strict)**.

```bash
curl -I https://accordniche.pp.ua/
curl -I https://shop.accordniche.pp.ua/
curl -I https://elfar.pp.ua/
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Панель `dashboard.accordniche.pp.ua` залишається окремою: Cloudflare Tunnel → `http://127.0.0.1:18082` із Access/MFA. Сценарій не публікує панель у спільному Nginx.

Подовження сертифіката використовує чинний renew-loop promo-controller, який читає спільний `/etc/letsencrypt`. ACME location додана також у HTTPS-vhost ACCORD, щоб перевірка працювала при перенаправленні HTTP→HTTPS на Cloudflare. Після інсталяції варто окремо перевірити renew dry-run у погодженому режимі обслуговування.

Подальші оновлення ACCORD виконуйте з `--docker-edge`. Зміни `deploy/docker-compose.prod.yml` та новий `deploy/nginx/accord-main.conf` у репозиторії ELFAR потрібно зберегти як власні інфраструктурні зміни, щоб наступне оновлення вихідних файлів їх не затерло.

## Межі перевірки збірки

Локальні тести перевіряють внесення змін, межі двох проєктів, команди Certbot, успішний сценарій і відкат через Docker stub. Реальний Docker/Nginx/Certbot, DNS та випуск сертифіката перевіряються тільки під час виконання на VPS. Повні приватні ключі, env-файли та Docker inspect Env сценарій не виводить.
