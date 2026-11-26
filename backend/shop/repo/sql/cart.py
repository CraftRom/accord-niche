"""Кошик покупця.

Частина SqlRepository (див. shop/repo/sql/__init__.py)."""
from __future__ import annotations

from shop.repo.sql._common import *  # noqa: F401,F403


class CartMixin:
    async def get_cart(self, user_id) -> list[CartLine]:
        rows = await self.s.scalars(
            select(m.CartItem).where(m.CartItem.user_id == user_id)
            .options(selectinload(m.CartItem.product)).order_by(m.CartItem.id)
        )
        rows = list(rows)
        active = await self._parents_active_map([r.product_id for r in rows if r.product is not None])
        return [CartLine(product_id=r.product_id, qty=r.qty,
                         product=_product(r.product, parent_active=active.get(r.product_id, True)))
                for r in rows]

    async def _parents_active_map(self, product_ids) -> dict[int, bool]:
        if not product_ids:
            return {}
        rows = await self.s.execute(select(m.Product.id, _parents_active()).where(m.Product.id.in_(list(product_ids))))
        return {int(pid): bool(ok) for pid, ok in rows}

    async def _row_published(self, product) -> bool:
        """Locked ORM row: individual flag plus parent groups (A08)."""
        if product is None or not product.is_active:
            return False
        return (await self._parents_active_map([product.id])).get(product.id, False)

    async def change_cart_qty_atomic(self, user_id: int, product_id: int, delta: int):
        """Змінює кількість у кошику під row-lock користувача.

        Lock саме User серіалізує також перше додавання, коли CartItem ще
        не існує й його нема чим ``FOR UPDATE`` заблокувати. Це прибирає
        lost-update між двома вкладками/клієнтами одного Telegram акаунта.
        """
        try:
            user_row = await self.s.scalar(
                select(m.User).where(m.User.id == user_id).with_for_update()
            )
            if not user_row:
                await self.s.rollback()
                return None
            product = await self.s.scalar(
                select(m.Product).where(m.Product.id == product_id).with_for_update()
            )
            if delta >= 0 and not await self._row_published(product):
                await self.s.rollback()
                return None
            row = await self.s.scalar(
                select(m.CartItem)
                .where(m.CartItem.user_id == user_id, m.CartItem.product_id == product_id)
                # CartItem.product має lazy=joined. Без явного lazyload SQLAlchemy
                # додає LEFT OUTER JOIN products, а PostgreSQL забороняє
                # FOR UPDATE на nullable-side outer join. Тут product уже
                # заблокований окремим SELECT вище, тому лочимо тільки cart_items.
                .options(lazyload(m.CartItem.product))
                .with_for_update(of=m.CartItem)
            )
            current = int(row.qty) if row else 0
            # Removing an existing line must not depend on catalog activity.
            # Missing/inactive products still have a customer-owned cart row.
            new_qty = max(current + int(delta), 0)
            if await self._row_published(product):
                new_qty = min(new_qty, max(int(product.stock or 0), 0))
            if new_qty <= 0:
                if row:
                    await self.s.delete(row)
            elif row:
                row.qty = new_qty
            else:
                self.s.add(m.CartItem(user_id=user_id, product_id=product_id, qty=new_qty))
            await self.s.commit()
            return new_qty
        except Exception:
            await self.s.rollback()
            raise

    async def set_cart_qty(self, user_id, product_id, qty: int) -> None:
        """Встановлює абсолютну кількість, серіалізуючись з checkout.

        Цей шлях досі використовує Telegram-бот. Lock користувача тут
        обов'язковий: atomic checkout і Mini App +/- беруть той самий lock,
        тому жоден із трьох каналів не може непомітно перетерти кошик іншого.
        """
        try:
            user_row = await self.s.scalar(
                select(m.User).where(m.User.id == user_id).with_for_update()
            )
            if not user_row:
                await self.s.rollback()
                return
            product = await self.s.scalar(
                select(m.Product).where(m.Product.id == product_id).with_for_update()
            )
            row = await self.s.scalar(
                select(m.CartItem)
                .where(m.CartItem.user_id == user_id, m.CartItem.product_id == product_id)
                # CartItem.product має lazy=joined. Без явного lazyload SQLAlchemy
                # додає LEFT OUTER JOIN products, а PostgreSQL забороняє
                # FOR UPDATE на nullable-side outer join. Тут product уже
                # заблокований окремим SELECT вище, тому лочимо тільки cart_items.
                .options(lazyload(m.CartItem.product))
                .with_for_update(of=m.CartItem)
            )
            capped = min(max(int(qty), 0), int(product.stock or 0)) if await self._row_published(product) else 0
            if capped <= 0:
                if row:
                    await self.s.delete(row)
            elif row:
                row.qty = capped
            else:
                self.s.add(m.CartItem(user_id=user_id, product_id=product_id, qty=capped))
            await self.s.commit()
        except Exception:
            await self.s.rollback()
            raise

    async def replace_cart(self, user_id: int, items: list[tuple[int, int]]) -> None:
        """Validate and replace the entire browser cart in one transaction.

        The User lock is also taken by Telegram +/- and checkout, so another
        request cannot observe an empty/partially copied cart. Product rows
        are locked in sorted order, like the stock reservation pipeline.
        """
        product_ids = [pid for pid, _ in items]
        if len(product_ids) != len(set(product_ids)) or not items:
            raise ValueError('Некоректний склад кошика')
        if len(items) > 30 or any(pid <= 0 or qty < 1 or qty > 99 for pid, qty in items):
            raise ValueError('Некоректна кількість товарів')
        try:
            user = await self.s.scalar(select(m.User).where(m.User.id == user_id).with_for_update())
            if user is None:
                raise ValueError('Профіль покупця не знайдено')
            rows = (await self.s.scalars(
                select(m.Product).where(m.Product.id.in_(product_ids))
                .order_by(m.Product.id).with_for_update()
            )).all()
            products = {product.id: product for product in rows}
            parents = await self._parents_active_map(list(products))
            for pid, qty in items:
                product = products.get(pid)
                if not product or not product.is_active or not parents.get(pid) or product.price <= 0:
                    raise ValueError('Деякі товари більше не продаються')
                if int(product.stock or 0) < qty:
                    raise ValueError(f'«{product.name}»: залишилось {product.stock or 0} шт.')
            await self.s.execute(delete(m.CartItem).where(m.CartItem.user_id == user_id))
            self.s.add_all(m.CartItem(user_id=user_id, product_id=pid, qty=qty) for pid, qty in items)
            await self.s.commit()
        except Exception:
            await self.s.rollback()
            raise

    async def clear_cart(self, user_id) -> None:
        """Очищає кошик під тим самим user-lock, що й checkout/+/- qty."""
        try:
            user_row = await self.s.scalar(
                select(m.User).where(m.User.id == user_id).with_for_update()
            )
            if not user_row:
                await self.s.rollback()
                return
            await self.s.execute(delete(m.CartItem).where(m.CartItem.user_id == user_id))
            await self.s.commit()
        except Exception:
            await self.s.rollback()
            raise
