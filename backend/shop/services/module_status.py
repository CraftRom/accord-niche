"""Стан модулів: «увімкнено» ≠ «працює» (A04).

Кожен модуль отримує один із станів:

* ``disabled`` — вимкнено в налаштуваннях; нічого не очікується;
* ``not_configured`` — увімкнено або потрібне, але бракує ключа/адреси;
* ``no_worker`` — налаштовано, але виконавець (scheduler/bot/maintenance) не подає heartbeat;
* ``ready`` — налаштовано й виконавець живий.

Нічого не надсилає назовні й не розкриває ключів: лише наявність налаштувань
і вік heartbeat. Реальні виклики провайдерів — окрема діагностика інтеграцій.
"""
from __future__ import annotations


from shop.config import settings
from shop.services.shop_settings import get_shop_settings
from shop.worker_health import states

STATES = ("disabled", "not_configured", "no_worker", "ready")


def _module(key, title, status, detail, worker=None):
    assert status in STATES
    return {"key": key, "title": title, "status": status, "detail": detail, "worker": worker}


def _needs(worker_states, worker, key, title, ready_detail, absent_detail):
    running = worker_states[worker]["running"]
    return _module(key, title, "ready" if running else "no_worker",
                   ready_detail if running else absent_detail, worker)


def sms_configured(shop=None) -> bool:
    """SMS gateway address, login and password are set (panel or .env)."""
    from shop.services.shop_settings import current
    return (shop or current()).sms_ready


async def module_report(repo, *, heartbeat_directory=None, now=None) -> dict:
    shop = await get_shop_settings(repo)
    workers = states(directory=heartbeat_directory, now=now)
    no_scheduler = ("Планувальник не запущений. Запустіть профіль workers: "
                    "bash deploy/domains.sh --docker-edge --profile workers up -d scheduler")
    modules = [
        _needs(workers, "scheduler", "scheduled_broadcasts", "Заплановані розсилки",
               "Планувальник запускає розсилки в призначений час.",
               no_scheduler + ". Ручна «Надіслати зараз» працює, заплановані — ні."),
    ]
    if not shop.backup_enabled:
        modules.append(_module("auto_backups", "Щоденні резервні копії", "disabled",
                               "Вимкнено в налаштуваннях.", "scheduler"))
    else:
        modules.append(_needs(workers, "scheduler", "auto_backups", "Щоденні резервні копії",
                              "Копія створюється раз на добу в заданий час.", no_scheduler + "."))
    modules.append(_needs(workers, "scheduler", "housekeeping", "Обслуговування даних",
                          "Прибирання журналів, старих копій і прострочених токенів раз на добу.",
                          no_scheduler + "."))
    modules.append(_needs(workers, "maintenance", "backup_jobs", "Копії з панелі",
                          "Виконавець приймає запити на копію з панелі.",
                          "Виконавець maintenance не подає heartbeat: запит копії з панелі чекатиме."))
    if not settings.bot_token:
        modules.append(_module("telegram_bot", "Telegram-бот", "not_configured",
                               "BOT_TOKEN не задано: бот і Telegram-оформлення вимкнені.", "bot"))
    else:
        modules.append(_needs(workers, "bot", "telegram_bot", "Telegram-бот",
                              "Бот отримує повідомлення в режимі polling.",
                              "Процес бота не подає heartbeat. Запустіть профіль bot."))
    if not shop.salesdrive_enabled:
        modules.append(_module("salesdrive", "SalesDrive CRM", "disabled", "Вимкнено в налаштуваннях.", "scheduler"))
    elif not shop.salesdrive_ready:
        modules.append(_module("salesdrive", "SalesDrive CRM", "not_configured",
                               "Бракує домену або ключа форми SalesDrive.", "scheduler"))
    else:
        modules.append(_needs(workers, "scheduler", "salesdrive", "SalesDrive CRM",
                              "Відправка йде одразу; повтори й фонове читання — у планувальнику.",
                              "Нові заявки відправляються одразу, але повтори після збою й фонове "
                              "читання не працюватимуть без планувальника."))
    from shop.services.phone_verification import telegram_ready
    modules.append(_module(
        "phone_telegram", "Підтвердження номера через Telegram",
        "ready" if telegram_ready() else "not_configured",
        "Покупці підтверджують номер на сайті кнопкою «📱 Надіслати номер» у боті." if telegram_ready() else
        "Задайте BOT_TOKEN і BOT_USERNAME: без бота підтвердження через Telegram недоступне.", "bot"))
    modules.append(_module(
        "sms_verification", "SMS-підтвердження телефону",
        "ready" if sms_configured(shop) else "not_configured",
        "Коди надсилаються через ваш SMS-шлюз (Android)." if sms_configured(shop) else
        "Необов'язково. Щоб надсилати коди в SMS, задайте SMS-шлюз у Налаштування → Інтеграції → "
        "«SMS-шлюз (Android)».", None))
    return {"modules": modules,
            "workers": [workers[name] for name in workers]}
