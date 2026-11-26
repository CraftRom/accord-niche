"""Налаштування магазину, які редагуються з панелі.

Значення перекривають змінні оточення: те, що не збережено тут, і далі
береться з .env. Тому свіжий деплой працює без жодного запису в базу.
"""
from __future__ import annotations

from dataclasses import fields

from fastapi import APIRouter, Depends, HTTPException

from api.auth import Principal, require_admin, require_sysadmin
from api.schemas import ShopSettingsIn, ShopSettingsOut
from shop import security_log as security
from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services.shop_settings import current, get_shop_settings, save_shop_settings

router = APIRouter(dependencies=[Depends(require_admin)])

# Central role policy. Managers have no writable settings, including loyalty.
from shop.access import INFRA_FIELDS, editable_settings  # INFRA_FIELDS is re-exported for QA
OPERATOR_FIELDS = frozenset()  # Compatibility for QA/imports: no manager exceptions.


def _out(shop) -> ShopSettingsOut:
    """Налаштування у вигляді, придатному для панелі.

    Складаємо вручну, а не віддаємо dataclass: серед полів є ключ Нової
    пошти, якого у відповіді бути не повинно, і похідна від нього ознака
    «підключено», якої немає серед збережених полів.
    """
    stored = {f.name: getattr(shop, f.name) for f in fields(shop)}
    for flag in ("novaposhta_connected", "salesdrive_form_connected",
                 "salesdrive_api_connected", "salesdrive_webhook_connected",
                 "sms_gateway_connected", "env_defaults"):
        stored[flag] = getattr(shop, flag)
    return ShopSettingsOut(**{
        key: value for key, value in stored.items()
        if key in ShopSettingsOut.model_fields
    })


@router.get("", response_model=ShopSettingsOut)
async def read_settings(repo: Repository = Depends(get_repo)):
    return _out(await get_shop_settings(repo))


@router.get("/environment")
async def environment(who: Principal = Depends(require_sysadmin)):
    """Стан змінних оточення: задані чи ні. Значень не розкриваємо.

    Лише для системного адміністратора: перелік того, що налаштовано на сервері, —
    підказка для того, хто шукає діру в захисті.
    """
    from shop.config import settings as env

    # Передаємо чинні налаштування: адреса сайту й імʼя бота можуть бути
    # задані в панелі, а не в оточенні
    return {"items": env.environment_report(current())}


@router.put("", response_model=ShopSettingsOut)
async def write_settings(
    data: ShopSettingsIn,
    who: Principal = Depends(require_admin),
    repo: Repository = Depends(get_repo),
):
    # exclude_unset — часткове збереження не затирає полів, яких немає у запиті
    payload = data.model_dump(exclude_unset=True)

    forbidden = sorted(set(payload) - editable_settings(who.role, ShopSettingsIn.model_fields))
    if forbidden:
        security.record('security.access.denied', actor=who.login, role=who.role.value,
                        reason='налаштування: ' + ', '.join(forbidden))
        raise HTTPException(403, 'Ці налаштування змінює лише системний адміністратор: '
                            + ', '.join(forbidden))

    saved = await save_shop_settings(repo, payload)
    # Самі назви полів, без значень: серед налаштувань є токен бота й
    # ідентифікатори чатів, і журнал не має ставати місцем їх витоку.
    security.record("security.settings.changed", actor=who.login,
                    role=who.role.value, reason=", ".join(sorted(payload)))
    return _out(saved)
