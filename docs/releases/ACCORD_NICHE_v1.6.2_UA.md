# ACCORD NICHE v1.6.2 — паралельний запуск з ELFAR і TLS

Додано scripts/connect_elfar_edge.py під підтверджене середовище VPS: ELFAR /opt/elfar/deploy, Compose project deploy, deploy-nginx-1, deploy-certbot-1; ACCORD /opt/accord-niche, namespace accord-niche.

Сценарій створює спільну мережу для одного ELFAR Nginx і двох публічних frontend ACCORD, запускає окремий ACCORD стек, додає постійний mount/config у Compose ELFAR та випускає окремий сертифікат для accordniche.pp.ua і shop.accordniche.pp.ua. Дані, env і сертифікат ELFAR не замінюються. При внесенні mount/network коротко перестворюються тільки nginx і promo-controller, оскільки controller ділить PID namespace з nginx.

Перед змінами створюються копії конфігурацій; перевіряються Compose, nginx -t у helper без host ports, HTTP challenge, TLS з SNI/hostname validation та відповіді публічних сторінок. При помилці відновлюються попередні конфігурації й проксі. Є захист від сторонніх vhost/mounts, іншого Compose namespace і невідомої структури YAML.

ACME route додана до HTTPS-віртуальних хостів для подовження після HTTP→HTTPS redirect; сертифікат потрапляє в чинне спільне сховище Certbot і renew-loop promo-controller. Правила deny.d ELFAR застосовуються й до нових віртуальних хостів. Для stock root Nginx frontend ACCORD виправлено capability allowlist (попереднє cap_drop ALL без потрібних прав заважало worker setup).

Попередні ролі, мінімум DASHBOARD_PASSWORD у 8 символів, окремі томи й приватний dashboard збережені. Сценарій не публікує dashboard: для нього залишається Cloudflare Tunnel/Access.

Перевірки: 219 pytest-тестів і 4 subtests пройдено, зокрема 12 нових перевірок зміни Compose, ізоляції, bootstrap, команд Certbot, успішного сценарію й відкату. compileall і YAML parse пройшли. Сценарій на реальному VPS ще не виконувався; Docker/Nginx/Certbot у локальному прогоні замінені stub-ами.

Повна інструкція: docs/ELFAR_ACCORD_SHARED_EDGE_UA.md. На час першого випуску сертифіката DNS @ і shop ACCORD потрібно направити на VPS та тимчасово перевести в DNS only; після успіху повернути Proxied і Full (strict).
