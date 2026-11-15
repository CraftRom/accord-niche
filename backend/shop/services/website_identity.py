"""Identity reconciliation for ACCORD website and Telegram customers.

Sharing one database does not imply rewriting order owners. An order, its
bonuses and counters must keep the original customer ID so reporting remains
consistent; an account may have multiple proven identities.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select, delete
from fastapi import HTTPException
from shop import models as m
from shop.repo.base import Repository


async def _owned_user_ids(repo: Repository, account: m.WebsiteAccount) -> list[int]:
    """One customer's proven identities; never match on unverified phone/email."""
    ids = {account.user_id}
    aliases = await repo.s.scalars(select(m.WebsiteAccountUser.user_id).where(
        m.WebsiteAccountUser.account_id == account.id))
    ids.update(aliases.all())
    if account.linked_telegram_user_id:
        ids.add(account.linked_telegram_user_id)
    return sorted(ids)


def _order_time(order: dict) -> float:
    value = order.get('created_at')
    if not isinstance(value, datetime):
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


async def attach_guest_identity(repo: Repository, account: m.WebsiteAccount,
                                guest: m.WebsiteAccount) -> None:
    """Bind guest purchase history only when caller has the guest's session.

    This transaction is committed by the caller together with Google identity
    update + session rotation. A prior mapping to another account is a hard
    conflict, never an implicit transfer of purchase history.
    """
    if guest.id == account.id or guest.google_sub or guest.user_id == account.user_id:
        raise HTTPException(409, 'Цей профіль не є гостьовим')
    old = await repo.s.scalar(select(m.WebsiteAccountUser).where(
        m.WebsiteAccountUser.user_id == guest.user_id
    ))
    if old and old.account_id != account.id:
        raise HTTPException(409, 'Історію гостя вже привʼязано до іншого профілю')
    if not old:
        repo.s.add(m.WebsiteAccountUser(account_id=account.id, user_id=guest.user_id))
        await repo.s.flush()
    await repo.s.execute(delete(m.WebsiteSession).where(m.WebsiteSession.account_id == guest.id))
    await repo.s.delete(guest)
