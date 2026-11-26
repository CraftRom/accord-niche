"""Server-side <head> metadata and sitemaps for the main website.

The website is a SPA: every URL returns the same index.html, so crawlers and
messenger previews that do not run JavaScript would see one generic title for
all products and articles. Nginx asks this module, through an SSI include, for
the tags of the requested path. Only public, published data is used;
everything is HTML-escaped, and JSON-LD is serialized so that it cannot close
its <script> element.

Addresses:
- one aroma = one indexable page, /aroma/<id>-<brand-name> (id of its first
  SKU). Every volume (/aroma/<sku id>, old links included) points its
  canonical there, so 2, 5 and 10 ml never compete with each other;
- a brand is /catalog?brand=<name>: its own title, description and canonical;
- filters, sorting and search are never canonical, page N of a list is.

Sitemaps: /sitemap.xml is an index of pages, aromas (with images) and blog.
They are built from the database on request and cached until the content
changes (catalog and blog saves call invalidate()), the next scheduled article
goes live, or ten minutes pass, whichever is first.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, quote, unquote, urlsplit
from weakref import WeakKeyDictionary

from sqlalchemy import func, select

from shop import models as m
from shop.domain_security import DOMAIN

ORIGIN = f"https://{DOMAIN}"
SITE = "ACCORD NICHE"
# Google wants a raster logo of at least 112 px for Organization.
LOGO = f"{ORIGIN}/logo.png"
DEFAULT_TITLE = "ACCORD NICHE — розпив оригінальної нішевої парфумерії"
DEFAULT_DESCRIPTION = ("ACCORD NICHE — розпив оригінальної нішевої парфумерії. Creed, Kilian, Nasomatto, "
                       "Amouage та інші. Спробуйте аромат у форматах 2, 5 або 10 мл.")
STATIC = {
    "/": (DEFAULT_TITLE, DEFAULT_DESCRIPTION),
    "/catalog": ("Каталог нішевих ароматів на розпив — ACCORD NICHE",
                 "Усі оригінальні нішеві аромати в наявності: розпив від 2 мл, ціни за мілілітр, доставка по Україні."),
    "/sets": ("Набори ароматів на розпив — ACCORD NICHE", "Набори для знайомства з нішевою парфумерією: кілька ароматів у малих об’ємах."),
    "/brands": ("Бренди нішевої парфумерії — ACCORD NICHE", "Нішеві парфумерні будинки в каталозі ACCORD NICHE: оберіть бренд і спробуйте аромат від 2 мл."),
    "/blog": ("Блог про нішеву парфумерію — ACCORD NICHE", "Статті редакції ACCORD NICHE про аромати, ноти та парфумерні будинки."),
    "/how": ("Як це працює — ACCORD NICHE", "Як замовити розпив аромату: об’єми, доставка та оплата."),
    "/terms": ("Публічна оферта — ACCORD NICHE", "Умови купівлі парфумерії на розпив: оформлення, оплата, доставка, повернення."),
    "/privacy": ("Політика конфіденційності — ACCORD NICHE", "Як ACCORD NICHE обробляє й захищає персональні дані покупців."),
}
# Sitemap priority hints for the static sections (lists matter more than legal text).
_SECTION_PAGES = ("/", "/catalog", "/sets", "/brands", "/blog", "/how", "/terms", "/privacy")
PRIVATE = ("/checkout", "/profile", "/order/")
_AROMA = re.compile(r"^/aroma/([1-9][0-9]{0,9})(?:-[a-z0-9-]{1,120})?$")
_BLOG = re.compile(r"^/blog/([^/]{1,180})$")
# Google Search Console token (meta method). Rechecked here because the .env
# fallback never passed the panel's validation.
_VERIFICATION = re.compile(r"^[A-Za-z0-9_-]{20,100}$")
GENDER = {"male": "male", "female": "female", "unisex": "unisex"}
GENDER_UA = {"male": "чоловічий", "female": "жіночий", "unisex": "унісекс"}
TITLE_LIMIT = 70
DESCRIPTION_LIMIT = 160


def _text(value, limit, *, markdown=False) -> str:
    """Single-line text for tags; markdown punctuation is dropped only from bodies."""
    raw = str(value or "")
    if markdown:
        raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", raw)          # images
        raw = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", raw)          # links -> text
        raw = re.sub(r"[#*_>`]", " ", raw)
    clean = re.sub(r"\s+", " ", raw).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1]
    # Never end on half a word: "чорна сморо…" reads as a mistake in a snippet.
    if " " in cut and not clean[limit - 1].isspace():
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—-") + "…"


def _title(main: str, limit: int = TITLE_LIMIT) -> str:
    """'<main> | ACCORD NICHE' while it fits Google's snippet, else just <main>."""
    main = _text(main, limit)
    suffix = f" | {SITE}"
    return main + suffix if len(main) + len(suffix) <= limit else main


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
    from shop.services import test_mode
    if test_mode.active():
        # Sandbox pages are only for the administrator's browser: never indexed.
        meta = {**meta, "noindex": True, "title": "[ТЕСТ] " + meta["title"], "google_verification": None}
    tags = [f"<title>{e(meta['title'])}</title>",
            f'<meta name="description" content="{e(meta["description"])}" />']
    if meta.get("noindex"):
        tags.append('<meta name="robots" content="noindex, follow" />')
    else:
        tags.append('<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1" />')
    if _VERIFICATION.fullmatch(meta.get("google_verification") or ""):
        tags.append(f'<meta name="google-site-verification" content="{e(meta["google_verification"])}" />')
    if meta.get("canonical"):
        tags.append(f'<link rel="canonical" href="{e(meta["canonical"])}" />')
        tags.append(f'<link rel="alternate" hreflang="uk" href="{e(meta["canonical"])}" />')
        tags.append(f'<link rel="alternate" hreflang="x-default" href="{e(meta["canonical"])}" />')
    for rel in ("prev", "next"):
        if meta.get(rel):
            tags.append(f'<link rel="{rel}" href="{e(meta[rel])}" />')
    tags += [f'<meta property="og:site_name" content="{SITE}" />',
             f'<meta property="og:type" content="{e(meta.get("type", "website"))}" />',
             f'<meta property="og:title" content="{e(meta.get("og_title") or meta["title"])}" />',
             f'<meta property="og:description" content="{e(meta["description"])}" />',
             '<meta property="og:locale" content="uk_UA" />']
    if meta.get("canonical"):
        tags.append(f'<meta property="og:url" content="{e(meta["canonical"])}" />')
    if meta.get("image"):
        tags.append(f'<meta property="og:image" content="{e(meta["image"])}" />')
        if meta.get("image_alt"):
            tags.append(f'<meta property="og:image:alt" content="{e(meta["image_alt"])}" />')
        tags.append('<meta name="twitter:card" content="summary_large_image" />')
    else:
        tags.append('<meta name="twitter:card" content="summary" />')
    for prop, value in meta.get("og_extra", ()):
        tags.append(f'<meta property="{e(prop)}" content="{e(value)}" />')
    for data in meta.get("json_ld", ()):
        tags.append(f'<script type="application/ld+json">{_json_ld(data)}</script>')
    return "\n".join(tags) + "\n"


def _money(value) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _price(value) -> str:
    """Human price for titles: 450 ₴, 1 250.50 ₴."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    whole = amount == amount.to_integral()
    text = f"{amount:,.0f}" if whole else f"{amount:,.2f}"
    return text.replace(",", " ") + " ₴"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def brand_url(brand: str) -> str:
    return f"{ORIGIN}/catalog?brand={quote(brand, safe='')}"


def _breadcrumbs(*items: tuple[str, str]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": index, "name": name, "item": url}
        for index, (name, url) in enumerate(items, 1)]}


def _organization() -> dict:
    return {"@type": "Organization", "@id": ORIGIN + "/#organization", "name": SITE, "url": ORIGIN, "logo": LOGO}


# ------------------------------------------------------------------ aromas

def _volumes(group) -> str:
    volumes = group["volumes"]
    return ", ".join(str(v) for v in volumes) + " мл" if volumes else ""


def _notes_sentence(group) -> str:
    """'Ноти: ананас, бергамот, береза, пачулі, мускус, дубовий мох.' — two per tier, lowercase."""
    notes = []
    for field in ("top_notes", "heart_notes", "base_notes"):
        parts = [p.strip() for p in re.split(r"[,;]", group.get(field) or "") if p.strip()]
        notes += [p[:1].lower() + p[1:] if p[:2] != p[:2].upper() else p for p in parts[:2]]
    return ("Ноти: " + ", ".join(notes) + ".") if notes else ""


def aroma_title(group) -> str:
    if group.get("seo_title"):
        return _text(group["seo_title"], 120)
    name = " ".join(part for part in (group["brand"], group["name"]) if part)
    concentration = {"edp": "EDP", "edt": "EDT", "edc": "EDC", "extrait": "Extrait", "parfum": "Parfum"}.get(
        group.get("concentration") or "", "")
    head = f"{name} {concentration}".strip()
    volumes = _volumes(group)
    full = f"{head} — розпив {volumes} від {_price(group['min_price'])}" if volumes else f"{head} — розпив від {_price(group['min_price'])}"
    return _title(full) if len(full) <= TITLE_LIMIT else _title(f"{head} — розпив від {_price(group['min_price'])}")


def aroma_description(group) -> str:
    from shop.services.aroma_seo import CONCENTRATION_NAMES
    if group.get("seo_description"):
        return _text(group["seo_description"], 300)
    name = " ".join(part for part in (group["brand"], group["name"]) if part)
    concentration = CONCENTRATION_NAMES.get(group.get("concentration") or "", "")
    kind = GENDER_UA.get(group.get("gender") or "unisex", "унісекс")
    family = (group.get("fragrance_family") or "").strip()
    lead = f"{name}{' (' + concentration + ')' if concentration else ''} — оригінальний {kind} аромат"
    volumes = _volumes(group)
    offer = f" на розпив {volumes} від {_price(group['min_price'])}" if volumes else f" на розпив від {_price(group['min_price'])}"
    sentence = lead + offer + "."
    if family:
        sentence += f" {family[:1].upper() + family[1:]}."
    extra = _notes_sentence(group) or _text(group.get("description"), 300, markdown=True)
    return _text(f"{sentence} {extra}".strip(), DESCRIPTION_LIMIT)


def _variant_name(product, group) -> str:
    size = f"{product.volume_ml} мл" if product.volume_ml else ""
    return " ".join(part for part in (group["brand"], group["name"], size) if part)


def _aroma_ld(group, url, image, description, skus: dict) -> list[dict]:
    from shop.services.aroma_seo import CONCENTRATION_NAMES
    name = " ".join(part for part in (group["brand"], group["name"]) if part)
    properties = []
    for label, field in (("Концентрація", "concentration"), ("Сімейство", "fragrance_family"),
                         ("Верхні ноти", "top_notes"), ("Ноти серця", "heart_notes"), ("Базові ноти", "base_notes"),
                         ("Парфумер", "perfumer"), ("Рік випуску", "release_year")):
        value = group.get(field)
        if field == "concentration":
            value = CONCENTRATION_NAMES.get(value or "", "")
        if value not in (None, ""):
            properties.append({"@type": "PropertyValue", "name": label, "value": str(value)})
    common = {"brand": {"@type": "Brand", "name": group["brand"]}} if group["brand"] else {}
    common["audience"] = {"@type": "PeopleAudience", "suggestedGender": GENDER.get(group.get("gender"), "unisex")}
    if image:
        common["image"] = [image]
    if properties:
        common["additionalProperty"] = properties
    common["category"] = "Health & Beauty > Personal Care > Cosmetics > Perfume & Cologne"

    def offer(product, offer_url):
        return {"@type": "Offer", "url": offer_url, "priceCurrency": "UAH", "price": _money(product.price),
                "availability": "https://schema.org/" + ("InStock" if product.stock > 0 else "OutOfStock"),
                "itemCondition": "https://schema.org/NewCondition",
                "seller": {"@type": "Organization", "name": SITE, "@id": ORIGIN + "/#organization"}}

    variants = sorted(group["variants"], key=lambda p: (p.volume_ml or 100000, p.id))
    if len(variants) == 1:
        product = variants[0]
        data = {"@context": "https://schema.org", "@type": "Product", "@id": url + "#product", "name": name,
                "sku": skus.get(product.id) or str(product.id), "description": description,
                "url": url, **common, "offers": offer(product, url)}
        if product.volume_ml:
            data["size"] = f"{product.volume_ml} мл"
        return [data]
    # One page, several volumes: schema.org ProductGroup with one Product per volume.
    data = {"@context": "https://schema.org", "@type": "ProductGroup", "@id": url + "#product", "name": name,
            "description": description, "url": url, "productGroupID": str(group["id"]),
            "variesBy": ["https://schema.org/size"], **common, "hasVariant": []}
    for product in variants:
        variant_url = f"{ORIGIN}/aroma/{product.id}-{group['slug']}"
        variant = {"@type": "Product", "name": _variant_name(product, group), "sku": skus.get(product.id) or str(product.id),
                   "url": variant_url, "offers": offer(product, variant_url)}
        if product.volume_ml:
            variant["size"] = f"{product.volume_ml} мл"
        variant_image = absolute(product.photo_url or product.photo_endpoint)
        if variant_image:
            variant["image"] = variant_image
        data["hasVariant"].append(variant)
    return [data]


async def _groups(repo):
    from api.routers.public_catalog import public_product
    from shop.services.storefront import snapshot
    return (await snapshot(repo, public_product))["groups"]


async def _product_meta(repo, product_id: int) -> dict | None:
    groups = await _groups(repo)
    group = next((g for g in groups if any(p.id == product_id for p in g["variants"])), None)
    if group is None:
        return None
    # Variants come serialized (PublicProduct, no system article): read SKUs for JSON-LD.
    skus = dict((await repo.s.execute(select(m.Product.id, m.Product.sku).where(
        m.Product.id.in_([p.id for p in group["variants"]])))).all())
    variants = group["variants"]
    url = ORIGIN + group["path"]
    description = aroma_description(group)
    name = " ".join(part for part in (group["brand"], group["name"]) if part)
    image = absolute(group["image"])
    alt = group.get("image_alt") or f"{name} — розпив оригінального аромату"
    crumbs = [("Головна", ORIGIN + "/"), ("Каталог", ORIGIN + "/catalog")]
    if group["brand"]:
        crumbs.append((group["brand"], brand_url(group["brand"])))
    crumbs.append((group["name"], url))
    buyable = [p for p in variants if p.stock > 0]
    extra = [("product:price:amount", _money(group["min_price"])), ("product:price:currency", "UAH"),
             ("product:availability", "in stock" if buyable else "out of stock"),
             ("product:condition", "new")]
    if group["brand"]:
        extra.append(("product:brand", group["brand"]))
    return {"title": aroma_title(group), "og_title": name, "description": description, "canonical": url,
            "type": "product", "image": image, "image_alt": alt, "og_extra": extra,
            "json_ld": [*_aroma_ld(group, url, image, description, skus), _breadcrumbs(*crumbs)]}


# ------------------------------------------------------------------ blog

def post_url(post) -> str:
    return f"{ORIGIN}/blog/{quote(post.slug, safe='')}"


async def _post_meta(repo, slug: str) -> dict | None:
    now = datetime.now(timezone.utc)
    post = await repo.s.scalar(select(m.BlogPost).join(m.BlogSlug, m.BlogSlug.post_id == m.BlogPost.id).where(
        m.BlogSlug.slug == slug, m.BlogPost.status == "published", m.BlogPost.published_at <= now))
    if post is None:
        return None
    # Old slugs stay reachable, but the canonical address is the current one.
    url = post_url(post)
    description = _text(post.seo_description or post.excerpt or post.body, DESCRIPTION_LIMIT, markdown=True)
    image = absolute(post.cover_url)
    published = _aware(post.published_at)
    modified = max(published, _aware(post.updated_at) or published)
    comments = await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(
        m.BlogComment.post_id == post.id, m.BlogComment.status == "approved"))
    words = len(re.findall(r"\w+", _text(post.body, 10 ** 6, markdown=True)))
    person = bool(post.author_name) and "Редакція" not in post.author_name
    data = {"@context": "https://schema.org", "@type": "BlogPosting", "@id": url + "#article",
            "headline": _text(post.title, 110), "description": description,
            "datePublished": published.isoformat(), "dateModified": modified.isoformat(), "url": url,
            "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "inLanguage": "uk-UA", "wordCount": words,
            "commentCount": comments or 0,
            "author": {"@type": "Person" if person else "Organization", "name": post.author_name or SITE,
                       **({} if person else {"url": ORIGIN})},
            "publisher": _organization(), "isPartOf": {"@type": "Blog", "@id": ORIGIN + "/blog", "name": f"Блог {SITE}"}}
    if post.focus_keyword:
        data["keywords"] = post.focus_keyword
    if image:
        data["image"] = [image]
    extra = [("article:published_time", published.isoformat()), ("article:modified_time", modified.isoformat())]
    title = _text(post.seo_title, 120) if post.seo_title else _title(post.title)
    return {"title": title, "og_title": post.seo_title or post.title, "description": description, "canonical": url,
            "type": "article", "image": image, "image_alt": post.cover_alt or post.title, "og_extra": extra,
            "noindex": bool(post.noindex),
            "json_ld": [data, _breadcrumbs(("Головна", ORIGIN + "/"), ("Блог", ORIGIN + "/blog"), (_text(post.title, 110), url))]}


# ------------------------------------------------------------------ lists

def _page(query: dict) -> int:
    raw = (query.get("page") or ["1"])[0]
    return int(raw) if raw.isdigit() and 0 < int(raw) < 10000 else 1


def _list_url(path: str, page: int, **params) -> str:
    pairs = [f"{key}={quote(value, safe='')}" for key, value in params.items() if value]
    if page > 1:
        pairs.append(f"page={page}")
    return ORIGIN + ("" if path == "/" else path) + ("?" + "&".join(pairs) if pairs else "")


async def _brand_meta(repo, name: str, page: int) -> dict | None:
    groups = [g for g in await _groups(repo) if g["brand"].casefold() == name.casefold()]
    if not groups:
        return None
    brand = groups[0]["brand"]
    row = await repo.s.scalar(select(m.Brand).where(m.Brand.name_key == brand.strip().lower()))
    if row is not None and not row.is_active:
        return None
    count = len(groups)
    low = min(g["min_price"] for g in groups)
    description = _text(row.description, DESCRIPTION_LIMIT, markdown=True) if row is not None and row.description else _text(
        f"{brand}: {count} {'аромат' if count == 1 else 'аромати' if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else 'ароматів'} "
        f"на розпив від {_price(low)}. Оригінальна нішева парфумерія від 2 мл у {SITE}.", DESCRIPTION_LIMIT)
    url = _list_url("/catalog", page, brand=brand)
    title = _title(f"{brand} — оригінальні аромати на розпив" + (f", сторінка {page}" if page > 1 else ""))
    items = [{"@type": "ListItem", "position": index, "url": ORIGIN + g["path"], "name": g["name"]}
             for index, g in enumerate(groups[:30], 1)]
    return {"title": title, "description": description, "canonical": url,
            "json_ld": [{"@context": "https://schema.org", "@type": "CollectionPage", "name": f"{brand} — {SITE}",
                         "url": url, "mainEntity": {"@type": "ItemList", "itemListElement": items}},
                        _breadcrumbs(("Головна", ORIGIN + "/"), ("Бренди", ORIGIN + "/brands"), (brand, brand_url(brand)))]}


def _home_ld() -> list[dict]:
    return [{"@context": "https://schema.org", **_organization()},
            {"@context": "https://schema.org", "@type": "WebSite", "@id": ORIGIN + "/#website", "name": SITE,
             "url": ORIGIN, "inLanguage": "uk-UA", "publisher": {"@id": ORIGIN + "/#organization"},
             "potentialAction": {"@type": "SearchAction",
                                 "target": {"@type": "EntryPoint", "urlTemplate": ORIGIN + "/catalog?q={search_term_string}"},
                                 "query-input": "required name=search_term_string"}}]


def normalize_path(raw: str) -> str:
    path = unquote(urlsplit(raw or "/").path or "/")
    path = "/" + path.lstrip("/")
    return path.rstrip("/") or "/"


def _query(raw: str) -> dict:
    try:
        return parse_qs(urlsplit(raw or "/").query, keep_blank_values=False)
    except ValueError:
        return {}


GENERIC = {"title": DEFAULT_TITLE, "description": DEFAULT_DESCRIPTION, "noindex": True}


async def head_for(repo, raw_path: str) -> str:
    path, query = normalize_path(raw_path), _query(raw_path)
    page = _page(query)
    search = (query.get("q") or [""])[0].strip()
    if path == "/catalog" and (query.get("brand") or [""])[0].strip() and not search:
        meta = await _brand_meta(repo, query["brand"][0].strip(), page)
        return render(meta or GENERIC)
    if path in STATIC:
        title, description = STATIC[path]
        meta = {"title": title, "description": description, "canonical": ORIGIN + ("" if path == "/" else path)}
        if path in ("/catalog", "/sets", "/blog") and page > 1:
            meta["title"] = _title(title.replace(f" — {SITE}", "") + f", сторінка {page}")
            meta["canonical"] = _list_url(path, page)
            meta["prev"] = _list_url(path, page - 1)
        if search:
            # Internal search results are thin duplicates: follow links, do not index.
            meta.update(noindex=True, canonical=None)
        if path == "/":
            from shop.services.shop_settings import get_shop_settings
            meta["google_verification"] = (await get_shop_settings(repo)).site("google_site_verification")
            meta["json_ld"] = _home_ld()
        elif path == "/blog":
            meta["json_ld"] = [_breadcrumbs(("Головна", ORIGIN + "/"), ("Блог", ORIGIN + "/blog"))]
        elif path in ("/catalog", "/brands", "/sets"):
            meta["json_ld"] = [_breadcrumbs(("Головна", ORIGIN + "/"), (title.split(" — ")[0], ORIGIN + path))]
        return render(meta)
    if any(path == p.rstrip("/") or path.startswith(p) for p in PRIVATE):
        return render(GENERIC)
    meta = None
    if match := _AROMA.match(path):
        meta = await _product_meta(repo, int(match.group(1)))
    elif match := _BLOG.match(path):
        meta = await _post_meta(repo, match.group(1))
    # Unknown, hidden or unpublished: generic tags and never indexed.
    return render(meta or GENERIC)


async def page_exists(repo, raw_path: str) -> bool:
    """Is there a page at this address? Nginx answers HTTP 404 when not.

    The website is a SPA: without this every unknown address answered 200
    with a «not found» screen and noindex, which Google reports as soft 404s.
    Private pages (checkout, profile, order) exist: they are noindex, not missing.
    """
    path = normalize_path(raw_path)
    if path == "/index.html":
        return True
    if path in STATIC or any(path == p.rstrip("/") or path.startswith(p) for p in PRIVATE):
        return True
    if match := _AROMA.match(path):
        product_id = int(match.group(1))
        return any(any(p.id == product_id for p in g["variants"]) for g in await _groups(repo))
    if match := _BLOG.match(path):
        now = datetime.now(timezone.utc)
        found = await repo.s.scalar(select(m.BlogPost.id).join(m.BlogSlug, m.BlogSlug.post_id == m.BlogPost.id).where(
            m.BlogSlug.slug == match.group(1), m.BlogPost.status == "published", m.BlogPost.published_at <= now))
        return found is not None
    return False


# ------------------------------------------------------------------ sitemaps

SITEMAP_TTL_SECONDS = 600
SECTIONS = ("pages", "aromas", "blog")
_SITEMAP_CACHE: WeakKeyDictionary = WeakKeyDictionary()
_NS = ('xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
       'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"')


def invalidate() -> None:
    """Content changed: the next request rebuilds every sitemap."""
    _SITEMAP_CACHE.clear()


def _lastmod(value: datetime | None) -> str:
    value = _aware(value)
    return value.replace(microsecond=0).isoformat() if value else ""


def _url(loc: str, lastmod: datetime | None = None, images: tuple = ()) -> str:
    e = html.escape
    parts = [f"<url><loc>{e(loc)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{_lastmod(lastmod)}</lastmod>")
    for image in images:
        parts.append(f"<image:image><image:loc>{e(image)}</image:loc></image:image>")
    parts.append("</url>")
    return "".join(parts)


async def _build(repo) -> dict:
    now = datetime.now(timezone.utc)
    groups = await _groups(repo)
    posts = (await repo.s.execute(select(m.BlogPost.slug, m.BlogPost.updated_at, m.BlogPost.published_at,
                                         m.BlogPost.cover_url, m.BlogPost.title).where(
        m.BlogPost.status == "published", m.BlogPost.published_at <= now, m.BlogPost.noindex.is_(False))
        .order_by(m.BlogPost.published_at.desc(), m.BlogPost.id.desc()))).all()
    hidden_brands = set((await repo.s.scalars(select(m.Brand.name_key).where(m.Brand.is_active.is_(False)))).all())
    aroma_stamp = max((_aware(g.get("updated_at")) for g in groups if g.get("updated_at")), default=None)
    post_stamp = max((max(_aware(u) or _aware(p), _aware(p)) for _, u, p, _, _ in posts), default=None)

    aroma_rows = []
    for group in sorted(groups, key=lambda g: g["id"]):
        images = []
        for variant in group["variants"]:
            image = absolute(variant.photo_url or variant.photo_endpoint)
            if image and image not in images:
                images.append(image)
        aroma_rows.append(_url(ORIGIN + group["path"], group.get("updated_at"), tuple(images[:5])))

    page_rows = []
    for path in _SECTION_PAGES:
        stamp = aroma_stamp if path in ("/", "/catalog", "/sets", "/brands") else post_stamp if path == "/blog" else None
        page_rows.append(_url(ORIGIN + ("" if path == "/" else path), stamp))
    brands: dict[str, list] = {}
    for group in groups:
        if group["brand"] and group["brand"].strip().lower() not in hidden_brands:
            brands.setdefault(group["brand"], []).append(group)
    for brand in sorted(brands, key=str.casefold):
        stamp = max((_aware(g.get("updated_at")) for g in brands[brand] if g.get("updated_at")), default=None)
        page_rows.append(_url(brand_url(brand), stamp))

    blog_rows = []
    for slug, updated, published, cover, title in posts:
        image = absolute(cover)
        stamp = max(_aware(updated) or _aware(published), _aware(published))
        blog_rows.append(_url(f"{ORIGIN}/blog/{quote(slug, safe='')}", stamp, (image,) if image else ()))

    def urlset(rows):
        return "\n".join(['<?xml version="1.0" encoding="UTF-8"?>', f"<urlset {_NS}>", *rows[:50000], "</urlset>"]) + "\n"

    stamps = {"pages": max([s for s in (aroma_stamp, post_stamp) if s], default=None), "aromas": aroma_stamp,
              "blog": post_stamp}
    docs = {"pages": urlset(page_rows), "aromas": urlset(aroma_rows), "blog": urlset(blog_rows)}
    index = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for name in SECTIONS:
        lastmod = f"<lastmod>{_lastmod(stamps[name])}</lastmod>" if stamps[name] else ""
        index.append(f"<sitemap><loc>{ORIGIN}/sitemap-{name}.xml</loc>{lastmod}</sitemap>")
    index.append("</sitemapindex>")
    docs["index"] = "\n".join(index) + "\n"
    # The next scheduled article must appear on time, not up to TTL later.
    upcoming = await repo.s.scalar(select(func.min(m.BlogPost.published_at)).where(
        m.BlogPost.status == "published", m.BlogPost.published_at > now))
    expires = time.monotonic() + SITEMAP_TTL_SECONDS
    if upcoming is not None:
        expires = min(expires, time.monotonic() + max(1.0, (_aware(upcoming) - now).total_seconds()))
    return {"docs": docs, "expires": expires,
            "etags": {key: hashlib.sha256(value.encode()).hexdigest()[:32] for key, value in docs.items()}}


async def sitemap_document(repo, name: str = "index") -> tuple[str, str]:
    """(xml, etag) of the sitemap index or one section; cached until content changes."""
    engine = getattr(getattr(repo, "s", None), "bind", None)
    cached = _SITEMAP_CACHE.get(engine)
    if not cached or cached["expires"] <= time.monotonic():
        cached = await _build(repo)
        if engine is not None:
            _SITEMAP_CACHE[engine] = cached
    return cached["docs"][name], cached["etags"][name]


async def sitemap(repo) -> str:
    """All public URLs in one urlset (kept for tools and tests that expect a flat list)."""
    docs = [(await sitemap_document(repo, name))[0] for name in SECTIONS]
    rows = [line for doc in docs for line in doc.splitlines() if line.startswith("<url>")]
    return "\n".join(['<?xml version="1.0" encoding="UTF-8"?>', f"<urlset {_NS}>", *rows, "</urlset>"]) + "\n"
