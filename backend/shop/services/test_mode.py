"""Test mode: a temporary sandbox copy of the storefront for the system administrator.

What it is
    A separate SQLite database in /data/test-mode with ten real niche perfumes
    (three volumes each, notes, prices, illustrations) and three blog posts.
    It never touches the main PostgreSQL database.

Who sees it
    Only a browser holding the signed test-mode cookie, which the system
    administrator gets from the panel. Every other visitor, crawler, the
    Mini App, the bot and the panel itself keep working on the main data.

What it can do
    Read requests of the website API (/api/public, /api/web) and the SEO head
    are served from the sandbox. Writes that would reach the outside world
    (orders, sign-in, SMS, Telegram linking, comments) are refused with a
    clear message; the visit counter and checkout quote work inside the sandbox.

How it ends
    It expires on its own (2 hours by default, 24 at most) or when the system
    administrator turns it off; the sandbox file is deleted either way.
    Sandbox responses are never cached (no-store) and never indexed (noindex).
"""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from shop.domain_security import DOMAIN

COOKIE = "__Host-accord_test"
ASSETS = Path(__file__).resolve().parents[1] / "test_mode_assets"
DEFAULT_HOURS = 2
MAX_HOURS = 24
MEDIA_PREFIX = f"https://{DOMAIN}/api/public/test-mode/media/"
# Web API writes allowed in the sandbox: they only touch sandbox tables.
ALLOWED_WRITES = {"/api/web/analytics/visit", "/api/web/checkout/quote"}

_active: contextvars.ContextVar[dict | None] = contextvars.ContextVar("accord_test_mode", default=None)
_engines: dict[str, tuple] = {}


# ------------------------------------------------------------------ storage

def root() -> Path:
    from shop.paths import DATA_ROOT
    path = DATA_ROOT / "test-mode"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_file() -> Path:
    return root() / "state.json"


def _db_file(sandbox_id: str) -> Path:
    return root() / f"sandbox-{sandbox_id}.db"


def _secret() -> bytes:
    from shop.config import settings
    return hashlib.sha256(b"accord-test-mode:" + str(settings.jwt_secret).encode()).digest()


def _sign(sandbox_id: str, expires: int) -> str:
    body = f"{sandbox_id}.{expires}"
    return body + "." + hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()


def state() -> dict | None:
    """Current sandbox, or None. An expired sandbox is removed here."""
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not str(data.get("id", "")).isalnum():
        return None
    if int(data.get("expires", 0)) <= time.time() or not _db_file(data["id"]).is_file():
        disable_sync()
        return None
    return data


def token(data: dict) -> str:
    return _sign(data["id"], int(data["expires"]))


def verify(raw: str | None) -> dict | None:
    """The sandbox this cookie opens, if the signature, id and time all match."""
    if not raw or raw.count(".") != 2 or len(raw) > 200:
        return None
    sandbox_id, expires, _ = raw.split(".")
    if not expires.isdigit() or not hmac.compare_digest(_sign(sandbox_id, int(expires)), raw):
        return None
    current = state()
    if not current or current["id"] != sandbox_id or int(current["expires"]) != int(expires):
        return None
    return current


def public(data: dict | None) -> dict:
    if not data:
        return {"active": False}
    return {"active": True, "created_by": data.get("created_by", ""), "created_at": data.get("created_at"),
            "expires_at": datetime.fromtimestamp(int(data["expires"]), timezone.utc).isoformat(),
            "products": data.get("products", 0), "aromas": data.get("aromas", 0), "posts": data.get("posts", 0),
            "enter_url": f"https://{DOMAIN}/api/public/test-mode/enter?token={token(data)}",
            "exit_url": f"https://{DOMAIN}/api/public/test-mode/exit"}


# ------------------------------------------------------------------ request scope

def active() -> dict | None:
    """The sandbox of the current request (set by the middleware)."""
    return _active.get()


def bind(data: dict | None):
    return _active.set(data)


def unbind(handle) -> None:
    _active.reset(handle)


def session_maker(data: dict):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    cached = _engines.get(data["id"])
    if cached is None:
        engine = create_async_engine("sqlite+aiosqlite:///" + str(_db_file(data["id"])))
        cached = (engine, async_sessionmaker(engine, expire_on_commit=False))
        _engines[data["id"]] = cached
    return cached[1]


# ------------------------------------------------------------------ lifecycle

def disable_sync() -> None:
    for sandbox_id in list(_engines):
        engine, _ = _engines.pop(sandbox_id)
        try:
            engine.sync_engine.dispose()
        except Exception:
            pass
    path = root()
    for item in path.iterdir():
        if item.name == "state.json" or item.name.startswith("sandbox-"):
            item.unlink(missing_ok=True) if item.is_file() else shutil.rmtree(item, ignore_errors=True)


async def disable() -> None:
    for sandbox_id in list(_engines):
        engine, _ = _engines.pop(sandbox_id)
        await engine.dispose()
    disable_sync()


async def enable(actor: str, hours: int = DEFAULT_HOURS) -> dict:
    """Fresh sandbox with seed data. An existing one is replaced."""
    await disable()
    hours = max(1, min(MAX_HOURS, int(hours)))
    sandbox_id = secrets.token_hex(8)
    from sqlalchemy.ext.asyncio import create_async_engine
    from shop import models as m
    engine = create_async_engine("sqlite+aiosqlite:///" + str(_db_file(sandbox_id)))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(m.Base.metadata.create_all)
            counts = await _seed(connection)
    finally:
        await engine.dispose()
    data = {"id": sandbox_id, "created_by": actor, "created_at": datetime.now(timezone.utc).isoformat(),
            "expires": int(time.time() + hours * 3600), **counts}
    temporary = _state_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temporary, _state_file())
    return data


def asset(name: str) -> Path | None:
    path = ASSETS / name
    if "/" in name or "\\" in name or not name.endswith(".png") or not path.is_file():
        return None
    return path


# ------------------------------------------------------------------ seed data

def _img(slug: str) -> str:
    return MEDIA_PREFIX + slug + ".png"


# Real perfumes; notes as commonly published by the houses and fragrance catalogs.
# Prices are test prices for decants, not a price list.
AROMAS = [
    dict(slug="creed-aventus", brand="Creed", name="Aventus", gender="male", concentration="edp", year=2010,
         family="Шипровий фруктовий", perfumer="Olivier Creed, Erwin Creed",
         top="Ананас, бергамот, чорна смородина, яблуко", heart="Береза, пачулі, марокканський жасмин, троянда",
         base="Мускус, дубовий мох, амбра, ваніль", prices=(260, 590, 1090), stock=(12, 7, 0), featured=True,
         description="Легенда сучасної чоловічої парфумерії: соковитий ананас і бергамот на старті, димна береза в серці й теплий мускус із дубовим мохом у базі."),
    dict(slug="mfk-baccarat-rouge-540", brand="Maison Francis Kurkdjian", name="Baccarat Rouge 540", gender="unisex",
         concentration="edp", year=2015, family="Амбровий квітковий", perfumer="Francis Kurkdjian",
         top="Шафран, жасмин", heart="Амбра, амбровий дерев’яний акорд", base="Смола ялиці, кедр",
         prices=(310, 720, 1350), stock=(9, 4, 2), featured=True, new=True,
         description="Повітряний, мінеральний і водночас теплий аромат-підпис: шафран, жасмин і кристалічна амбра, яка звучить на шкірі й одязі годинами."),
    dict(slug="le-labo-santal-33", brand="Le Labo", name="Santal 33", gender="unisex", concentration="edp", year=2011,
         family="Деревний ароматичний", perfumer="Frank Voelkl", top="Кардамон, ірис, фіалка", heart="Амброксан, папірус",
         base="Вірджинський кедр, шкіра, сандал", prices=(240, 540, 990), stock=(15, 8, 3),
         description="Сухий сандал, кедр і шкіра з пряним кардамоном — затишний «аромат великого міста», що пасує і чоловікам, і жінкам."),
    dict(slug="byredo-gypsy-water", brand="Byredo", name="Gypsy Water", gender="unisex", concentration="edp", year=2008,
         family="Деревний ароматичний", perfumer="Jérôme Epinette", top="Бергамот, лимон, перець, ялівець",
         heart="Ладан, соснова хвоя, ірис", base="Амбра, ваніль, сандал", prices=(220, 490, 900), stock=(6, 5, 1),
         description="Свіжа хвоя, цитрус і м’який ладан над теплою ваніллю: аромат лісу, багаття й свободи."),
    dict(slug="tom-ford-tobacco-vanille", brand="Tom Ford", name="Tobacco Vanille", gender="unisex", concentration="edp",
         year=2007, family="Східний пряний", perfumer="Olivier Gillotin", top="Тютюновий лист, прянощі",
         heart="Ваніль, какао, боби тонка, квітки тютюну", base="Сухофрукти, деревні ноти", prices=(250, 560, 1020),
         stock=(10, 6, 4),
         description="Густий і теплий: медовий тютюн, ваніль і какао із сухофруктами. Класичний вечірній аромат для холодної пори."),
    dict(slug="kilian-angels-share", brand="Kilian Paris", name="Angels' Share", gender="unisex", concentration="edp",
         year=2020, family="Східний гурманський", perfumer="Benoist Lapouza", top="Коньяк", heart="Кориця, боби тонка, дуб",
         base="Праліне, ваніль, сандал", prices=(270, 620, 1150), stock=(8, 0, 2), new=True,
         description="Коньяк у дубовій бочці, кориця й праліне: солодкий, але не нудотний гурманський аромат, який легко полюбити з першого вдиху."),
    dict(slug="amouage-interlude-man", brand="Amouage", name="Interlude Man", gender="male", concentration="edp",
         year=2012, family="Амбровий пряний", perfumer="Pierre Negrin", top="Орегано, перець, бергамот",
         heart="Ладан, амбра, ладанник, опопонакс", base="Шкіра, агарове дерево, сандал, пачулі",
         prices=(280, 650, 1200), stock=(5, 3, 1),
         description="Димний ладан, шкіра й уд із пряним орегано: щільний характерний аромат для тих, хто не боїться бути помітним."),
    dict(slug="nasomatto-black-afgano", brand="Nasomatto", name="Black Afgano", gender="unisex", concentration="extrait",
         year=2008, family="Деревний ароматичний", perfumer="Alessandro Gualtieri", top="Конопля, зелені ноти",
         heart="Смоли, деревні ноти, тютюн", base="Уд, ладан, кава", prices=(260, 600, 1100), stock=(7, 4, 0),
         description="Темний, смолистий і дуже стійкий екстракт: зелена конопля, тютюн, кава й уд. Кількох крапель вистачає на весь день."),
    dict(slug="pdm-layton", brand="Parfums de Marly", name="Layton", gender="male", concentration="edp", year=2016,
         family="Східний квітковий", perfumer="Hamid Merati-Kashani", top="Яблуко, лаванда, бергамот, мандарин",
         heart="Герань, фіалка, жасмин", base="Ваніль, кардамон, сандал, перець, пачулі, гваякове дерево",
         prices=(230, 520, 960), stock=(11, 9, 5), featured=True,
         description="Свіже яблуко й лаванда переходять у кремову ваніль із кардамоном — універсальний чоловічий аромат на кожен день і вечір."),
    dict(slug="xerjoff-naxos", brand="Xerjoff", name="Naxos", gender="male", concentration="edp", year=2015,
         family="Ароматичний фужерний", perfumer="Chris Maurice", top="Лаванда, бергамот, лимон",
         heart="Мед, кориця, кашмеран, жасмин", base="Тютюновий лист, боби тонка, ваніль", prices=(240, 550, 1000),
         stock=(4, 2, 1),
         description="Сицилійський цитрус, лаванда й мед над тютюном і ваніллю: сонячний, медово-тютюновий аромат із італійським характером."),
]
BRAND_TEXT = {
    "Creed": "Creed — парфумерний дім із Лондона й Парижа, відомий з XVIII століття. Розпив оригінальних ароматів Creed від 2 мл.",
    "Maison Francis Kurkdjian": "Паризький дім Франсіса Куркджяна: прозорі, світлі композиції й Baccarat Rouge 540.",
    "Le Labo": "Нью-йоркська лабораторія ароматів, що змішує парфуми під замовлення.",
    "Byredo": "Стокгольмський дім Бена Горема: мінімалізм і спогади в ароматах.",
    "Tom Ford": "Колекція Private Blend Тома Форда — розкішні, насичені аромати.",
    "Kilian Paris": "Дім Кіліана Еннессі: аромати як твори мистецтва, зокрема колекція «напоїв».",
    "Amouage": "Оманський дім Amouage: ладан, уд і багаті східні композиції.",
    "Nasomatto": "Мікро-бренд Алессандро Гуальтієрі з Амстердама: темні, екстремально стійкі екстракти.",
    "Parfums de Marly": "Французький дім, натхненний придворною парфумерією XVIII століття.",
    "Xerjoff": "Італійський дім із Турина: розкішні флакони й насичені композиції.",
}
POSTS = [
    dict(slug="yak-obraty-nishevyi-aromat", cover="blog-yak-obraty", days=6,
         title="Як обрати нішевий аромат: 5 кроків без помилок",
         excerpt="Як обрати нішевий аромат і не помилитися: ноти, концентрація, тест на шкірі та розпив 2–5 мл перед покупкою флакона.",
         seo_title="Як обрати нішевий аромат: 5 кроків | ACCORD NICHE",
         seo_description="Як обрати нішевий аромат: читаємо піраміду нот, обираємо концентрацію, тестуємо на шкірі й купуємо розпив від 2 мл замість флакона наосліп.",
         keyword="нішевий аромат", cover_alt="Флакони нішевих ароматів різних форм на світлому тлі",
         body="""Нішевий аромат обирають не за рекламою, а за власною шкірою. Повний флакон коштує дорого, тому помилка болить подвійно. Ось п’ять кроків, які допоможуть знайти свій аромат і не переплатити.

## 1. Почніть із сімейства, а не з бренду

Згадайте аромати, які вам уже подобались: свіжі цитрусові, деревні, квіткові, пряні чи солодкі гурманські. Сімейство підкаже напрям пошуку краще за гучну назву. У [каталозі](/catalog) біля кожного аромату вказано сімейство й піраміду нот.

## 2. Читайте піраміду нот правильно

Верхні ноти звучать перші 15–30 хвилин і швидко зникають. Ноти серця тримаються кілька годин і формують характер. Базові ноти лишаються на шкірі до вечора. Якщо вам подобається лише старт, аромат розчарує вже за пів години, тому дивіться передусім на серце й базу.

## 3. Оберіть концентрацію під свій ритм

Eau de Toilette легша й підходить для офісу та спекотних днів. Eau de Parfum насиченіша й стійкіша, її вистачає на робочий день. Extrait de Parfum найщільніший: кілька крапель на весь вечір.

## 4. Тестуйте на шкірі, а не на блотері

Паперова смужка показує задум парфумера, шкіра показує ваш аромат. Нанесіть одне розпилення на зап’ястя й проживіть із ним день. Не тестуйте більше трьох ароматів одночасно — ніс втомлюється, і всі вони почнуть звучати однаково.

## 5. Купіть розпив перед флаконом

Розпив 2 або 5 мл дає кілька днів чесного тесту за ціну кави. Наприклад, [Creed Aventus](/aroma/1-creed-aventus) у форматі 2 мл — зручний спосіб зрозуміти, чи ваш це легендарний ананас із березою.

## Коротко

Обирайте сімейство, дивіться на ноти серця й бази, підбирайте концентрацію під свій день, тестуйте на шкірі й починайте з розпиву. Усі аромати можна замовити від 2 мл у [каталозі](/catalog)."""),
    dict(slug="piramida-not", cover="blog-piramida-not", days=4,
         title="Піраміда нот: що звучить першим, а що лишається до вечора",
         excerpt="Верхні, серцеві й базові ноти на прикладах Baccarat Rouge 540, Santal 33 і Tobacco Vanille.",
         seo_title="Піраміда нот парфуму: верхні, серце, база",
         seo_description="Що таке піраміда нот: як звучать верхні ноти, ноти серця й бази, скільки тримається кожен рівень — пояснюємо на прикладах відомих ароматів.",
         keyword="піраміда нот", cover_alt="Пляшечки з ароматами на тлі зелених і теплих відтінків",
         body="""Піраміда нот — це не маркетинг, а розклад, за яким аромат звучить на шкірі. Розуміючи її, легше обрати парфум і не розчаруватися через годину.

## Верхні ноти: перше враження

Цитруси, легкі прянощі, зелені й фруктові ноти випаровуються першими: за 15–30 хвилин. У Gypsy Water це бергамот, лимон і ялівець, у Layton — яблуко й лаванда.

## Ноти серця: характер аромату

Квіти, прянощі, смоли й деревні акорди проявляються після старту й тримаються кілька годин. У [Baccarat Rouge 540](/aroma/4-maison-francis-kurkdjian-baccarat-rouge-540) серце — амбровий дерев’яний акорд, який і робить аромат упізнаваним.

## Базові ноти: шлейф до вечора

Мускус, ваніль, деревина, смоли й уд — найважчі молекули. Саме вони лишаються на одязі наступного ранку. У Tobacco Vanille база з деревини й сухофруктів підтримує ваніль із тютюном.

## Як цим користуватися

Читайте ноти серця й бази уважніше за верхні. Тестуйте аромат щонайменше 4–6 годин. І порівнюйте два-три кандидати в розпиві 2 мл з [каталогу](/catalog), перш ніж купувати флакон."""),
    dict(slug="edp-chy-edt", cover="blog-edp-chy-edt", days=1,
         title="EDP чи EDT: у чому різниця і що обрати",
         excerpt="Концентрація, стійкість і шлейф без міфів: коли брати Eau de Parfum, коли Eau de Toilette, а коли екстракт.",
         seo_title="EDP чи EDT: різниця концентрацій парфумів",
         seo_description="EDP чи EDT: скільки олій у кожній концентрації, як це впливає на стійкість і шлейф і яку обрати для офісу, вечора та спеки.",
         keyword="EDP чи EDT", cover_alt="Флакони різних концентрацій на бузковому тлі",
         body="""Скорочення на флаконі — не про якість, а про частку ароматичних олій. Від неї залежать стійкість, шлейф і навіть те, як звучить композиція.

## Eau de Toilette (EDT)

Зазвичай 5–15 % олій. Легша, прозоріша, добре звучить у спеку й в офісі. Тримається кілька годин, тож її часто оновлюють протягом дня.

## Eau de Parfum (EDP)

Приблизно 15–20 % олій. Найпопулярніший формат нішевої парфумерії: насичений звук і стійкість на робочий день. Більшість ароматів нашого [каталогу](/catalog) — саме EDP.

## Extrait de Parfum

20 % і більше. Щільний, близький до шкіри, але дуже стійкий. [Black Afgano](/aroma/22-nasomatto-black-afgano) — екстракт, якого вистачає на весь день із двох крапель.

## Що обрати

Для офісу й літа — EDT або легкий EDP. Для вечора й холодної пори — EDP або екстракт. Якщо аромат існує в кількох концентраціях, порівняйте їх у розпиві: різниця буває помітнішою, ніж здається."""),
]


async def _seed(connection) -> dict:
    """Write the test catalog and blog into a fresh sandbox (SQLite connection)."""
    from sqlalchemy import insert
    from shop import models as m
    from shop.services.storefront import aroma_name  # noqa: F401  (grouping rules match the site)
    now = datetime.now(timezone.utc)
    brands = {}
    for index, name in enumerate(BRAND_TEXT, 1):
        brands[name] = index
        await connection.execute(insert(m.Brand).values(id=index, name=name, name_key=name.lower(),
                                                        description=BRAND_TEXT[name], sort_order=index, is_active=True))
    product_id = 0
    for order, aroma in enumerate(AROMAS):
        for volume, price, stock in zip((2, 5, 10), aroma["prices"], aroma["stock"]):
            product_id += 1
            name = f"{aroma['name']} {volume} мл"
            code = "".join(ch for ch in aroma["brand"].upper() if ch.isalpha())[:3]
            await connection.execute(insert(m.Product).values(
                id=product_id, brand_id=brands[aroma["brand"]], brand=aroma["brand"], name=name, name_lower=name.lower(),
                sku=f"TST-{code}-{product_id:04d}", gender=aroma["gender"], volume_ml=volume,
                price=Decimal(price), stock=stock, description=aroma["description"], photo_url=_img(aroma["slug"]),
                is_active=True, is_featured=aroma.get("featured", False), is_new=aroma.get("new", False), sort_order=order,
                concentration=aroma["concentration"], fragrance_family=aroma["family"], top_notes=aroma["top"],
                heart_notes=aroma["heart"], base_notes=aroma["base"], perfumer=aroma["perfumer"],
                release_year=aroma["year"], image_alt=f"Флакон {aroma['brand']} {aroma['name']} — ілюстрація тест-режиму",
                updated_at=now))
    for post_id, post in enumerate(POSTS, 1):
        published = now - timedelta(days=post["days"])
        await connection.execute(insert(m.BlogPost).values(
            id=post_id, slug=post["slug"], title=post["title"], excerpt=post["excerpt"], body=post["body"],
            search_text=(post["title"] + " " + post["excerpt"]).casefold(), cover_url=_img(post["cover"]),
            cover_alt=post["cover_alt"], author_name="Редакція ACCORD NICHE", status="published",
            seo_title=post["seo_title"], seo_description=post["seo_description"], focus_keyword=post["keyword"],
            comments_enabled=False, published_at=published, created_by="test-mode", updated_by="test-mode",
            created_at=published, updated_at=published))
        await connection.execute(insert(m.BlogSlug).values(slug=post["slug"], post_id=post_id))
    return {"aromas": len(AROMAS), "products": product_id, "posts": len(POSTS)}
