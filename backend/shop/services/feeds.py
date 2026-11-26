"""Google Merchant Center product feed and the blog RSS feed.

- https://accordniche.pp.ua/feeds/google-merchant.xml: RSS 2.0 with the Google
  ``g:`` namespace, one item per SKU (2, 5, 10 ml…), grouped by aroma through
  ``g:item_group_id``. Decants have no GTIN, so ``g:identifier_exists`` is
  ``no``. Delivery and returns are configured in Merchant Center itself.
- https://accordniche.pp.ua/blog/rss.xml: the latest published articles.

Built from the same public data as the sitemap (published aromas, published
indexable articles), cached until content changes (seo.invalidate()), the
next scheduled article goes live, or ten minutes pass.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from weakref import WeakKeyDictionary

from sqlalchemy import func, select

from shop import models as m
from shop.services import seo

MERCHANT_PATH = "/feeds/google-merchant.xml"
BLOG_RSS_PATH = "/blog/rss.xml"
# Google product taxonomy 479: Health & Beauty > Personal Care > Cosmetics > Perfume & Cologne.
PERFUME_CATEGORY = "479"
RSS_ITEMS = 30
TITLE_LIMIT = 150
_GENDER = {"male": "male", "female": "female", "unisex": "unisex"}
_CACHE: WeakKeyDictionary = WeakKeyDictionary()


def invalidate() -> None:
    _CACHE.clear()


def _x(value) -> str:
    return escape(str(value), quote=False)


def _tag(name: str, value) -> str:
    return f"<{name}>{_x(value)}</{name}>" if value not in (None, "") else ""


def _merchant_title(product, group) -> str:
    concentration = {"edp": "EDP", "edt": "EDT", "edc": "EDC", "extrait": "Extrait", "parfum": "Parfum"}.get(
        group.get("concentration") or "", "")
    size = f"{product.volume_ml} мл" if product.volume_ml else ""
    title = " ".join(part for part in (group["brand"], group["name"], concentration, size) if part)
    return (title + " (розпив)")[:TITLE_LIMIT]


def _merchant(groups, skus: dict) -> str:
    items = []
    for group in sorted(groups, key=lambda g: g["id"]):
        description = seo.aroma_description(group)
        group_image = seo.absolute(group.get("image"))
        for product in sorted(group["variants"], key=lambda p: (p.volume_ml or 100000, p.id)):
            image = seo.absolute(product.photo_url or product.photo_endpoint) or group_image
            if not image or not product.price or product.price <= 0:
                continue  # Google rejects items without an image or a price
            link = f"{seo.ORIGIN}/aroma/{product.id}-{group['slug']}"
            parts = [
                _tag("g:id", skus.get(product.id) or product.id),
                _tag("g:title", _merchant_title(product, group)),
                _tag("g:description", description),
                _tag("g:link", link),
                _tag("g:image_link", image),
                _tag("g:availability", "in_stock" if product.stock > 0 else "out_of_stock"),
                _tag("g:price", f"{seo._money(product.price)} UAH"),
                _tag("g:condition", "new"),
                _tag("g:brand", group["brand"]),
                _tag("g:identifier_exists", "no"),
                _tag("g:google_product_category", PERFUME_CATEGORY),
                _tag("g:product_type", " > ".join(p for p in ("Парфумерія на розпив", group["brand"]) if p)),
                _tag("g:gender", _GENDER.get(group.get("gender") or "", "unisex")),
                _tag("g:age_group", "adult"),
            ]
            if len(group["variants"]) > 1:
                parts.append(_tag("g:item_group_id", group["id"]))
            if product.volume_ml:
                parts.append(_tag("g:size", f"{product.volume_ml} мл"))
                parts.append(_tag("g:unit_pricing_measure", f"{product.volume_ml}ml"))
                parts.append(_tag("g:unit_pricing_base_measure", "1ml"))
            items.append("<item>" + "".join(p for p in parts if p) + "</item>")
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">',
        "<channel>",
        _tag("title", seo.SITE),
        _tag("link", seo.ORIGIN + "/"),
        _tag("description", seo.DEFAULT_DESCRIPTION),
        *items,
        "</channel>",
        "</rss>",
    ]) + "\n"


def _rfc822(value: datetime) -> str:
    return format_datetime(seo._aware(value).astimezone(timezone.utc), usegmt=True)


def _rss(posts) -> str:
    items = []
    for post in posts:
        url = seo.post_url(post)
        image = seo.absolute(post.cover_url)
        description = post.excerpt or post.seo_description or seo._text(post.body, 300, markdown=True)
        parts = [_tag("title", post.title), _tag("link", url),
                 f'<guid isPermaLink="true">{_x(url)}</guid>',
                 _tag("pubDate", _rfc822(post.published_at)),
                 _tag("dc:creator", post.author_name),
                 _tag("description", description)]
        if image:
            parts.append(f'<media:content url="{escape(image, quote=True)}" medium="image" />')
        items.append("<item>" + "".join(p for p in parts if p) + "</item>")
    newest = max((seo._aware(p.updated_at) or seo._aware(p.published_at) for p in posts), default=None)
    title, description = seo.STATIC["/blog"]
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">',
        "<channel>",
        _tag("title", title),
        _tag("link", seo.ORIGIN + "/blog"),
        f'<atom:link href="{seo.ORIGIN}{BLOG_RSS_PATH}" rel="self" type="application/rss+xml" />',
        _tag("description", description),
        _tag("language", "uk"),
        _tag("lastBuildDate", _rfc822(newest)) if newest else "",
        *items,
        "</channel>",
        "</rss>",
    ]) + "\n"


async def _build(repo) -> dict:
    now = datetime.now(timezone.utc)
    groups = await seo._groups(repo)
    ids = [p.id for g in groups for p in g["variants"]]
    skus = dict((await repo.s.execute(select(m.Product.id, m.Product.sku).where(m.Product.id.in_(ids)))).all()) if ids else {}
    posts = list((await repo.s.scalars(select(m.BlogPost).where(
        m.BlogPost.status == "published", m.BlogPost.published_at <= now, m.BlogPost.noindex.is_(False))
        .order_by(m.BlogPost.published_at.desc(), m.BlogPost.id.desc()).limit(RSS_ITEMS))).all())
    docs = {"merchant": _merchant(groups, skus), "rss": _rss(posts)}
    upcoming = await repo.s.scalar(select(func.min(m.BlogPost.published_at)).where(
        m.BlogPost.status == "published", m.BlogPost.published_at > now))
    expires = time.monotonic() + seo.SITEMAP_TTL_SECONDS
    if upcoming is not None:
        expires = min(expires, time.monotonic() + max(1.0, (seo._aware(upcoming) - now).total_seconds()))
    return {"docs": docs, "expires": expires,
            "etags": {key: hashlib.sha256(value.encode()).hexdigest()[:32] for key, value in docs.items()}}


async def document(repo, name: str) -> tuple[str, str]:
    """(xml, etag) of ``merchant`` or ``rss``."""
    engine = getattr(getattr(repo, "s", None), "bind", None)
    cached = _CACHE.get(engine)
    if not cached or cached["expires"] <= time.monotonic():
        cached = await _build(repo)
        if engine is not None:
            _CACHE[engine] = cached
    return cached["docs"][name], cached["etags"][name]
