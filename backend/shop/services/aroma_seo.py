"""One perfume, many volumes: shared SEO fields and readable addresses.

Each volume is its own SKU, but the shopper (and a search engine) sees one
aroma page. Notes, concentration, perfumer and the SEO title belong to the
aroma, so saving them on one SKU stores them on every SKU of that aroma, and a
new volume of an existing aroma inherits them.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select

from shop import models as m
from shop.services.storefront import aroma_name, normalized

TEXT_FIELDS = ("seo_title", "seo_description", "image_alt", "concentration", "fragrance_family",
               "top_notes", "heart_notes", "base_notes", "perfumer")
FIELDS = TEXT_FIELDS + ("release_year",)
CONCENTRATION_NAMES = {
    "parfum": "Parfum", "extrait": "Extrait de Parfum", "edp": "Eau de Parfum", "edt": "Eau de Toilette",
    "edc": "Eau de Cologne", "cologne": "Cologne", "oil": "Парфумована олія", "other": "",
}

# Офіційна транслітерація (КМУ №55, 2010) + російські літери, що трапляються в назвах.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z",
    "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "ё": "e", "ы": "y", "э": "e", "ъ": "", "'": "", "’": "",
    "ʼ": "", "&": "-and-", "+": "-plus-",
}


def slugify(*parts: str, limit: int = 80) -> str:
    """Latin, lowercase, hyphenated: 'Kilian Angels’ Share' -> 'kilian-angels-share'."""
    raw = " ".join(p for p in parts if p).casefold()
    raw = "".join(_TRANSLIT.get(char, char) for char in raw)
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0] or slug[:limit]
    return slug


def group_key(product) -> str:
    return normalized(product.brand.strip()) + ":" + normalized(aroma_name(product))


def aroma_slug(brand: str, name: str) -> str:
    return slugify(brand, name) or "aroma"


def aroma_path(group_id: int, brand: str, name: str) -> str:
    return f"/aroma/{group_id}-{aroma_slug(brand, name)}"


def first_value(products, field):
    for product in sorted(products, key=lambda p: p.id):
        value = getattr(product, field, None)
        if value not in (None, ""):
            return value
    return None if field == "release_year" else ""


async def siblings(repo, product_id: int) -> list:
    """SKUs of the same aroma (same brand and name without the volume)."""
    row = await repo.s.get(m.Product, product_id)
    if row is None:
        return []
    key = group_key(row)
    # The catalog is small (hundreds of SKUs); grouping needs the same rules as the storefront.
    candidates = (await repo.s.scalars(select(m.Product))).all()
    return [p for p in candidates if p.id != row.id and p.name.strip() and group_key(p) == key]


async def share(repo, product_id: int, changes: dict) -> list[int]:
    """Store aroma-level fields on every volume of the aroma. Returns touched ids."""
    values = {key: value for key, value in changes.items() if key in FIELDS}
    if not values:
        return []
    others = await siblings(repo, product_id)
    for other in others:
        for key, value in values.items():
            setattr(other, key, value)
    if others:
        await repo.s.commit()
    return [p.id for p in others]


async def inherit(repo, product_id: int) -> None:
    """A new volume of a known aroma takes the aroma card it does not have yet."""
    row = await repo.s.get(m.Product, product_id)
    others = await siblings(repo, product_id)
    if row is None or not others:
        return
    changed = False
    for key in FIELDS:
        if getattr(row, key) in (None, ""):
            value = first_value(others, key)
            if value not in (None, ""):
                setattr(row, key, value)
                changed = True
    if changed:
        await repo.s.commit()


async def canonical_paths(repo, product_ids) -> list[str]:
    """Canonical /aroma/<first-id>-<slug> of the aromas these SKUs belong to."""
    paths = set()
    for product_id in product_ids:
        row = await repo.s.get(m.Product, product_id)
        if row is None or not row.name.strip():
            continue
        group = [row, *await siblings(repo, product_id)]
        paths.add(aroma_path(min(p.id for p in group), row.brand.strip(), aroma_name(row)))
    return sorted(paths)
