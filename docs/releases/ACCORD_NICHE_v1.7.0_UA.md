# ACCORD NICHE v1.7.0 — панель через спільний HTTPS

У попередній схемі магазин і Mini App налаштовувалися через Nginx ELFAR, а dashboard вимагав окремого Cloudflare Tunnel. Якщо DNS dashboard вказував безпосередньо на VPS, Nginx віддавав сертифікат іншого сайту й Cloudflare повертав 526.

Тепер усі три домени використовують той самий HTTPS edge. Додано окремий vhost dashboard.accordniche.pp.ua, Docker alias accord-dashboard і підключення frontend панелі до accord-shared-edge. API, PostgreSQL та Redis залишаються у внутрішній мережі; host-порти frontend залишаються прив'язаними до 127.0.0.1. Шаблон системного Nginx також оновлено.

Сценарій connect_elfar_edge.py автоматично знаходить origin.pem та origin.key в /etc/accord-niche/tls. Власні шляхи й режим Let's Encrypt збережені. Сертифікат перевіряється для кореня, shop і dashboard до змін проксі; підтримується корінь разом із *.accordniche.pp.ua. Для Let's Encrypt усі три домени включені у SAN і ACME probe. Після налаштування перевіряється TLS і відповідь кожного з трьох доменів. Сертифікат ELFAR не замінюється.

Вхід у панель, HttpOnly/Secure cookies, перевірки Origin/CSRF, RBAC, ліміти входу, HSTS і security headers збережені. Tunnel та Cloudflare Access більше не є обов'язковими для запуску; Access за бажанням можна використовувати як додатковий захист.

## Оновлення

Оновіть вихідні файли тільки у /opt/accord-niche, збережіть .env.domains, томи та файли /etc/accord-niche/tls. Від root виконайте одну команду:

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py
```

Сценарій сам запускає збірку й Compose ACCORD, застосовує Nginx та перевіряє три домени. Для цього способу DNS @, shop, dashboard має вести на VPS у Proxied; SSL/TLS — Full (strict). При недостатньому покритті SAN він зупиниться з назвою домену до зміни Nginx: сертифікат потрібно перевипустити з коренем та wildcard або трьома SAN. Перевірка TLS не вимикається.

## Перевірки

- 247 pytest-тестів і 4 subtests пройдено, включно з попередньою PostgreSQL-регресією, новою мережею frontend, відмовою для сертифіката без dashboard, автоматичним вибором наявних PEM і TLS/HTTP-перевірками всіх трьох hostname.
- Обидва edge-шаблони й внутрішній конфіг dashboard пройшли nginx -t на зібраному з офіційних вихідних файлів Nginx 1.28.0. У тесті використано тимчасовий сертифікат і непривілейовані порти.
- У локальному Nginx перевірено повний шлях HTTPS edge → dashboard frontend: сторінка панелі 200, захищений API 401, старий login endpoint 404, спроба читання SQL через media 404, HTTP redirect 308, повторні спроби входу отримують 429. Для перевірки маршрутизації API та дві публічні вітрини замінювалися локальними Nginx-відповідями; це не тест фактичної авторизації backend.
- Реальні DNS, сертифікат користувача та застосування конфігурації на VPS тут не змінювалися; їх перевіряє скрипт під час запуску на сервері.
