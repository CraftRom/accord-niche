"""Public SEO endpoints of the main website: per-URL <head> tags and sitemap."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response

from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services import seo

router = APIRouter()


@router.get("/head", include_in_schema=False)
async def head(path: str = Query("/", max_length=600),
               x_accord_path: str | None = Header(None, max_length=600),
               repo: Repository = Depends(get_repo)):
    """HTML fragment for the SSI include in index.html (no JavaScript needed).

    Nginx passes the visitor's original URI in X-Accord-Path; ``path`` is for
    manual checks. Only public, published data is ever rendered.
    """
    body = await seo.head_for(repo, x_accord_path or path)
    return Response(body, media_type="text/html; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=60", "X-Robots-Tag": "noindex"})


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(repo: Repository = Depends(get_repo)):
    return Response(await seo.sitemap(repo), media_type="application/xml; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=600"})
