# ACCORD NICHE v1.49.2 — `assetlinks.json` для Android-застосунку, назва ACCORD у SalesDrive

Міграцій немає. Після оновлення: `bash deploy/domains.sh up -d --build`, далі одноразово очистити кеш
`https://accordniche.pp.ua/.well-known/assetlinks.json` у Cloudflare (інструкція нижче).

## Симптом

Після додавання `ACCORD_ANDROID_CERT_SHA256` у `.env.domains` і перезапуску адреса
`https://accordniche.pp.ua/.well-known/assetlinks.json` повертала `[]`.

## Що виправлено

- **Кеш.** Порожня відповідь `[]` тепер іде з `Cache-Control: no-store`, заповнена — з `public, max-age=300`,
  тож Cloudflare не тримає порожню заяву годину. Загальний захисний middleware API ставить `no-store` на всі
  відповіді `/api/`; для `assetlinks.json` він тепер залишає заголовок ендпоінта. Nginx у
  `location = /.well-known/assetlinks.json` не додає власних `Cache-Control`/`expires`, `Content-Type` —
  `application/json` від API (перевіряється тестом).
- **Лапки й формат.** Docker `env_file` передає лапки буквально. Для `ACCORD_ANDROID_CERT_SHA256`,
  `ACCORD_ANDROID_PACKAGE` і `ACCORD_GOOGLE_ANDROID_CLIENT_IDS` навколишні `"`, `'` і пробіли прибираються.
  Відбиток приймається в будь-якому регістрі, з двокрапками або як 64 hex-символи — у заяві завжди `AA:BB:…`.
  Кілька значень розділяються комою, крапкою з комою або пробілом. Розбір — у `backend/shop/android_config.py`.
- **Тиха відмова.** Якщо змінна задана, але жодне значення не пройшло перевірку, у журналі API з'являється одне
  попередження з назвою змінної й причиною (без самого значення).
- **SalesDrive.** Коментар до замовлення тепер «Замовлення ACCORD №…», назва форми в підказках панелі й
  документації — «ACCORD — Telegram Bot». Інтеграція звіряє лише числовий `formId`, тож форму в SalesDrive
  можна перейменувати без змін у налаштуваннях.

## Перевірка в обхід Cloudflare

```bash
bash deploy/domains.sh exec api printenv ACCORD_ANDROID_CERT_SHA256
ACCORD_SITE_PORT=$(grep -E '^ACCORD_SITE_PORT=' .env.domains | cut -d= -f2); ACCORD_SITE_PORT=${ACCORD_SITE_PORT:-18081}
curl -s -H 'Host: accordniche.pp.ua' http://127.0.0.1:$ACCORD_SITE_PORT/.well-known/assetlinks.json
bash deploy/domains.sh logs api | grep -i 'ACCORD_ANDROID\|ACCORD_GOOGLE_ANDROID'
```

Якщо локально заява є, а через домен — `[]`: Cloudflare → accordniche.pp.ua → **Caching → Configuration →
Purge Cache → Custom Purge → URL** → `https://accordniche.pp.ua/.well-known/assetlinks.json`. Докладніше — розділ
«Android-застосунок» у [DEPLOY.md](../DEPLOY.md).

## Перевірки

`backend/tests_accord/test_android_app.py`: значення в лапках, нижній регістр, без двокрапок, кілька відбитків
через пробіл, кому й крапку з комою дають правильну заяву; порожня відповідь — `no-store`, заповнена —
`public, max-age=300` (і після middleware); некоректне значення дає `[]` і одне попередження; клієнт Android
у лапках приймається й дає вхід. Повний `backend/tests_accord`, `qa_accord_domain_split`.
