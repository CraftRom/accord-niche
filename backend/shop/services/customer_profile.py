"""Customer card for the dashboard: who the buyer is, what they buy, how to
reach them.

Website buyers have no Telegram name: their name and email come from the
Google account they signed in with (WebsiteAccount.display_name / email).
Statistics cover every proven identity of the customer (Google account,
signed guest sessions, linked Telegram profile) — the same set the order
history uses — and never guess ownership from a phone typed into a form.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, or_, select

from shop import models as m
from shop.entities import OrderStatus
from shop.services import order_business
from shop.services.commerce_workspace import channel_expression
from shop.services.website_identity import _owned_user_ids

CHANNELS = {"website": "Сайт", "miniapp": "Mini App", "bot": "Бот", "unknown": "Невідомо"}


async def accounts_for(repo, user_ids) -> dict[int, m.WebsiteAccount]:
    """Website account of each customer id (own, linked Telegram or alias)."""
    ids = list({int(i) for i in user_ids})
    if not ids:
        return {}
    aliases = dict((await repo.s.execute(select(m.WebsiteAccountUser.user_id, m.WebsiteAccountUser.account_id)
                                          .where(m.WebsiteAccountUser.user_id.in_(ids)))).all())
    rows = (await repo.s.scalars(select(m.WebsiteAccount).where(or_(
        m.WebsiteAccount.user_id.in_(ids), m.WebsiteAccount.linked_telegram_user_id.in_(ids),
        m.WebsiteAccount.id.in_(list(aliases.values()) or [-1]))))).all()
    by_id = {row.id: row for row in rows}
    out = {}
    for row in rows:
        for uid in (row.user_id, row.linked_telegram_user_id):
            if uid in ids:
                out.setdefault(uid, row)
    for uid, account_id in aliases.items():
        if account_id in by_id:
            out.setdefault(uid, by_id[account_id])
    return out


def identity_fields(account) -> dict:
    """Name and email from the social sign-in (Google), never a guess."""
    if account is None:
        return {"display_name": None, "email": None, "google_connected": False}
    google = bool(account.google_sub)
    return {"display_name": (account.display_name or "").strip() or None,
            "email": account.email if google else None, "google_connected": google}


async def enrich(repo, customers) -> list[dict]:
    accounts = await accounts_for(repo, [c.id for c in customers])
    return [{**vars(c), **identity_fields(accounts.get(c.id))} for c in customers]


def _money(value) -> str:
    """Exact amount as a string: JSON floats would lose kopecks."""
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


async def summary(repo, user) -> dict:
    account = (await accounts_for(repo, [user.id])).get(user.id)
    ids = await _owned_user_ids(repo, account) if account else [user.id]
    orders = m.Order.user_id.in_(ids)
    sale = m.Order.business_state == order_business.BUSINESS_SALE
    lost = or_(m.Order.business_state == order_business.BUSINESS_REFUSAL, m.Order.status == OrderStatus.CANCELLED)

    def count_if(condition):
        return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)
    row = (await repo.s.execute(select(
        func.count(m.Order.id), count_if(sale), func.coalesce(func.sum(case((sale, m.Order.total), else_=0)), 0),
        count_if(lost), func.min(m.Order.created_at), func.max(m.Order.created_at),
        func.coalesce(func.sum(case((~lost, m.Order.total), else_=0)), 0),
        count_if(~lost),
    ).where(orders))).one()
    total, sales, revenue, lost_count, first_at, last_at, ordered_sum, ordered_count = row
    channel = channel_expression()
    channels = [{"key": key, "label": CHANNELS.get(key, key), "orders": int(n)} for key, n in
                (await repo.s.execute(select(channel, func.count()).where(orders).group_by(channel)
                                      .order_by(func.count().desc()))).all()]
    kept = (m.Order.business_state != order_business.BUSINESS_REFUSAL) & (m.Order.status != OrderStatus.CANCELLED)
    brand = func.coalesce(func.nullif(func.trim(m.Product.brand), ""), "Без бренду")
    brands = [{"name": name, "qty": int(qty), "amount": _money(amount)} for name, qty, amount in
              (await repo.s.execute(select(brand, func.sum(m.OrderItem.qty), func.sum(m.OrderItem.qty * m.OrderItem.price))
                                    .join(m.Order, m.Order.id == m.OrderItem.order_id)
                                    .outerjoin(m.Product, m.Product.id == m.OrderItem.product_id)
                                    .where(orders, kept).group_by(brand)
                                    .order_by(func.sum(m.OrderItem.qty).desc()).limit(5))).all()]
    products = [{"name": name, "qty": int(qty)} for name, qty in
                (await repo.s.execute(select(m.OrderItem.name, func.sum(m.OrderItem.qty))
                                      .join(m.Order, m.Order.id == m.OrderItem.order_id)
                                      .where(orders, kept).group_by(m.OrderItem.name)
                                      .order_by(func.sum(m.OrderItem.qty).desc()).limit(5))).all()]
    # Chats: order conversations (newest first) and general support threads.
    last_msg = func.max(m.OrderMessage.created_at)
    unread = func.coalesce(func.sum(case(((m.OrderMessage.direction == "in") & (m.OrderMessage.is_read.is_(False)), 1), else_=0)), 0)
    order_chats = [{"order_id": oid, "messages": int(n), "unread": int(u), "last_message_at": at} for oid, n, u, at in
                   (await repo.s.execute(select(m.OrderMessage.order_id, func.count(), unread, last_msg)
                                         .join(m.Order, m.Order.id == m.OrderMessage.order_id).where(orders)
                                         .group_by(m.OrderMessage.order_id).order_by(last_msg.desc()).limit(20))).all()]
    support = [{"id": t.id, "status": t.status, "created_at": t.created_at, "last_message_at": t.last_message_at,
                "closed_at": t.closed_at} for t in
               (await repo.s.scalars(select(m.SupportThread).where(m.SupportThread.user_id.in_(ids))
                                     .order_by(m.SupportThread.id.desc()).limit(20))).all()]
    sales = int(sales)
    return {
        "user_ids": ids,
        **identity_fields(account),
        "verified_phone": account.verified_phone if account else None,
        "telegram_connected": bool(user.tg_id > 0 or (account and account.linked_telegram_user_id)),
        "stats": {
            "orders": int(total), "sales": sales, "lost": int(lost_count),
            "revenue": _money(revenue),
            "average_check": _money(Decimal(str(revenue)) / sales) if sales else None,
            "ordered_sum": _money(ordered_sum),
            "average_order": _money(Decimal(str(ordered_sum)) / int(ordered_count)) if int(ordered_count) else None,
            "first_order_at": first_at, "last_order_at": last_at,
            "bonus_balance": _money(user.bonus_balance),
        },
        "channels": channels, "brands": brands, "products": products,
        "order_chats": order_chats, "support_threads": support,
    }
