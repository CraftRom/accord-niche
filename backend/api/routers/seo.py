"""Public SEO endpoints of the main website: per-URL <head> tags, sitemaps, IndexNow key."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services import indexnow, seo

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


async def _sitemap(repo, name: str, if_none_match: str | None):
    body, etag = await seo.sitemap_document(repo, name)
    headers = {"Cache-Control": "public, max-age=300", "ETag": f'"{etag}"'}
    if if_none_match and etag in if_none_match:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/xml; charset=utf-8", headers=headers)


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_index(if_none_match: str | None = Header(None, max_length=200),
                        repo: Repository = Depends(get_repo)):
    return await _sitemap(repo, "index", if_none_match)


@router.get("/sitemap-{section}.xml", include_in_schema=False)
async def sitemap_section(section: str, if_none_match: str | None = Header(None, max_length=200),
                          repo: Repository = Depends(get_repo)):
    if section not in seo.SECTIONS:
        raise HTTPException(404, "Not found")
    return await _sitemap(repo, section, if_none_match)


@router.get("/indexnow/{name}.txt", include_in_schema=False)
async def indexnow_key(name: str):
    """IndexNow ownership proof: https://<domain>/<key>.txt returns the key itself."""
    key = indexnow.key()
    if not key or name != key:
        raise HTTPException(404, "Not found")
    return PlainTextResponse(key, headers={"Cache-Control": "public, max-age=86400"})
