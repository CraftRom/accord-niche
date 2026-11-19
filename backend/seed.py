"""Наповнює каталог демо-даними.

    docker compose -f docker-compose.prod.yml exec api python seed.py
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from shop.entities import PromoType
from shop.repo.factory import open_repo

# Демо-каталог парфумерії на розпив: бренд → аромати (назва, опис, ціна, залишок, мл).
CATALOG = {
    "Creed": [
        ("Aventus 5 мл", "Ананас, береза, мускус. Розпив з оригінального флакона", 650, 10, 5),
        ("Aventus 10 мл", "Ананас, береза, мускус. Розпив з оригінального флакона", 1200, 6, 10),
    ],
    "Kilian": [
        ("Angels' Share 5 мл", "Коньяк, кориця, ваніль", 720, 8, 5),
    ],
    "Nasomatto": [
        ("Black Afgano 2 мл", "Смоли, тютюн, кава", 380, 12, 2),
    ],
    "Amouage": [
        ("Interlude Man 5 мл", "Ладан, амбра, шкіра", 690, 7, 5),
    ],
}

PROMOS = [
    {"code": "WELCOME10", "type": PromoType.PERCENT, "value": Decimal(10),
     "min_order": Decimal(500), "max_uses": None, "per_user_limit": 1},
    {"code": "OPT500", "type": PromoType.FIXED, "value": Decimal(500),
     "min_order": Decimal(5000), "max_uses": 50, "per_user_limit": 3},
]


async def main() -> None:
    from shop.db import init_db

    await init_db()

    async with open_repo() as repo:
        if await repo.list_products(limit=1) or await repo.list_brands():
            print("У базі вже є дані — сідинг пропущено.")
            return

        for name, products in CATALOG.items():
            brand = await repo.create_brand({"name": name, "is_active": True})
            for p_order, (p_name, description, price, stock, volume) in enumerate(products):
                await repo.create_product({
                    "brand_id": brand.id, "name": p_name, "volume_ml": volume,
                    "description": description, "price": Decimal(price),
                    "stock": stock, "sort_order": p_order, "is_active": True,
                })

        for promo in PROMOS:
            await repo.create_promo(promo | {"is_active": True})

        print(f"Готово: {len(CATALOG)} брендів, {len(PROMOS)} промокоди "
              "(база: Postgres).")


if __name__ == "__main__":
    asyncio.run(main())
