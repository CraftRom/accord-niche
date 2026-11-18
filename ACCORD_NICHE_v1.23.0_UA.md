# ACCORD NICHE v1.23.0 — промосторінки прибрано

Dashboard **1.89.0**. Промосторінки (конструктор лендингів на власних доменах) видалено з ACCORD повністю. Пункт A09 аудиту закрито рішенням не підтримувати цю функцію. Міграцій БД немає, head `a3d9b6e14f02`.

## Що прибрано

- **API:** роутер `/api/landing-pages` (редактор, публікація, статистика, SEO-генератор, Cloudflare, підключення доменів) і публічні маршрути рендеру й кліків. Middleware більше не має винятків для динамічних хостів: усі запити API проходять звичайний список дозволених хостів.
- **Панель:** розділ «Промосторінки» в меню, маршрут, сторінка й методи API-клієнта; рядок у матриці прав та інструкції.
- **Стан модулів і діагностика:** модуль «Домени промосторінок», перевірка Cloudflare-токена, рядки Google tags і DNS origin. Cloudflare-клієнт видалено, бо ним користувались лише промосторінки.
- **Журнал безпеки:** події `promo.*`.
- **Мертвий код:** `attributed_button_url`, який використовувала лише кнопка промосторінки.
- **Тести:** `qa_promo_landing`, `qa_promo_cloudflare`, `qa_promo_google`, `qa_external_google`, `qa_external_origin`, `run_promo_only.sh`, `promo-domain-ux.mjs`, промо-перевірки в змішаних наборах.
- **Старе одно-доменне розгортання в цьому репозиторії:** `deploy/promo-controller/`, `deploy-promo.sh`, `promo-domain-add.sh`/`promo-domain-remove.sh`, `nginx/promo-domain.conf.template`, промофаза в `deploy.sh` (тепер 5 фаз), токен у `bootstrap.sh`, сервіс і мережі в `docker-compose.prod.yml`, `include promo.d` у шаблоні nginx. Контролер раніше також поновлював TLS-сертифікати й перезавантажував nginx. Тепер у цьому compose-файлі це робить сам certbot-helper (`certbot renew` двічі на добу), а nginx перечитує сертифікати власним періодичним reload.
- **Документація:** `PROMO_PAGES.md`, `PROMO_CLOUDFLARE.md`, `PROMO_GOOGLE_INTEGRATION.md`.

## Що навмисно лишилось

- **Дані.** Таблиці `promo_landing_pages` і `promo_landing_daily_stats` та їхні моделі не видаляються: оновлення не знищує вже створені сторінки й статистику. Код їх більше не читає й не пише. Остаточне видалення таблиць — окремою міграцією за окремим рішенням.
- **ELFAR.** Живий ELFAR у `/opt/elfar` і його власний promo-controller не змінювались. `connect_elfar_edge.py`, як і раніше, перестворює nginx і контролер **ELFAR** у його compose під час підключення edge.
- **Промокоди** (знижки в кошику) — це окрема функція; вона працює без змін.

## Перевірено

- `backend/tests_accord` + `qa_accord_domain_split.py` з реальною PostgreSQL 16: **429 passed**.
- Повний `backend/qa/run_all.sh` у мережевій ізоляції: «Усі набори пройдено». Серед них етапи деплою, health gate і rollback legacy-сценарію з новою нумерацією фаз.
- Dashboard: production build і **56** JS/DOM-тестів.
- `qa/qa-nginx-security.py` локально не пройшов синтаксичну перевірку лише через директиву `http2`: тут nginx 1.24, а потрібна ≥ 1.25.

## Оновлення

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py
python3 /opt/accord-niche/scripts/accord_release_check.py
```

Після оновлення пункт «Промосторінки» зникне з меню панелі. Якщо в `.env.domains` є `PROMO_CONTROLLER_*`, ці змінні більше ні на що не впливають, і їх можна прибрати.
