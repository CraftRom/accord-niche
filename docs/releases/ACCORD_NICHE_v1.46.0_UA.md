# ACCORD NICHE v1.46.0 — підтримка Android-застосунку магазину

Версія панелі: 1.96.0.

Для сайту — збільшена й зручніша мобільна версія (розділ 4).

Android-застосунок ACCORD NICHE — окремий проєкт (Android 12+, Kotlin, Jetpack Compose). Він працює з чинним API
сайту (`/api/public`, `/api/web`) з тими самими cookies, `Origin` і CSRF. Цей реліз додає на сервері те, без чого
застосунок не міг повноцінно працювати, і показує його замовлення окремим каналом.

## 1. Вхід через Google із застосунку

Android Credential Manager видає ID-токен для вебклієнта сайту (`aud` = `ACCORD_GOOGLE_CLIENT_ID`), але з
Android-клієнтом у полі `azp`. Раніше сервер такий токен відхиляв. Тепер `azp` приймається, лише якщо цей
Android-клієнт перелічено в `ACCORD_GOOGLE_ANDROID_CLIENT_IDS`. Android-клієнт ніколи не приймається як `aud`.
Вхід із сайту не змінився.

## 2. `/.well-known/assetlinks.json` — посилання сайту відкриваються в застосунку

Nginx головного домену віддає `GET /api/public/android/assetlinks.json` за адресою `/.well-known/assetlinks.json`.
Заява будується з `ACCORD_ANDROID_PACKAGE` (типово `ua.accordniche.shop`) і `ACCORD_ANDROID_CERT_SHA256`. Поки
відбиток не задано, відповідь — `[]`: нічого не заявляється.

Формат значень: навколишні лапки `"…"`/`'…'` і пробіли прибираються (Docker `env_file` передає їх буквально);
кілька значень розділяються комою, крапкою з комою або пробілом. Відбиток SHA-256 приймається в будь-якому
регістрі, з двокрапками (`AB:CD:…`) або як 64 hex-символи без них — у заяві він завжди `AB:CD:…`.

### Якщо відповідь `[]`, хоча відбиток задано

Перевірка в обхід Cloudflare (на сервері, з кореня проєкту):

```bash
# 1. Чи дійшла змінна до контейнера API (лапки навколо значення допустимі)
bash deploy/domains.sh exec api printenv ACCORD_ANDROID_CERT_SHA256

# 2. Що віддає сам сайт, без Cloudflare. Порт — ACCORD_SITE_PORT з .env.domains (типово 18081).
ACCORD_SITE_PORT=$(grep -E '^ACCORD_SITE_PORT=' .env.domains | cut -d= -f2); ACCORD_SITE_PORT=${ACCORD_SITE_PORT:-18081}
curl -s -H 'Host: accordniche.pp.ua' http://127.0.0.1:$ACCORD_SITE_PORT/.well-known/assetlinks.json
curl -sI -H 'Host: accordniche.pp.ua' http://127.0.0.1:$ACCORD_SITE_PORT/.well-known/assetlinks.json | grep -i 'cache-control\|content-type'

# 3. Чому порожньо: попередження з назвою змінної і причиною (саме значення в журнал не пишеться)
bash deploy/domains.sh logs api | grep -i 'ACCORD_ANDROID\|ACCORD_GOOGLE_ANDROID'
```

- Порожня `printenv` — змінна не потрапила в контейнер: перевірте назву в `.env.domains` і перезапустіть
  `bash deploy/domains.sh up -d api` (лише `restart` нових змінних не підхоплює).
- Локально заява є, а `https://accordniche.pp.ua/.well-known/assetlinks.json` повертає `[]` — це старий кеш
  Cloudflare. Очищення: Cloudflare → домен accordniche.pp.ua → **Caching → Configuration → Purge Cache →
  Custom Purge → URL** → `https://accordniche.pp.ua/.well-known/assetlinks.json` → Purge. Або через API:
  `curl -X POST "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/purge_cache" -H "Authorization: Bearer <TOKEN>"
  -H 'Content-Type: application/json' --data '{"files":["https://accordniche.pp.ua/.well-known/assetlinks.json"]}'`.
  З v1.49.2 порожня відповідь має `Cache-Control: no-store`, а заповнена — `public, max-age=300`, тож ця
  ситуація більше не має повторюватися.
- Після цього Android перевіряє домен під час встановлення/оновлення застосунку; повторна перевірка на
  пристрої: `adb shell pm verify-app-links --re-verify ua.accordniche.shop`, стан —
  `adb shell pm get-app-links ua.accordniche.shop` (має бути `verified`).

## 3. Канал продажу «Застосунок»

Замовлення й візити з застосунку раніше записувались як «Сайт». Тепер у них окремий канал `accord_android`:

- **Візити.** `POST /api/web/analytics/visit` із джерелом `accord_android` пише візит із каналом `accord_android`
  (дублікат того самого запуску не рахується — новий частковий унікальний індекс `ux_analytics_app_session`).
- **Замовлення.** `POST /api/web/checkout` ставить канал `accord_android` і прив'язує замовлення до візиту застосунку.
  Візит сайту й візит застосунку ніколи не конвертують одне одного.
- **Аналітика.** Воронка показує «Застосунок» окремим рядком поруч із «Сайт» і «Mini App».
- **Панель.** Фільтр «Канал продажу» в замовленнях, лічильники відкритих замовлень і картка клієнта мають
  «Застосунок».

Ціни, залишки, знижки й права однакові для сайту й застосунку: канал впливає лише на звіти.

## 4. Сайт на телефоні: крупніше й зручніше

- **Шапка** лишається вгорі під час прокрутки; висота 72 px, логотип 132 px, значки 24 px у зонах натискання 48 px,
  лічильник кошика більший. На вузьких телефонах (до 380 px) — на крок менше, нічого не обрізається.
- **Меню** відкривається на весь екран під шапкою: пункти 22 px у рядках 64 px зі стрілками, поточний розділ
  виділено; сторінка під меню не прокручується.
- **Текст і керування:** дрібний текст 13 px (було 12), кнопки 14 px і 52 px заввишки, поля вводу 16 px і 48 px
  (iOS більше не збільшує сторінку під час введення), більші кнопки «−/+», «Видалити», «Оновити», «← Назад».
- Лише для ширини до 750 px; комп’ютерна версія не змінилася.

## Оновлення

Міграція `c3e9a1f7b254` лише створює індекс; дані не змінюються.

```bash
bash deploy/domains.sh check
bash deploy/domains.sh up -d --build
```

Нові змінні (`ACCORD_GOOGLE_ANDROID_CLIENT_IDS`, `ACCORD_ANDROID_PACKAGE`, `ACCORD_ANDROID_CERT_SHA256`) описані в
`.env.example` і `.env.domains.example`; без них усе працює як раніше, окрім Google-входу в застосунку.

Налаштування в Google Cloud: OAuth-клієнт типу *Android* у тому ж проєкті, що й вебклієнт, — пакет
`ua.accordniche.shop` і SHA-1 ключа підпису застосунку.

## Перевірки

- `backend/tests_accord/test_android_app.py`: вебтокен як раніше; Android-`azp` лише з налаштованим ID; чужий клієнт
  і Android-клієнт як `aud` відхиляються; `assetlinks.json` порожній без відбитка й коректний із ним; Nginx віддає
  файл раніше за блокування dot-файлів.
- `test_website_funnel.py`: візити застосунку — окремий канал, повтор не рахується, конверсія 50 % на двох запусках
  і одному замовленні, перехресні ідентифікатори сайту й застосунку не конвертують.
- `test_commerce_workspace.py`: замовлення застосунку — канал `app` у черзі, фільтрі й лічильниках, навіть із
  `session_id` (раніше такі потрапляли б у Mini App).
- Повний шлях покупця застосунку проти цього API: каталог, розрахунок із промокодом, замовлення в каналі «Застосунок»,
  повтор без дубля, історія, скасування, відновлення простроченого CSRF.
