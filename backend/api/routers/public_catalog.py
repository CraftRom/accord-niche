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

from shop.repo.base import Repository
from shop.repo.factory import get_repo

router = APIRouter()

@router.get("/site-config")
async def site_config():
    from shop.links import NAMED_MINIAPP_URL
    from shop.config import settings
    # Explicit configuration only. Never send ACCORD shoppers to legacy ELFAR
    # bot as a silent fallback: no checkout link is safer than the wrong store.
    named_app = (os.getenv("ACCORD_MINIAPP_URL", "") or (
        NAMED_MINIAPP_URL if os.getenv("NAMED_MINIAPP_URL") else ""
    )) if settings.bot_token else ""
    def safe_social(value):
        parts = urlsplit(value)
        return value if parts.scheme == "https" and parts.netloc and not parts.username and not parts.password else ""
    return {
        "miniapp_url": named_app,
        "instagram_url": safe_social(os.getenv("ACCORD_INSTAGRAM_URL", "")),
        "tiktok_url": safe_social(os.getenv("ACCORD_TIKTOK_URL", "")),
        "phone": os.getenv("ACCORD_PHONE", ""),
    }

# Only local product media exposed by this *product-authorized* endpoint.
# It must never become a general purpose /data/media file server.
_LOCAL_MEDIA = re.compile(r"^/media/([a-zA-Z0-9_-]+\.(?:png|jpg|jpeg|webp|gif))$")

def local_product_media_name(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
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
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
            url = None
    return PublicProduct(
        id=p.id, name=p.name, brand=p.brand,
        gender=p.gender or "unisex", volume_ml=p.volume_ml,
        is_featured=p.is_featured, is_new=p.is_new,
        description=p.description, price=p.price,
        stock=p.stock, photo_url=url,
        photo_endpoint=f"/api/public/catalog/{p.id}/photo" if p.photo_file_id or hosted else None,
    )

@router.get("/catalog", response_model=PublicCatalog)
async def catalog(
    limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0),
    repo: Repository = Depends(get_repo),
):
    items = await repo.list_products(only_active=True, perfume_only=True, limit=limit, offset=offset)
    total = await repo.count_products(only_active=True, perfume_only=True)
    return PublicCatalog(items=[public_product(p) for p in items], total=total, limit=limit, offset=offset)

@router.get("/catalog/{product_id}", response_model=PublicProduct)
async def detail(product_id: int, repo: Repository = Depends(get_repo)):
    p = await repo.get_product(product_id)
    if not p or not p.is_active or not p.brand.strip():
        raise HTTPException(404, "Аромат не знайдено")
    return public_product(p)

@router.get("/catalog/{product_id}/photo")
async def photo(product_id: int, repo: Repository = Depends(get_repo)):
    p = await repo.get_product(product_id)
    if not p or not p.is_active or not p.brand.strip():
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
