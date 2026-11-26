"""Каталог: бренди, товари, вітрина, залишки.

Частина SqlRepository (див. shop/repo/sql/__init__.py)."""
from __future__ import annotations

from shop.repo.sql._common import *  # noqa: F401,F403


class CatalogMixin:
    @staticmethod
    def _filters(query, brand_id=None, search=None,
                 only_active=False, is_new=None, is_sale=None, without_brand=False, perfume_only=False, inventory=None):
        if inventory:
            sellable=and_(_published(),m.Product.price>0,func.trim(m.Product.name)!='')
            conditions={
                'available':and_(sellable,m.Product.stock>0),
                'low':and_(sellable,m.Product.stock>0,m.Product.stock<=3),
                'out':and_(sellable,m.Product.stock<=0),
                'unpriced':and_(_published(),m.Product.price<=0),
                # Hidden on the storefront: individually or through a hidden brand.
                'hidden':not_(_published()),
                'missing_photos':and_(sellable,func.trim(func.coalesce(m.Product.photo_url,''))=='',func.trim(func.coalesce(m.Product.photo_file_id,''))=='')}
            query=query.where(conditions[inventory])
        if brand_id is not None:
            query = query.where(m.Product.brand_id == brand_id)
        if without_brand:
            query = query.where(m.Product.brand_id.is_(None))
        if search:
            query = query.where(or_(m.Product.name_lower.contains(search.lower(), autoescape=True),
                                   m.Product.brand.icontains(search, autoescape=True),
                                   m.Product.sku.icontains(search, autoescape=True),
                                   m.Product.external_sku.icontains(search, autoescape=True)))
        if only_active:
            query = query.where(_published())
        if perfume_only:
            query = query.where(func.trim(m.Product.brand) != "")
        if is_new is not None:
            query = query.where(m.Product.is_new.is_(is_new))
        if is_sale is not None:
            query = query.where(m.Product.is_sale.is_(is_sale))
        return query

    async def list_brands(self, only_active=False) -> list[Brand]:
        count = select(func.count(m.Product.id)).where(m.Product.brand_id == m.Brand.id).correlate(m.Brand).scalar_subquery()
        query = select(m.Brand, count).order_by(m.Brand.sort_order, m.Brand.name_key)
        if only_active:
            query = query.where(m.Brand.is_active.is_(True))
        return [_brand(row, cnt) for row, cnt in await self.s.execute(query)]

    async def get_brand(self, brand_id):
        row = await self.s.get(m.Brand, brand_id)
        if not row:
            return None
        count = await self.s.scalar(select(func.count(m.Product.id)).where(m.Product.brand_id == brand_id))
        return _brand(row, int(count or 0))

    async def _brand_by_key(self, name):
        return await self.s.scalar(select(m.Brand).where(m.Brand.name_key == _brand_key(name).lower()))

    async def create_brand(self, data):
        name = _brand_key(data.get("name"))
        if not name:
            raise ValueError("Назва бренду не може бути порожньою")
        if await self._brand_by_key(name):
            raise ValueError(f"Бренд «{name}» уже є")
        row = m.Brand(name=name, name_key=name.lower(), description=data.get("description"),
                      sort_order=int(data.get("sort_order") or 0), is_active=bool(data.get("is_active", True)))
        self.s.add(row)
        try:
            await self.s.commit()
        except IntegrityError:
            await self.s.rollback()
            raise ValueError(f"Бренд «{name}» уже є") from None
        return await self.get_brand(row.id)

    async def update_brand(self, brand_id, data):
        row = await self.s.get(m.Brand, brand_id)
        if not row:
            return None
        if "name" in data:
            name = _brand_key(data["name"])
            if not name:
                raise ValueError("Назва бренду не може бути порожньою")
            other = await self._brand_by_key(name)
            if other is not None and other.id != brand_id:
                raise ValueError(f"Бренд «{name}» уже є")
            row.name, row.name_key = name, name.lower()
            # The products keep a copy of the name for the site, search and SEO.
            await self.s.execute(update(m.Product).where(m.Product.brand_id == brand_id).values(brand=name))
        for key in ("description", "sort_order", "is_active"):
            if key in data:
                setattr(row, key, data[key])
        await self.s.commit()
        return await self.get_brand(brand_id)

    async def delete_brand(self, brand_id):
        row = await self.s.get(m.Brand, brand_id)
        if not row:
            return False
        if await self.s.scalar(select(func.count(m.Product.id)).where(m.Product.brand_id == brand_id)):
            raise ValueError("У бренду є товари: перенесіть їх до іншого бренду або приховайте бренд")
        await self.s.delete(row)
        await self.s.commit()
        return True

    async def ensure_brand(self, name):
        name = _brand_key(name)
        if not name:
            return None
        row = await self._brand_by_key(name)
        if row is None:
            row = m.Brand(name=name, name_key=name.lower(), sort_order=0, is_active=True)
            self.s.add(row)
            try:
                await self.s.flush()
            except IntegrityError:
                await self.s.rollback()
                row = await self._brand_by_key(name)
        return _brand(row) if row else None

    async def list_products(self, brand_id=None, search=None, only_active=False, limit=500, offset=0,
                            is_new=None, is_sale=None, without_brand=False, perfume_only=False,
                            inventory=None,sort=None):
        query = select(m.Product, _parents_active())
        query = self._filters(query, brand_id, search, only_active, is_new, is_sale, without_brand, perfume_only,inventory)
        ordering={'name-asc':m.Product.name.asc(),'name-desc':m.Product.name.desc(),
            'price-asc':m.Product.price.asc(),'price-desc':m.Product.price.desc(),
            'stock-asc':m.Product.stock.asc(),'stock-desc':m.Product.stock.desc()}
        columns=[ordering[sort],m.Product.id] if sort else [m.Product.sort_order,m.Product.name,m.Product.id]
        query=query.order_by(*columns).limit(limit).offset(offset)
        return [_product(row, active) for row, active in await self.s.execute(query.execution_options(populate_existing=True))]

    async def storefront_data(self, since, until):
        # Count commercial sales, never unpaid reservations, refusals or clicks.
        event = func.coalesce(m.Order.business_state_at, m.Order.created_at)
        sales = await self.s.execute(
            select(m.OrderItem.product_id, func.sum(m.OrderItem.qty))
            .join(m.Order, m.Order.id == m.OrderItem.order_id)
            .where(m.Order.business_state == business.BUSINESS_SALE,
                   event >= since, event < until, m.OrderItem.product_id.is_not(None),
                   m.OrderItem.qty > 0)
            .group_by(m.OrderItem.product_id)
        )
        query = (select(m.Product, _parents_active())
                 .where(_published(), m.Product.price > 0)
                 .order_by(m.Product.sort_order, m.Product.name, m.Product.id))
        products = [_product(row, active) for row, active in await self.s.execute(query)]
        return products, {int(pid): int(qty) for pid, qty in sales}

    async def products_by_ids(self, ids):
        if not ids:
            return []
        query = select(m.Product, _parents_active()).where(m.Product.id.in_(list(ids)))
        return [_product(row, active) for row, active in await self.s.execute(query.execution_options(populate_existing=True))]

    async def count_products(self, brand_id=None, only_active=True, **filters):
        query = self._filters(select(func.count(m.Product.id)), brand_id=brand_id, only_active=only_active, **filters)
        return await self.s.scalar(query) or 0

    async def get_product(self, product_id):
        rows = await self.products_by_ids([product_id])
        return rows[0] if rows else None

    async def _resolve_brand(self, data):
        """brand_id is the link; brand (name) is its copy for the site.

        A product saved with a brand id gets that brand's name; one saved with
        only a name (XLSX import, old clients) gets the brand of that name,
        created when it does not exist yet. An empty name clears the brand.
        """
        if data.get("brand_id") is not None:
            row = await self.s.get(m.Brand, data["brand_id"])
            if not row:
                raise ValueError("Такого бренду немає")
            data["brand"] = row.name
        elif "brand" in data:
            brand = await self.ensure_brand(data.get("brand"))
            data["brand_id"] = brand.id if brand else None
            data["brand"] = brand.name if brand else ""
        return data

    async def _validate_product(self, data):
        if data.get("is_sale") and (data.get("old_price") is None or Decimal(str(data["old_price"])) <= Decimal(str(data["price"]))):
            raise ValueError("Для акції стара ціна має бути більшою за поточну")
        for key in ("price", "old_price", "stock"):
            if data.get(key) is not None and Decimal(str(data[key])) < 0:
                raise ValueError("Ціна й залишок не можуть бути від’ємними")

    async def create_product(self, data):
        from shop.services.product_io import generate_sku
        data = dict(data)
        supplied = data.pop("sku", None)
        if supplied and not data.get("external_sku"):
            data["external_sku"] = str(supplied)[:255]
        data.setdefault("is_sale", bool(data.get("old_price") is not None and data["old_price"] > data["price"]))
        await self._validate_product(data)
        await self._resolve_brand(data)
        data["name_lower"] = data["name"].lower()
        for attempt in range(5):
            data["sku"] = await generate_sku(self, data.get("brand") or "GEN")
            row = m.Product(**data)
            self.s.add(row)
            try:
                await self.s.commit()
                return await self.get_product(row.id)
            except IntegrityError as exc:
                await self.s.rollback()
                if "sku" not in str(exc).lower() or attempt == 4:
                    raise
        raise RuntimeError("Не вдалося створити товар")

    async def get_product_by_sku(self, sku):
        row = await self.s.scalar(select(m.Product).where(m.Product.sku == sku.strip().upper()))
        return await self.get_product(row.id) if row else None

    async def get_product_by_external_sku(self, sku):
        rows = list(await self.s.scalars(select(m.Product.id).where(func.trim(m.Product.external_sku) == sku.strip()).limit(2)))
        if len(rows) > 1:
            raise ValueError("Зовнішній артикул неоднозначний — використайте системний SKU")
        return await self.get_product(rows[0]) if rows else None

    async def update_product(self, product_id, data):
        row = await self.s.get(m.Product, product_id)
        if not row:
            return None
        data = dict(data)
        data.pop("sku", None)  # The system article is immutable.
        merged = {key: getattr(row, key) for key in ("price", "old_price", "stock", "is_sale")}
        merged.update(data)
        await self._validate_product(merged)
        if "brand_id" in data or "brand" in data:
            await self._resolve_brand(data)
        for key, value in data.items():
            setattr(row, key, value)
        if "name" in data:
            row.name_lower = data["name"].lower()
        await self.s.commit()
        return await self.get_product(product_id)

    async def adjust_stock(self, product_id, delta: int) -> Product | None:
        # Відʼємний зсув — це резерв товару, а не просто «не піти в мінус».
        # Старий CASE(stock + delta, 0) дозволяв двом одночасним checkout
        # обом пройти перевірку залишку: другий теж створював замовлення,
        # а склад просто затискався в нуль. Тепер UPDATE виконується лише
        # якщо потрібна кількість реально ще є.
        query = update(m.Product).where(m.Product.id == product_id)
        if delta < 0:
            query = query.where(m.Product.stock >= -delta)
        result = await self.s.execute(query.values(stock=_not_below_zero(m.Product.stock + delta)))
        await self._commit()
        if not result.rowcount:
            return None
        return await self.get_product(product_id)

    async def set_stock(self, product_id, stock: int) -> Product | None:
        row = await self.s.get(m.Product, product_id)
        if not row:
            return None
        row.stock = max(0, stock)
        await self.s.commit()
        return await self.get_product(product_id)

    async def count_low_stock(self, threshold=5) -> int:
        return await self.s.scalar(
            select(func.count(m.Product.id))
            .where(m.Product.is_active.is_(True), m.Product.stock < threshold)
        ) or 0
