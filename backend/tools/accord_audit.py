"""Read-only by default: audit identity links, sales counters and expiring sessions.

Inside the ACCORD backend container (after migrations):
  python -m tools.accord_audit
  python -m tools.accord_audit --cleanup-expired   # opt-in, deletes expired tokens only

Does not expose customer PII, does not reassign an order or edit stock/bonuses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select

from shop import models as m


def _sale_mismatches():
    """Counters are *completed sales*, not total placed orders."""
    sales = (select(m.Order.user_id.label('uid'),
                    func.count(m.Order.id).label('count'),
                    func.coalesce(func.sum(m.Order.total), 0).label('spent'))
             .where(m.Order.business_state == 'sale')
             .group_by(m.Order.user_id).subquery())
    expected_count = func.coalesce(sales.c.count, 0)
    expected_spent = func.coalesce(sales.c.spent, 0)
    return (select(func.count(m.User.id))
            .outerjoin(sales, sales.c.uid == m.User.id)
            .where(or_(m.User.orders_count != expected_count,
                       m.User.total_spent != expected_spent)))


async def inspect_db(cleanup=False) -> dict:
    from shop.db import SessionMaker
    now = datetime.now(timezone.utc)
    async with SessionMaker() as session:
        stale_sessions = int(await session.scalar(select(func.count()).select_from(m.WebsiteSession)
                                                  .where(m.WebsiteSession.expires_at <= now)) or 0)
        stale_links = int(await session.scalar(select(func.count()).select_from(m.WebsiteTelegramLink)
                                               .where(m.WebsiteTelegramLink.expires_at <= now)) or 0)
        aliases = int(await session.scalar(select(func.count()).select_from(m.WebsiteAccountUser)) or 0)
        linked_telegram = int(await session.scalar(select(func.count()).select_from(m.WebsiteAccount)
                                                      .where(m.WebsiteAccount.linked_telegram_user_id.is_not(None))) or 0)
        wrong_alias_kind = int(await session.scalar(
            select(func.count()).select_from(m.WebsiteAccountUser)
            .join(m.User, m.User.id == m.WebsiteAccountUser.user_id)
            .where(m.User.tg_id > 0)) or 0)
        drift = int(await session.scalar(_sale_mismatches()) or 0)
        negative_stock = int(await session.scalar(select(func.count()).select_from(m.Product)
                                                  .where(m.Product.stock < 0)) or 0)
        report = {
            'website_guest_aliases': aliases,
            'website_telegram_links_verified': linked_telegram,
            'unexpected_positive_telegram_guest_aliases': wrong_alias_kind,
            'users_with_sales_counter_mismatch': drift,
            'products_with_negative_stock': negative_stock,
            'expired_browser_sessions': stale_sessions,
            'expired_unused_telegram_codes': stale_links,
            'changed_data': False,
        }
        if cleanup:
            # Expired tokens can never authenticate. No user/order/stock edits.
            await session.execute(delete(m.WebsiteSession).where(m.WebsiteSession.expires_at <= now))
            await session.execute(delete(m.WebsiteTelegramLink).where(m.WebsiteTelegramLink.expires_at <= now))
            await session.commit()
            report['changed_data'] = True
            report['deleted_expired_browser_sessions'] = stale_sessions
            report['deleted_expired_telegram_codes'] = stale_links
        return report


def main():
    cli = argparse.ArgumentParser(description='ACCORD identity, sales & token audit')
    cli.add_argument('--cleanup-expired', action='store_true',
                     help='Only prune expired session/Telegram link tokens; never fix customer totals automatically')
    args = cli.parse_args()
    print(json.dumps(asyncio.run(inspect_db(cleanup=args.cleanup_expired)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
