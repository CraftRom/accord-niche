"""Server-side <head> metadata for the main website (SEO, link previews).

The website is a SPA: every URL returns the same index.html, so crawlers and
messenger previews that do not run JavaScript saw one generic title for all
products and articles. Nginx now asks this module, through an SSI include,
for the tags of the requested path. Only public, published data is used;
everything is HTML-escaped, and JSON-LD is serialized so that it cannot
close its <script> element.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote, unquote, urlsplit

from sqlalchemy import select

from shop import models as m
from shop.domain_security import DOMAIN

ORIGIN = f"https://{DOMAIN}"
SITE = "ACCORD NICHE"
DEFAULT_TITLE = "ACCORD NICHE — розпив оригінальної нішевої парфумерії"
DEFAULT_DESCRIPTION = ("ACCORD NICHE — розпив оригінальної нішевої парфумерії. Creed, Kilian, Nasomatto, "
                       "Amouage та інші. Спробуйте аромат у форматах 2, 5 або 10 мл.")
STATIC = {
    "/": (DEFAULT_TITLE, DEFAULT_DESCRIPTION),
    "/catalog": ("Каталог нішевих ароматів — ACCORD NICHE", "Усі аромати в наявності: розпив від 2 мл, ціни та об’єми."),
    "/sets": ("Набори ароматів — ACCORD NICHE", "Набори для знайомства з нішевою парфумерією."),
    "/brands": ("Бренди — ACCORD NICHE", "Нішеві парфумерні будинки в каталозі ACCORD NICHE."),
    "/blog": ("Блог — ACCORD NICHE", "Статті редакції ACCORD NICHE про аромати та парфумерні будинки."),
    "/how": ("Як це працює — ACCORD NICHE", "Як замовити розпив аромату: об’єми, доставка та оплата."),
}
PRIVATE = ("/checkout", "/profile", "/order/")
_AROMA = re.compile(r"^/aroma/([1-9][0-9]{0,9})$")
_BLOG = re.compile(r"^/blog/([^/]{1,180})$")
# Google Search Console token (meta method). Rechecked here because the .env
# fallback never passed the panel's validation.
_VERIFICATION = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


def _text(value, limit, *, markdown=False) -> str:
    """Single-line text for tags; markdown punctuation is dropped only from bodies."""
    raw = str(value or "")
    if markdown:
        raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", raw)          # images
        raw = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", raw)          # links -> text
        raw = re.sub(r"[#*_>`]", " ", raw)
    clean = re.sub(r"\s+", " ", raw).strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def absolute(url: str | None) -> str | None:
    """Only same-site paths or https URLs become og:image; anything else is dropped."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme and not parts.netloc and url.startswith("/") and not url.startswith("//"):
        return ORIGIN + url
    if parts.scheme == "https" and parts.netloc and not parts.username and not parts.password:
        return url
    return None


def _json_ld(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    # "</script>" or "<!--" inside a value must not end the element.
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render(meta: dict) -> str:
    e = lambda value: html.escape(str(value), quote=True)
    tags = [f"<title>{e(meta['title'])}</title>",
            f'<meta name="description" content="{e(meta["description"])}" />']
    if meta.get("noindex"):
        tags.append('<meta name="robots" content="noindex, follow" />')
    if _VERIFICATION.fullmatch(meta.get("google_verification") or ""):
        tags.append(f'<meta name="google-site-verification" content="{e(meta["google_verification"])}" />')
    if meta.get("canonical"):
        tags.append(f'<link rel="canonical" href="{e(meta["canonical"])}" />')
    tags += [f'<meta property="og:site_name" content="{SITE}" />',
             f'<meta property="og:type" content="{e(meta.get("type", "website"))}" />',
             f'<meta property="og:title" content="{e(meta["title"])}" />',
             f'<meta property="og:description" content="{e(meta["description"])}" />',
             '<meta property="og:locale" content="uk_UA" />']
    if meta.get("canonical"):
        tags.append(f'<meta property="og:url" content="{e(meta["canonical"])}" />')
    if meta.get("image"):
        tags.append(f'<meta property="og:image" content="{e(meta["image"])}" />')
        tags.append('<meta name="twitter:card" content="summary_large_image" />')
    for data in meta.get("json_ld", ()):
        tags.append(f'<script type="application/ld+json">{_json_ld(data)}</script>')
    return "\n".join(tags) + "\n"


def _money(value) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


async def _product_meta(repo, product_id: int) -> dict | None:
    from api.routers.public_catalog import public_product
    product = await repo.get_product(product_id)
    if not product or not product.is_published or product.price <= 0 or not product.name.strip():
        return None
    public = public_product(product)
    name = " ".join(part for part in (product.brand.strip(), product.name.strip()) if part)
    volume = f", {product.volume_ml} мл" if product.volume_ml else ""
    title = _text(f"{name}{volume} — {_money(product.price)} ₴ | {SITE}", 110)
    description = _text(product.description or f"{name}{volume}: оригінальний аромат на розпив у {SITE}.", 200, markdown=True)
    url = f"{ORIGIN}/aroma/{product.id}"
    image = absolute(public.photo_url or public.photo_endpoint)
    offer = {"@type": "Offer", "url": url, "priceCurrency": "UAH", "price": _money(product.price),
             "availability": "https://schema.org/" + ("InStock" if product.stock > 0 else "OutOfStock")}
    data = {"@context": "https://schema.org", "@type": "Product", "name": name, "sku": product.sku,
            "description": description, "offers": offer, "url": url}
    if product.brand.strip():
        data["brand"] = {"@type": "Brand", "name": product.brand.strip()}
    if image:
        data["image"] = image
    return {"title": title, "description": description, "canonical": url, "type": "product",
            "image": image, "json_ld": [data]}


async def _post_meta(repo, slug: str) -> dict | None:
    now = datetime.now(timezone.utc)
    post = await repo.s.scalar(select(m.BlogPost).join(m.BlogSlug, m.BlogSlug.post_id == m.BlogPost.id).where(
        m.BlogSlug.slug == slug, m.BlogPost.status == "published", m.BlogPost.published_at <= now))
    if post is None:
        return None
    # Old slugs stay reachable, but the canonical address is the current one.
    url = f"{ORIGIN}/blog/{quote(post.slug, safe='')}"
    description = _text(post.excerpt or post.body, 200, markdown=True)
    image = absolute(post.cover_url)
    published = post.published_at if post.published_at.tzinfo else post.published_at.replace(tzinfo=timezone.utc)
    data = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": _text(post.title, 110),
            "description": description, "datePublished": published.isoformat(), "url": url,
            "mainEntityOfPage": url,
            "author": {"@type": "Organization" if not post.author_name or "Редакція" in post.author_name else "Person",
                       "name": post.author_name or SITE},
            "publisher": {"@type": "Organization", "name": SITE}}
    if image:
        data["image"] = image
    return {"title": _text(f"{post.title} — {SITE}", 110), "description": description, "canonical": url,
            "type": "article", "image": image, "json_ld": [data]}


def normalize_path(raw: str) -> str:
    path = unquote(urlsplit(raw or "/").path or "/")
    path = "/" + path.lstrip("/")
    return path.rstrip("/") or "/"


async def head_for(repo, raw_path: str) -> str:
    path = normalize_path(raw_path)
    if path in STATIC:
        title, description = STATIC[path]
        meta = {"title": title, "description": description, "canonical": ORIGIN + ("" if path == "/" else path)}
        if path == "/":
            from shop.services.shop_settings import get_shop_settings
            meta["google_verification"] = (await get_shop_settings(repo)).site("google_site_verification")
        return render(meta)
    if any(path == p.rstrip("/") or path.startswith(p) for p in PRIVATE):
        return render({"title": DEFAULT_TITLE, "description": DEFAULT_DESCRIPTION, "noindex": True})
    meta = None
    if match := _AROMA.match(path):
        meta = await _product_meta(repo, int(match.group(1)))
    elif match := _BLOG.match(path):
        meta = await _post_meta(repo, match.group(1))
    if meta is None:
        # Unknown, hidden or unpublished: generic tags and never indexed.
        return render({"title": DEFAULT_TITLE, "description": DEFAULT_DESCRIPTION, "noindex": True})
    return render(meta)


async def sitemap(repo) -> str:
    now = datetime.now(timezone.utc)
    urls = [(ORIGIN + ("" if path == "/" else path), None) for path in STATIC]
    products, _ = await repo.storefront_data(now, now)  # published, priced SKUs only
    urls += [(f"{ORIGIN}/aroma/{p.id}", None) for p in products if p.name.strip()]
    posts = (await repo.s.execute(select(m.BlogPost.slug, m.BlogPost.updated_at).where(
        m.BlogPost.status == "published", m.BlogPost.published_at <= now).order_by(m.BlogPost.id))).all()
    urls += [(f"{ORIGIN}/blog/{quote(slug, safe='')}", updated) for slug, updated in posts]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, updated in urls[:50000]:
        lastmod = f"<lastmod>{(updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc)).date().isoformat()}</lastmod>" if updated else ""
        lines.append(f"<url><loc>{html.escape(loc)}</loc>{lastmod}</url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"
