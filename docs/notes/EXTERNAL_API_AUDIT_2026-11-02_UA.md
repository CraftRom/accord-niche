# Перевірка зовнішніх API — 02.11.2026

Dashboard **1.78.0**, API **1.29.0**, build `2026-11-02-external-api-audit`.
Mini App **2.26.4**, бот **1.19.1**. Нових міграцій у цьому оновленні немає;
поточний Alembic head — `fb4a8c2d1e70` з попереднього оновлення розсилок.
Архів містить також попередні зміни промокодів і розсилок.

## Обсяг і результат

Перевірено всі знайдені в коді зовнішні інтеграції: офіційні контракти,
HTTP-транспорт, кеші, повтори, ліміти та обробку помилок. Наведені нижче
автоматичні перевірки використовують підмінені відповіді провайдерів.
Бойових ключів у цьому середовищі немає, тому автентифікацію реальних
облікових записів, мережу VPS і фактичні конверсії Google тут не підтверджено.
Повідомлень клієнтам, заявок, накладних, DNS-записів і сертифікатів не створювали.

| Інтеграція | Сумісність і виконані зміни |
| --- | --- |
| Telegram Bot API / Mini App | Наявний aiogram 3.31.0 уже підтримує Bot API 10.3. Перевірку initData не змінювали: вона відповідає схемі Telegram. Прямий клієнт більше не повторює повідомлення після неоднозначних помилок читання/запису чи 5xx; повністю враховує flood wait. Для розсилки використовується один пул HTTP-з’єднань на блок отримувачів. |
| Нова пошта | Збережено чинний JSON API 2.0. JSON POST з ключем проходить лише обмежені HTTPS-перенаправлення в межах того самого origin, включно з 303. Посилено перевірку відповідей, обробку 429 та ізоляцію кешів і пауз між ключами. |
| SalesDrive | Перевірено перехід на `data[].products` та `upsell`, наявний у коді. Додано збереження `stockBalance` поряд із `priceTypes`, `defaultPriceData` та `complect`. Однакові одночасні читання об’єднуються; відключення одного клієнта не скасовує запит для інших. Враховується `Retry-After`, включно з HTTP-date. |
| Cloudflare API v4 | Додано токени акаунта через `/accounts/{account_id}/tokens/verify` і поле Account ID у панелі; токени користувача перевіряються через `/user/tokens/verify`. Перевіряються активність, строки дії та структура відповіді. GET має один обмежений повтор; записи DNS/SSL автоматично не повторюються. |
| Google tag / GA4 / Ads / GTM | Збережено Consent Mode v2 з defaults перед config та одним способом завантаження тегів. Кнопка враховує Ctrl/Meta/Shift/Alt, нову вкладку, `event_timeout`, одноразовий callback та резервний перехід. Редактор не завантажує трекінг. Звітного API GA4/Ads або OAuth у проєкті немає. |
| Public IP / DNS-over-HTTPS | Запити до незалежних IP-провайдерів і IPv4/IPv6 виконуються паралельно; збережено голосування, overrides і кеш. DNS-відповіді перевіряються за `Status`, типом конверта та записів; помилки NS/A/AAAA не приймаються за успіх. |
| ACME v2 / Let’s Encrypt | Основний ACME v2 шлях збережено. Застарілий `--buypass` завершується з поясненням до запиту email або запуску Certbot: провайдер припинив випуск TLS/SSL у 2025 році. Оновлено інструкцію щодо лімітів та staging. |

## Важливі деталі реалізації

- SalesDrive з 19.08.2026 використовує `upsell`; старий `preSale` залишено
  як сумісний fallback. Явне `upsell: 0` має пріоритет над `preSale: 1`.
  Видалення старих product options з meta з 19.10.2026 не порушує читання:
  товари беруться з `data[].products`.
- Об’єднання одночасних запитів перевірено: 20 однакових читань SalesDrive
  виконують один HTTP-запит. Це перевірка конкретного сценарію, а не
  вимірювання загальної швидкодії або споживання квоти на бойовому сервері.
- Для `/api/order/list/` діють квоти SalesDrive 10/хв, 100/год, 1000/добу.
  Наявні пакетна синхронізація, кеш і Redis-координація збережені. Нові паузи
  після 429 та об’єднання читань працюють у межах процесу; глобального
  лічильника всієї квоти всіх споживачів акаунта це оновлення не додає.
- Безпечні помилки встановлення з’єднання і короткі відхилені Telegram 429
  можуть повторюватися. Неоднозначна доставка лишається непідтвердженою;
  журнал отримувачів розсилки керує подальшим відновленням.
- Секрети не входять у назви ключів кешу чи діагностичний звіт. Cloudflare
  токен лишається зашифрованим і не повертається до браузера. Account ID
  зберігається окремо від токена.

## Діагностика на сервері

У каталозі `backend`, з налаштованою базою та оточенням застосунку:

```bash
python -m shop.check_integrations
python -m shop.check_integrations --live
```

Перший запуск читає конфігурацію без мережі. `--live` паралельно перевіряє
налаштовані Telegram (`getMe`), Нову пошту (читання населених пунктів),
SalesDrive (актуальні статуси без stale-cache) та Cloudflare (активність токена).
Кожна перевірка має окремий таймаут. Звіт JSON містить провайдера, стан,
затримку, пояснення і кількість перевірених інтеграцій.

Для авторизованого системного адміністратора також доступні
`GET /api/integrations/health` і `GET /api/integrations/health?live=true`.
Методи діагностики не відправляють повідомлень і не створюють бізнес-об’єктів.
Перевірка Cloudflare підтверджує активність токена; доступ до конкретної
зони перевіряється наявною перевіркою домену у панелі.

`not_configured`, `client_side` та `runtime_required` означають, що інтеграцію
ще не підтверджено. Загальний `partial` і код виходу 0 не означають, що всі
сервіси перевірені: дивіться `verified`, `errors` і кожний рядок `providers`.
Код 1 означає помилку хоча б одного виконаного probe.

Google потрібно перевірити на опублікованій сторінці у власних Tag Assistant,
GA4/Ads; DNS, IP і HTTPS — на VPS через наявний promo-controller/Certbot.
Якщо сервер раніше поновлював сертифікат через Buypass, після перевірки
доменів треба перевипустити його через Let’s Encrypt; збережені ACME-конфіги
та сертифікати цим архівом автоматично не перезаписуються.

## Автоматична перевірка

| Набір | Результат |
| --- | --- |
| Нові контракти API, шифрування і HTTP-діагностика | 40/40 |
| Паралельні IP, DNS NS/A, відхилення Buypass | 8/8 |
| Генератор Google tag | 4/4 |
| Chromium: згода, модифікатори, callback/fallback | 6/6 |
| Нова пошта | 54/54 |
| SalesDrive / ТТН | 54/54 |
| SalesDrive dictionaries / rich read / background batch | 5/5, 29/29, 17/17 |
| CRM live sync / SalesDrive read side | 18/18, 6/6 |
| Розсилки: текст, фото, медіа | 60/60 |
| Черга розсилок, відновлення, Telegram, міграція | 35/35 |
| Наявні promo Cloudflare, Google та landing checks | PASS |
| Dashboard production build, Python compile, Bash syntax | PASS |

Нові Python-набори додано до `backend/qa/run_all.sh`; браузерний набір —
до `qa/run-browser.sh` і `npm run test:external-api`. Генератор fixture
використовує реальний production renderer. Мережа Google у браузерному
тесті підмінена; реальних аналітичних подій немає.

## Офіційні джерела

Звірено 02.11.2026:

- [SalesDrive: зміни API серпня 2026](https://salesdrive.ua/blog/api-changes-august-2026/)
- [SalesDrive: отримання заявок і квоти](https://salesdrive.ua/knowledge/api/order-list/)
- [Telegram Bot API changelog](https://core.telegram.org/bots/api-changelog)
- [aiogram changelog](https://docs.aiogram.dev/en/latest/changelog.html)
- [Telegram Mini App: перевірка initData](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)
- [Нова пошта: інтеграція, чинний API endpoint](https://novaposhta.ua/for-business/cooperation/integration/)
- [Cloudflare: account token verify](https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/verify/)
- [Cloudflare: user token verify](https://developers.cloudflare.com/api/resources/user/subresources/tokens/methods/verify/)
- [Cloudflare: API limits](https://developers.cloudflare.com/fundamentals/api/reference/limits/)
- [Google: Consent Mode](https://developers.google.com/tag-platform/security/guides/consent)
- [Google: параметри event_callback / event_timeout](https://developers.google.com/tag-platform/gtagjs/reference/parameters)
- [Let’s Encrypt: ACME updates](https://letsencrypt.org/docs/acme-protocol-updates/)
- [Let’s Encrypt: rate limits](https://letsencrypt.org/docs/rate-limits/)
- [Buypass: припинення випуску TLS/SSL](https://www.buypass.com/products/tls-ssl-certificates/discontinues-issuance-of-tls-ssl-certificates)

Портал методів Нової пошти повертав HTTP 403 із середовища перевірки.
Тому повне повторне читання закритих сторінок методів не заявляється;
наявний контракт перевірено локально, а роботу реального ключа має
підтвердити `--live` на сервері.
