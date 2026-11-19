"""Unauthenticated, read-only, deliberately minimal product feed for ACCORD NICHE.

No private analytics, internal SKU, supplier documents, customer data, bot token
or manager details are exposed. All public operations are GET.
"""
from __future__ import annotations
from decimal import Decimal
from urllib.parse import urlsplit
import re
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Literal

from shop.repo.base import Repository
from shop.repo.factory import get_repo

router = APIRouter()

@router.get("/site-config")
async def site_config(repo: Repository = Depends(get_repo)):
    from shop.links import NAMED_MINIAPP_URL
    from shop.config import settings
    from shop.services.shop_settings import get_shop_settings
    shop = await get_shop_settings(repo)
    # Explicit configuration only. Never send ACCORD shoppers to legacy ELFAR
    # bot as a silent fallback: no checkout link is safer than the wrong store.
    named_app = (shop.site("miniapp_url") or (
        NAMED_MINIAPP_URL if os.getenv("NAMED_MINIAPP_URL") else ""
    )) if settings.bot_token else ""
    def safe_social(value):
        try:
            parts = urlsplit(value)
        except ValueError:
            return ''
        return value if parts.scheme == "https" and parts.netloc and not parts.username and not parts.password else ""
    return {
        "miniapp_url": named_app,
        "instagram_url": safe_social(shop.site("instagram_url")),
        "tiktok_url": safe_social(shop.site("tiktok_url")),
        "phone": shop.seller_phone or os.getenv("ACCORD_PHONE", ""),
        "seller_name": shop.seller_name,
        "email": shop.seller_email,
        # W-10: purchase terms and privacy policy are the owner's documents.
        # They appear next to the checkout consent only when configured; the
        # site never invents legal text.
        "terms_url": safe_social(shop.site("terms_url")),
        "privacy_url": safe_social(shop.site("privacy_url")),
    }

# Only local product media exposed by this *product-authorized* endpoint.
# It must never become a general purpose /data/media file server.
_LOCAL_MEDIA = re.compile(r"^/media/([a-zA-Z0-9_-]+\.(?:png|jpg|jpeg|webp|gif))$")

def local_product_media_name(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        return None
    m = _LOCAL_MEDIA.fullmatch(parts.path)
    return m.group(1) if m else None

class PublicProduct(BaseModel):
    id: int
    name: str
    brand: str
    gender: str
    volume_ml: int | None
    is_featured: bool
    is_new: bool
    description: str | None
    price: Decimal
    stock: int
    photo_url: str | None
    photo_endpoint: str | None
    old_price: Decimal | None = None
    is_sale: bool = False

class PublicCatalog(BaseModel):
    items: list[PublicProduct]
    total: int
    limit: int
    offset: int


def public_product(p):
    url = p.photo_url
    hosted = local_product_media_name(url)
    if hosted:
        # Return the gated photo endpoint, not the raw /media path.
        url = None
    # Avoid browser execution and malformed/non-HTTPS external sources.
    if url:
        try:
            parts = urlsplit(url)
        except ValueError:
            url = None
        else:
            if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
                url = None
    return PublicProduct(
        id=p.id, name=p.name, brand=p.brand,
        gender=p.gender or "unisex", volume_ml=p.volume_ml,
        is_featured=p.is_featured, is_new=p.is_new,
        description=p.description, price=p.price,
        stock=p.stock, photo_url=url,
        photo_endpoint=f"/api/public/catalog/{p.id}/photo" if p.photo_file_id or hosted else None,
        old_price=p.old_price if p.old_price and p.old_price > p.price else None,
        is_sale=bool(p.is_sale and p.old_price and p.old_price > p.price),
    )

@router.get("/catalog", response_model=PublicCatalog)
async def catalog(
    limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
    repo: Repository = Depends(get_repo),
):
    items = await repo.list_products(only_active=True, limit=limit, offset=offset)
    total = await repo.count_products(only_active=True)
    return PublicCatalog(items=[public_product(p) for p in items], total=total, limit=limit, offset=offset)

@router.get("/catalog/{product_id}", response_model=PublicProduct)
async def detail(product_id: int, repo: Repository = Depends(get_repo)):
    p = await repo.get_product(product_id)
    if not p or not p.is_published or p.price <= 0:
        raise HTTPException(404, "Аромат не знайдено")
    return public_product(p)

@router.get("/catalog/{product_id}/photo")
async def photo(product_id: int, repo: Repository = Depends(get_repo)):
    p = await repo.get_product(product_id)
    if not p or not p.is_published:
        raise HTTPException(404, "Фото немає")
    local_name = local_product_media_name(p.photo_url)
    if local_name:
        from fastapi.responses import FileResponse
        from shop.paths import media_dir
        path = media_dir() / local_name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, "Фото немає")
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else {
            ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"
        }.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=mime, headers={
            "Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})
    if not p.photo_file_id:
        raise HTTPException(404, "Фото немає")
    from shop.config import settings
    if not settings.bot_token:
        raise HTTPException(503, "Фото Telegram доступне після налаштування бота")
    from api.routers.orders import _bot
    from shop.services.product_media import telegram_product_photo
    bot = _bot()
    if not bot:
        raise HTTPException(503, "Фото тимчасово недоступне")
    try:
        content = await telegram_product_photo(bot, p.photo_file_id)
    except Exception:
        raise HTTPException(502, "Фото тимчасово недоступне") from None
    data = content.read() if hasattr(content, "read") else content
    # Limit transfer to prevent memory exhaustion if Telegram serves a huge file.
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Фото завелике")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control":"public, max-age=3600", "X-Content-Type-Options":"nosniff"})


class PublicAroma(BaseModel):
    id: int
    default_product_id: int
    key: str
    name: str
    brand: str
    gender: str
    description: str
    variants: list[PublicProduct]
    categories: list[dict]
    stock: int
    min_price: Decimal
    price_per_ml: Decimal | None
    image: str
    volumes: list[int]
    is_new: bool
    is_featured: bool
    is_set: bool
    bestseller_rank: int | None


class AromaPage(BaseModel):
    items: list[PublicAroma]
    total: int
    limit: int
    offset: int
    brands: list[str]
    categories: list[dict]
    volumes: list[int]
    updated_at: str


class Storefront(BaseModel):
    hits: list[PublicAroma]
    recommended: list[PublicAroma]
    new_arrivals: list[PublicAroma]
    selection: list[PublicAroma]
    total: int
    available: int
    window_days: int
    updated_at: str


@router.get('/storefront', response_model=Storefront)
async def storefront(response: Response, repo: Repository = Depends(get_repo)):
    from shop.services.storefront import snapshot, sorted_groups, WINDOW_DAYS
    data = await snapshot(repo, public_product)
    groups = data['groups']
    available = [g for g in groups if g['stock'] > 0]
    response.headers['Cache-Control'] = 'no-store'
    return Storefront(
        hits=[g for g in sorted_groups(available, 'popular') if g['bestseller_rank']][:8],
        recommended=[g for g in sorted_groups(available) if g['is_featured']][:8],
        new_arrivals=[g for g in sorted_groups(available, 'new') if g['is_new']][:8],
        selection=sorted_groups(available or groups)[:8], total=len(groups), available=len(available),
        window_days=WINDOW_DAYS, updated_at=data['updated_at'])


@router.get('/aromas', response_model=AromaPage)
async def aromas(
    response: Response, q: str = Query('', max_length=120), brand: str = Query('', max_length=100),
    gender: Literal['', 'male', 'female', 'unisex'] = '', category: int | None = Query(None, gt=0),
    available: bool = False, volume: int | None = Query(None, gt=0, le=10000),
    kind: Literal['all', 'sets', 'new', 'hits', 'recommended'] = 'all',
    sort: Literal['recommended', 'popular', 'new', 'price_asc', 'price_desc', 'name'] = 'recommended',
    limit: int = Query(24, ge=1, le=48), offset: int = Query(0, ge=0),
    repo: Repository = Depends(get_repo),
):
    from shop.services.storefront import snapshot, sorted_groups
    data = await snapshot(repo, public_product)
    all_groups = data['groups']
    needle = q.strip().casefold()
    groups = [g for g in all_groups if
        (not needle or needle in (g['brand'] + ' ' + g['name']).casefold()) and
        (not brand or g['brand'] == brand) and (not gender or g['gender'] == gender) and
        (not category or any(c['id'] == category for c in g['categories'])) and
        (not available or g['stock'] > 0) and
        (not volume or any(p.volume_ml == volume and (not available or p.stock > 0) for p in g['variants'])) and
        (kind != 'sets' or g['is_set']) and (kind != 'new' or g['is_new']) and
        (kind != 'hits' or g['bestseller_rank'] is not None) and
        (kind != 'recommended' or g['is_featured'])]
    if volume:
        # A 10 ml filter must not advertise the unrelated 2 ml starting price.
        # Copy groups: snapshot is cached and also serves the unfiltered store.
        selected=[]
        for group in groups:
            variants=[p for p in group['variants'] if p.volume_ml == volume]
            buyable=[p for p in variants if p.stock > 0]
            priced=buyable or variants
            choice=min(priced,key=lambda p:(p.price,p.id))
            selected.append({**group,'default_product_id':choice.id,'variants':variants,
                'stock':sum(max(0,p.stock) for p in variants),
                'min_price':choice.price,'price_per_ml':choice.price/volume,'volumes':[volume],
                'image':next((p.photo_url or p.photo_endpoint for p in priced if p.photo_url or p.photo_endpoint),group['image'])})
        groups=selected
    groups = sorted_groups(groups, 'popular' if kind == 'hits' else sort)
    categories = {c['id']: c for g in all_groups for c in g['categories']}
    response.headers['Cache-Control'] = 'no-store'
    return AromaPage(items=groups[offset:offset+limit], total=len(groups), limit=limit, offset=offset,
        brands=sorted({g['brand'] for g in all_groups if g['brand']}, key=str.casefold),
        categories=sorted(categories.values(), key=lambda c: c['name'].casefold()),
        volumes=sorted({v for g in all_groups for v in g['volumes']}), updated_at=data['updated_at'])


class AromaDetail(BaseModel):
    item: PublicAroma
    related: list[PublicAroma]


@router.get('/aromas/{product_id}', response_model=AromaDetail)
async def aroma_detail(product_id: int, response: Response, repo: Repository = Depends(get_repo)):
    from shop.services.storefront import snapshot, sorted_groups
    groups = (await snapshot(repo, public_product))['groups']
    group = next((g for g in groups if any(p.id == product_id for p in g['variants'])), None)
    if group is None:
        raise HTTPException(404, 'Товар не знайдено')
    related = [g for g in groups if g['key'] != group['key'] and g['stock'] > 0 and
               ((group['brand'] and g['brand'] == group['brand']) or g['gender'] == group['gender'])]
    response.headers['Cache-Control'] = 'no-store'
    return AromaDetail(item=group, related=sorted_groups(related)[:4])


@router.get('/products', response_model=list[PublicProduct])
async def cart_products(ids: str = Query('', max_length=600), repo: Repository = Depends(get_repo)):
    if not ids:
        return []
    if not re.fullmatch(r'[1-9][0-9]{0,18}(?:,[1-9][0-9]{0,18}){0,29}', ids):
        raise HTTPException(422, 'Дозволено до 30 ідентифікаторів товарів')
    selected = {int(value) for value in ids.split(',')}
    if max(selected) > 2**31 - 1:
        raise HTTPException(422, 'Некоректний ідентифікатор товару')
    products = await repo.products_by_ids(list(selected))
    return [public_product(p) for p in products if p.is_published and p.price > 0]
