"""Shared brand and monetary rules for quotes, bot and locked checkout."""
from decimal import Decimal


def eligible_subtotal(lines, brand_ids):
    """Sum of the lines a promo applies to. Empty brand_ids — the whole cart."""
    selected = set(brand_ids or [])
    return sum((
        line.product.price * line.qty for line in lines
        if line.product and line.product.is_active and line.qty > 0 and (
            not selected or getattr(line.product, "brand_id", None) in selected
        )
    ), Decimal(0))


def promo_discount(promo, subtotal):
    value = Decimal(str(promo.value))
    if promo.type == "percent":
        value = (subtotal * value / Decimal(100)).quantize(Decimal("0.01"))
    return max(Decimal(0), min(value, subtotal))
