# ACCORD NICHE v1.8.1 — окремі Docker-імена поруч з ELFAR

Після підключення ACCORD у спільну мережу в конфігурації виявлено небезпечний конфлікт DNS-імен. Docker Compose реєструє ім'я сервісу на кожній його мережі додатково до явних aliases. Отже, aliases accord-website/accord-miniapp/accord-dashboard не прибирали неявні website/miniapp/dashboard. Nginx ELFAR використовує саме короткі імена miniapp і dashboard, тому міг отримати IP frontend ACCORD. Той відхиляв чужий Host, що могло спричинити 502. Зовнішня перевірка показала ELFAR 502 і ACCORD/dashboard 200; точний upstream із журналу робочого VPS у цьому середовищі не отримано.

## Постійне виправлення

У доменному Compose ACCORD frontend-сервіси перейменовано на accord-website, accord-miniapp, accord-dashboard. Тепер навіть неявні service-name aliases мають окремі імена й не перекривають ELFAR. Шаблони Nginx вже використовують ці aliases. API, PostgreSQL та Redis не додаються до спільної мережі. Рішення не потребує нової опції use_service_name_alias або оновлення Docker Compose.

Імена образів збережено. При наступному up сценарій domains.sh мігрує тільки три старі stateless frontend-контейнери ACCORD. Він перевіряє Compose labels, namespace, вихідні файли й відсутність writable data volumes; при --build спочатку успішно збирає образи. Потім зупиняє й прибирає лише підтверджені старі frontend-контейнери, звільняючи їхні loopback-порти. Нові контейнери створює Compose. Бази, API, дані та контейнери ELFAR міграція не видаляє. Під час одноразової заміни можлива коротка перерва доступу до frontend ACCORD.

Після деплою connect_elfar_edge.py перевіряє не лише незмінність сертифіката ELFAR, а й його HTTPS/HTTP-відповідь. 502 більше не проходить як успіх. Якщо змінювався тільки існуючий edge-конфіг, відкат використовує nginx -t і reload, без перестворення nginx/promo-controller. Перестворення потрібне лише при фактичній зміні mounts/networks самого проксі.

Оновіть файли тільки в /opt/accord-niche зі збереженням .env.domains, томів та /etc/accord-niche/tls. Від root:

```bash
python3 /opt/accord-niche/scripts/connect_elfar_edge.py
```

Нові frontend-контейнери мають назви accord-niche-accord-website-1, accord-niche-accord-miniapp-1 та accord-niche-accord-dashboard-1. Для їхніх журналів використовуйте відповідні нові service names у domains.sh.

## Тимчасове усунення конфлікту до оновлення

Для старих frontend-контейнерів v1.7/v1.8 на підтвердженому VPS можна перепідключити тільки зовнішню мережу через Docker CLI. Він додасть тільки явні namespaced aliases. Внутрішня мережа ACCORD залишається підключеною:

```bash
for service in website miniapp dashboard; do
  docker network disconnect accord-shared-edge "accord-niche-${service}-1" &&
  docker network connect --alias "accord-${service}" accord-shared-edge "accord-niche-${service}-1"
done
docker exec deploy-nginx-1 nginx -t &&
docker exec deploy-nginx-1 nginx -s reload
```

Це тимчасовий крок: старий Compose при перестворенні frontend міг додати короткі aliases знову. Потрібно встановити постійну зміну імен із цієї збірки. Якщо ELFAR продовжує повертати 502, потрібен його nginx error log: конфлікт імен є реальним недоліком попередньої конфігурації, але він не виключає окремого збою upstream ELFAR.

## Перевірки

Пройдено 273 Python-тести та 14 subtests. Нові перевірки покривають саме неявні Compose aliases, збереження loopback listeners, ізоляцію API/БД, одноразову міграцію frontend, відмову при чужих labels або writable volume, успішну збірку до зупинки та відкат лише через reload, коли ELFAR HTTP-перевірка повертає 502. Реальний Docker Engine/VPS тут недоступний; Docker-команди перевірено через контрольовані підміни. Раніше виконані 15 JS/DOM-перевірок вітрини й ролей залишаються застосовними: їхній код у цьому виправленні не змінювався.

Офіційні правила Docker:
https://docs.docker.com/reference/compose-file/services/#aliases
https://docs.docker.com/compose/how-tos/networking/
