from __future__ import annotations

from shop.formatting import money as format_money

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shop.models import PromoCode, PromoUsage
from shop.services.promo_rules import eligible_subtotal, promo_discount


@dataclass
class PromoResult:
    ok: bool
    discount: Decimal = Decimal(0)
    promo: PromoCode | None = None
    error: str | None = None


async def apply(session: AsyncSession, code: str, user_id: int, subtotal: Decimal, *, lines=None) -> PromoResult:
    promo = await session.scalar(select(PromoCode).where(func.upper(PromoCode.code) == code.strip().upper()))

    if not promo or not promo.is_active:
        return PromoResult(False, error="Такого промокоду немає")

    if promo.expires_at:
        expires = promo.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            return PromoResult(False, error="Термін дії промокоду вичерпано")

    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        return PromoResult(False, error="Ліміт використань вичерпано")

    if subtotal < promo.min_order:
        return PromoResult(False, error=f"Мінімальна сума замовлення — {format_money(promo.min_order)} грн")

    used_by_user = await session.scalar(
        select(func.count(PromoUsage.id)).where(
            PromoUsage.promo_id == promo.id, PromoUsage.user_id == user_id
        )
    )
    if used_by_user >= promo.per_user_limit:
        return PromoResult(False, error="Ви вже використали цей промокод")

    base = subtotal
    if promo.brand_ids:
        if lines is None:
            from shop.services import cart
            lines = await cart.get_items(session, user_id)
        base = eligible_subtotal(lines, promo.brand_ids)
        if base <= 0:
            return PromoResult(False, error="У кошику немає товарів брендів цього промокоду")
    return PromoResult(True, discount=promo_discount(promo, base), promo=promo)


async def register_usage(session: AsyncSession, promo_id: int, user_id: int, order_id: int) -> None:
    session.add(PromoUsage(promo_id=promo_id, user_id=user_id, order_id=order_id))
    promo = await session.get(PromoCode, promo_id)
    if promo:
        promo.used_count += 1
    await session.commit()
