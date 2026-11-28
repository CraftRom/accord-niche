"""Read-only production probes. No submitted route is ever fetched."""
import asyncio
import json
import os
from html.parser import HTMLParser
import re
from defusedxml import ElementTree as ET

import httpx

ORIGIN = "https://accordniche.pp.ua"
DASH = "https://dashboard.accordniche.pp.ua"
SHOP = "https://shop.accordniche.pp.ua"
RIVALS = {
    "benchmark": "https://parfum.kh.ua/creed-aventus-raspiv-5-ml",
    "benchmark-drbeauty": "https://drbeauty.com.ua/ua/creed-aventus--raspiv---v-t-ch--atom---5ml/",
}

# key, view/module, scenario, route, acceptance criterion
CASES = [
    ("sitemap", "seo", "Карта сайту й товарні URL", "/sitemap-aromas.xml", "Карта містить канонічні URL ароматів на основному домені."),
    ("metadata", "seo", "Метатеги й schema.org", "/aroma/…", "На товарній сторінці є title із назвою аромату, description, canonical та коректна Product/Offer розмітка з ціною."),
    ("index", "seo", "Індексація", "Google Search Console", "URL Inspection підтверджує індексацію вибраної картки та правильний canonical."),
    ("links", "seo", "Внутрішня перелінковка", "/catalog", "З каталогу та релевантної статті можна перейти на чинну картку аромату."),
    ("benchmark", "seo", "Creed Aventus 5 мл · Parfum.kh.ua", "/catalog", "Порівняно URL, заголовки, ціну 5 мл, наявність і доставку в обох магазинах."),
    ("benchmark-drbeauty", "seo", "Creed Aventus 5 мл · Dr Beauty", "/catalog", "Порівняно URL, заголовки, ціну 5 мл, наявність і доставку в обох магазинах."),
    ("volumes", "catalog", "Фільтри, об’єми та ціни", "/api/public/aromas", "Для 2, 5 і 10 мл є доступні варіанти з додатною ціною, які відповідають фільтру."),
    ("search", "catalog", "Пошук Creed Aventus 5 мл", "/api/public/aromas", "Пошук повертає доступний Creed Aventus 5 мл із ціною та товарним URL."),
    ("cart", "orders", "Кошик і оформлення", "/checkout", "Додати аромат, змінити кількість, оформити тестове замовлення й звірити підсумок у панелі."),
    ("profile", "profile", "Спільна історія покупок", "/profile", "Після входу клієнт бачить власне контрольне замовлення з Mini App і коректні дані профілю."),
    ("delivery", "delivery", "Адреса та відділення", "Nova Poshta", "Знайти місто, відділення й поштомат, звірити отримувача та доставку тестового замовлення."),
    ("dashboard", "dashboard", "Публічна оболонка Dashboard", DASH, "Домен повертає HTML української панелі магазину."),
    ("blog", "blog", "Блог і модерація коментаря", "/blog", "Опублікувати тестовий коментар, перевірити чергу та видимість після модерації."),
    ("miniapp", "miniapp", "Оболонка Telegram Mini App", SHOP, "Домен повертає HTML Mini App з Telegram Web App SDK."),
    ("telegram", "miniapp", "Вхід із Telegram", SHOP, "Відкрити застосунок через бота й підтвердити профіль тестового покупця."),
    ("heartbeat", "bot", "Стан процесу бота", "bot heartbeat", "API бачить свіжу позначку часу від процесу бота."),
    ("bot", "bot", "Telegram-бот", "/start", "Тестовий покупець отримує відповідь та відкриває правильний магазин."),
    ("api", "api", "Доступність API", DASH + "/api/health", "API повертає HTTP 200 та status=ok."),
    ("database", "database", "Запит до бази", "SELECT 1", "Сесія API отримує 1 у відповідь на SELECT 1."),
    ("redis", "redis", "З’єднання з Redis", "PING", "Налаштований Redis відповідає на PING."),
    ("dns", "domains", "DNS і Cloudflare", "Cloudflare DNS", "Звірити записи трьох доменів, проксі та SSL/TLS із конфігурацією origin."),
    ("edge", "nginx", "Маршрутизація та співіснування", "elfar.pp.ua", "Перевірити окремі vhost, сертифікати та відповіді обох магазинів через edge і origin."),
    ("cert", "certbot", "Поновлення TLS", "Certbot", "Журнал тестового поновлення підтверджує всі потрібні імена й успішне перечитування Nginx."),
    ("access", "security", "Права на аудит", "/api/store-audit", "Обидві адміністративні ролі мають доступ. Для менеджера повертається 403, без сесії — 401."),
]
AUTO = {"metadata", "api", "database", "redis", "sitemap", "volumes", "search", "dashboard", "miniapp"}


async def fetch(client, url):
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        if response.headers.get("x-accord-test-mode") == "1":
            raise ValueError("Тестовий режим вітрини")
        buf = bytearray()
        async for chunk in response.aiter_bytes(32768):
            buf.extend(chunk)
            if len(buf) > 4_000_000:
                raise ValueError("Завелика відповідь")
        return bytes(buf)


def checked(ok, message):
    return ("pass" if ok else "fail", message)


class PageHead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag = None
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.schemas = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.tag = "title"
        elif tag == "script" and values.get("type") == "application/ld+json":
            self.tag = "schema"
        elif tag == "meta" and values.get("name") == "description":
            self.description = values.get("content", "")
        elif tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href", "")

    def handle_endtag(self, tag):
        if tag in ("title", "script"):
            self.tag = None

    def handle_data(self, data):
        if self.tag == "title":
            self.title += data
        elif self.tag == "schema":
            self.schemas.append(json.loads(data))


async def product_metadata(client):
    catalog = json.loads(await fetch(client, ORIGIN + "/api/public/aromas?limit=1"))
    if not catalog["items"]:
        return "unknown", "Каталог порожній: немає картки для тесту."
    item = catalog["items"][0]
    if not re.fullmatch(r"/aroma/[1-9]\d*-[a-z0-9-]+", item["path"]):
        return "fail", "Каталог повернув некоректний шлях картки."
    url = ORIGIN + item["path"]
    head = PageHead()
    head.feed((await fetch(client, url)).decode())
    products = []
    for node in head.schemas:
        if isinstance(node, dict) and node.get("@type") == "ProductGroup":
            products.extend(node.get("hasVariant", []))
        elif isinstance(node, dict) and node.get("@type") == "Product":
            products.append(node)
    offers = bool(products) and all(p.get("offers", {}).get("@type") == "Offer"
        and p["offers"].get("priceCurrency") == "UAH" and float(p["offers"].get("price", 0)) > 0
        for p in products)
    criteria = {"title аромату": item["name"].casefold() in head.title.casefold(),
                "description": bool(head.description.strip()), "canonical": head.canonical == url,
                "Product/Offer": offers}
    return checked(all(criteria.values()), url + "\n" + "\n".join(
        f"{name} · {'так' if ok else 'ні'}" for name, ok in criteria.items()))


async def public_probe(key, client):
    if key == "metadata":
        return await product_metadata(client)
    if key == "sitemap":
        root = ET.fromstring(await fetch(client, ORIGIN + "/sitemap-aromas.xml"))
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        urls = [node.text or "" for node in root.findall(f"{ns}url/{ns}loc")]
        ok = root.tag == ns + "urlset" and urls and all(
            re.fullmatch(r"https://accordniche\.pp\.ua/aroma/[1-9]\d*-[a-z0-9-]+", u) for u in urls)
        return checked(ok, f"Товарних URL: {len(urls)}. Формат і домен: {'коректні' if ok else 'перевірити'}.")
    if key in ("dashboard", "miniapp"):
        domain, marker = (DASH, "<title>Панель магазину</title>") if key == "dashboard" else (SHOP, "https://telegram.org/js/telegram-web-app.js")
        body = (await fetch(client, domain)).decode()
        return checked(marker in body, f"{domain} · HTTP 200 · ознака застосунку: {marker in body}")
    if key == "api":
        data = json.loads(await fetch(client, DASH + "/api/health"))
        return checked(data.get("status") == "ok", f"HTTP 200 · status=ok: {data.get('status') == 'ok'}")
    evidence = []
    for volume in ([5] if key == "search" else [2, 5, 10]):
        path = f"/api/public/aromas?available=true&volume={volume}&limit=8"
        if key == "search":
            path += "&q=Creed%20Aventus"
        rows = json.loads(await fetch(client, ORIGIN + path))["items"]
        valid = bool(rows)
        for row in rows:
            valid &= bool(re.fullmatch(r"/aroma/[1-9]\d*-[a-z0-9-]+", row["path"]))
            valid &= row["volumes"] == [volume] and float(row["min_price"]) > 0 and row["stock"] > 0
            if key == "search":
                valid &= "creed aventus" in (row["brand"] + " " + row["name"]).casefold()
        evidence.append(f"{path}: перевірено {len(rows)}, відповідність {bool(valid)}")
        if not valid:
            return "fail", "\n".join(evidence)
    return "pass", "\n".join(evidence)


def automatic(key, env):
    if key in ("database", "redis", "heartbeat"):
        return env == os.getenv("STORE_AUDIT_ENV", "local")
    return key in AUTO and env == "production"


async def run_probe(key, repo):
    from sqlalchemy import text
    from redis import asyncio as redis
    from shop.services.realtime import _redis_url
    try:
        async with asyncio.timeout(12):
            if key == "heartbeat":
                from shop.worker_health import state
                heartbeat = await asyncio.to_thread(state, "bot")
                return checked(heartbeat["running"], f"Вік останньої позначки, с: {heartbeat['age_seconds']}")
            if key == "database":
                value = await repo.s.scalar(text("SELECT 1"))
                return checked(value == 1, f"SELECT 1 → {value}")
            if key == "redis":
                url = _redis_url()
                if not url:
                    return "unknown", "Адресу Redis не налаштовано."
                async with redis.from_url(url, socket_connect_timeout=3, socket_timeout=3) as client:
                    return checked(await client.ping(), "Відповідь на PING отримано.")
            async with httpx.AsyncClient(timeout=4, follow_redirects=False) as client:
                return await public_probe(key, client)
    except httpx.HTTPStatusError as exc:
        return checked(False, f"{exc.request.url.path}: HTTP {exc.response.status_code}")
    except Exception as exc:
        # Errors may contain credentials or internal addresses. Keep only their class.
        await repo.s.rollback()
        return "unknown", f"Не вдалося завершити перевірку: {type(exc).__name__}"
