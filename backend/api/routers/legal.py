"""Публічна оферта й політика конфіденційності: редагування в панелі
(адміністратор) і публічне читання для сайту та Mini App."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from api.auth import Principal, require_admin
from shop import security_log as security
from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services import legal
from shop.services.shop_settings import get_shop_settings

admin = APIRouter(dependencies=[Depends(require_admin)])
public = APIRouter()
Key = Literal["terms", "privacy"]


class LegalIn(BaseModel):
    # Порожній текст — повернутися до початкового шаблону.
    body: str = Field("", max_length=legal.MAX_BODY)


@admin.get("")
async def list_documents(repo: Repository = Depends(get_repo)):
    shop = await get_shop_settings(repo)
    items = [await legal.read(repo, key) for key in legal.KEYS]
    return {"items": items, "seller_ready": legal.seller_ready(shop),
            "defaults": {key: legal.DEFAULTS[key].strip() + "\n" for key in legal.KEYS}}


@admin.put("/{key}")
async def save_document(key: Key, data: LegalIn, who: Principal = Depends(require_admin),
                        repo: Repository = Depends(get_repo)):
    saved = await legal.save(repo, key, data.body, who.login)
    security.record("security.settings.changed", actor=who.login, role=who.role.value,
                    reason=f"документ: {key}" + (" (початковий шаблон)" if saved["is_default"] else ""))
    return saved


@admin.post("/{key}/preview")
async def preview(key: Key, data: LegalIn, repo: Repository = Depends(get_repo)):
    """Текст із підставленими реквізитами — як його побачить покупець."""
    shop = await get_shop_settings(repo)
    document = await legal.read(repo, key)
    document["body"] = data.body.strip() or legal.DEFAULTS[key]
    return {"body": legal.render(document, shop)}


@public.get("/legal/{key}")
async def public_document(key: Key, response: Response, repo: Repository = Depends(get_repo)):
    shop = await get_shop_settings(repo)
    document = await legal.read(repo, key)
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"key": key, "title": document["title"], "body": legal.render(document, shop),
            "updated_at": document["updated_at"], "seller_ready": legal.seller_ready(shop)}
