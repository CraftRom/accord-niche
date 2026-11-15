from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from api.auth import Principal, require_staff
from api.schemas import CustomerOut, CustomerPatch, CustomerPage
from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services import order_business
from shop import models as m
from shop.services.website_identity import _order_time, _owned_user_ids

router = APIRouter(dependencies=[Depends(require_staff)])


@router.get("", response_model=list[CustomerOut] | CustomerPage)
async def list_customers(
    search: str | None = None,
    blocked: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    paginated: bool = False,
    repo: Repository = Depends(get_repo),
):
    items = await repo.list_users(search=search, blocked=blocked, limit=limit, offset=offset)
    if not paginated:
        return items
    total = await repo.count_filtered_users(search=search, blocked=blocked)
    return dict(items=items, total=total, limit=limit, offset=offset,
                has_more=offset + len(items) < total)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def patch_customer(
    customer_id: int, data: CustomerPatch, repo: Repository = Depends(get_repo)
):
    if not await repo.get_user(customer_id):
        raise HTTPException(404, "Клієнта не знайдено")

    if data.is_blocked is not None:
        await repo.set_blocked(customer_id, data.is_blocked)

    if data.bonus_delta:
        await repo.add_bonus(customer_id, data.bonus_delta, data.bonus_reason)

    return await repo.get_user(customer_id)


@router.get("/{customer_id}/wishlists")
async def customer_wishlists(
    customer_id: int,
    repo: Repository = Depends(get_repo),
    who: Principal = Depends(require_staff),
):
    """Що клієнт відклав на потім.

    Менеджеру це потрібно предметно: людина пише в чат «те, що я
    відкладав» — і без цього екрана доводиться перепитувати. Плюс видно,
    чого чекають: якщо товар відкладено десятками людей, це сигнал про
    попит, а не просто список.
    """
    from shop.services import wishlist as wl

    lists = await wl.hydrate(repo, await wl.ensure_lists(repo, customer_id))
    return [
        {
            "id": x.id,
            "name": x.name,
            "size": x.size,
            "products": [
                {"id": p.id, "name": p.name, "price": str(p.price),
                 "photo_url": p.photo_url, "stock": p.stock,
                 "is_active": p.is_active}
                for p in x.products
            ],
        }
        for x in lists
    ]


async def _website_identity(repo: Repository, user_id: int):
    # Staff-only identity lookup: join records only when the customer
    # authenticated through Google, a signed guest session or Telegram proof.
    # Never infer ownership from an order's recipient phone number.
    alias_account_ids = select(m.WebsiteAccountUser.account_id).where(
        m.WebsiteAccountUser.user_id == user_id
    )
    return await repo.s.scalar(select(m.WebsiteAccount).where(or_(
        m.WebsiteAccount.user_id == user_id,
        m.WebsiteAccount.linked_telegram_user_id == user_id,
        m.WebsiteAccount.id.in_(alias_account_ids),
    )).limit(1))


@router.get("/{customer_id}/identity")
async def customer_identity(customer_id: int, repo: Repository = Depends(get_repo)):
    if not await repo.get_user(customer_id):
        raise HTTPException(404, 'Клієнта не знайдено')
    account = await _website_identity(repo, customer_id)
    if account is None:
        return {'linked': False, 'user_ids': [customer_id]}
    ids = await _owned_user_ids(repo, account)
    return {
        'linked': True,
        'user_ids': ids,
        'google_connected': bool(account.google_sub),
        'email': account.email if account.google_sub else None,
        'verified_phone': account.verified_phone,
        'telegram_connected': bool(account.linked_telegram_user_id),
        'note': 'Історія покупок об’єднана для перегляду. Бонусні рахунки різних user_id не переносяться автоматично.',
    }


@router.get("/{customer_id}/orders")
async def customer_orders(customer_id: int, limit: int = Query(200, ge=1, le=500),
                          offset: int = Query(0, ge=0), paginated: bool = False,
                          repo: Repository = Depends(get_repo)):
    if not await repo.get_user(customer_id):
        raise HTTPException(404, 'Клієнта не знайдено')
    account = await _website_identity(repo, customer_id)
    ids = await _owned_user_ids(repo, account) if account else [customer_id]
    # Bounded per-source fetch to merge a deterministic page. Order owner IDs
    # remain unchanged for accounting, only the read model is unified.
    orders = []
    for uid in ids:
        orders.extend(await repo.list_orders(user_id=uid, limit=offset + limit + 1, offset=0))
    orders.sort(key=lambda o: (_order_time({'created_at': o.created_at}), o.id), reverse=True)
    orders = orders[offset:offset + limit]
    items = [
        {
            "id": o.id, "status": o.status.value, "total": o.total,
            "crm_id": o.crm_id, "crm_status_id": o.crm_status_id,
            "crm_status_name": order_business.effective_crm_status_name(o) or None,
            "business_state": order_business.derive_business_state(o),
            "crm_fetched_at": o.crm_fetched_at,
            "created_at": o.created_at,
            "items": [{"name": ln.name, "qty": ln.qty, "price": ln.price} for ln in o.items],
        }
        for o in orders
    ]

    if not paginated:
        return items
    total = sum([await repo.count_filtered_orders(user_id=uid) for uid in ids])
    return dict(items=items, total=total, limit=limit, offset=offset,
                has_more=offset + len(items) < total)
