"""Administrative store audit with append-only, optimistic revisions."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from api.auth import Principal, require_admin
from shop.build import release_id
from shop.models import StoreAuditEvent as Event
from shop.repo.factory import get_repo
from shop.services.store_checks import CASES, RIVALS, automatic, run_probe

router = APIRouter(prefix="/api/store-audit", dependencies=[Depends(require_admin)])
Env = Literal["production", "staging", "local"]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=3000)]
Module = Literal["seo", "catalog", "orders", "profile", "delivery", "dashboard", "blog", "miniapp",
                 "bot", "api", "database", "redis", "domains", "nginx", "certbot", "security"]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Details(Payload):
    title: Short
    module: Module
    route: Short
    expected: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]
    keyword: Note = ""
    symptom: Note = ""
    steps: Note = ""
    risk: Note = ""
    dependencies: Note = ""
    team: Note = ""
    link: Note = ""
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    assessment: Literal["assumption", "risk"] = "assumption"
    workflow: Literal["open", "working", "retest"] = "open"
    competitor: Note = ""


class Edit(Payload):
    version: int = Field(ge=0)
    details: Details


class Comparison(Payload):
    store: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]
    rival: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]


class Test(Payload):
    comparison: Comparison | None = None
    version: int = Field(ge=0)
    outcome: Literal["pass", "fail", "unknown"] | None = None
    actual: Note = ""
    log: Note = ""


def fresh(key, details, env):
    return dict(id=key, details=details, environment=env, version=0, type="auto" if
                automatic(key, env) else "manual", result="unknown", status="open",
                checked=None, actual="", log="", attempts=0, failed=False)


def defaults(env):
    rows = {}
    for key, module, title, route, expected in CASES:
        details = Details(title=title, module=module, route=route, expected=expected, steps=expected)
        if key in RIVALS or key == "search":
            details.keyword = "Creed Aventus на розпив 5 мл"
        if key in RIVALS:
            details.competitor = RIVALS[key]
        rows[key] = fresh(key, details.model_dump(), env)
    return rows


async def current(repo, env, key):
    event = await repo.s.scalar(select(Event).where(Event.environment == env, Event.item == key)
                                .order_by(Event.version.desc()).limit(1))
    row = event.snapshot if event else defaults(env).get(key)
    if not row:
        raise HTTPException(404, "Запис не знайдено")
    return dict(row)


def conflict():
    return HTTPException(409, "Запис уже змінився. Оновіть сторінку та звірте результат.")


async def append(repo, row, actor, action):
    row["version"] += 1
    repo.s.add(Event(environment=row["environment"], item=row["id"], version=row["version"],
                     actor=actor, action=action, created=datetime.now(timezone.utc), snapshot=row))
    try:
        await repo.s.commit()
    except IntegrityError:
        await repo.s.rollback()
        raise conflict() from None
    return row


@router.get("")
async def workspace(environment: Env = "production", repo=Depends(get_repo)):
    latest = (select(Event.item, func.max(Event.version).label("version"))
              .where(Event.environment == environment).group_by(Event.item).subquery())
    snapshots = await repo.s.scalars(select(Event.snapshot).join(latest, and_(
        Event.item == latest.c.item, Event.version == latest.c.version)).where(Event.environment == environment))
    rows = defaults(environment)
    rows.update((s["id"], s) for s in snapshots)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    blockers = [k for k, r in rows.items() if r["status"] not in ("verified", "fixed")
                or r.get("build") != release_id() or datetime.fromisoformat(r["checked"]) < cutoff]
    return {"items": list(rows.values()), "blockers": blockers, "ready": bool(rows) and not blockers}


@router.post("", status_code=201)
async def create(details: Details, environment: Env, who: Principal = Depends(require_admin), repo=Depends(get_repo)):
    row = fresh(uuid4().hex, details.model_dump(), environment)
    row["status"] = details.workflow
    return await append(repo, row, who.login, "create")


@router.put("/{key}")
async def edit(key: str, body: Edit, environment: Env, who: Principal = Depends(require_admin), repo=Depends(get_repo)):
    row = await current(repo, environment, key)
    if row["version"] != body.version:
        raise conflict()
    details = body.details.model_dump()
    if row["type"] == "auto" and any(details[k] != row["details"][k] for k in ("module", "title", "route", "keyword", "expected")):
        raise HTTPException(422, "Умови вбудованої перевірки визначає її реалізація.")
    if details != row["details"]:
        # Evidence for a previous revision remains in history.
        row.update(details=details, attempts=0, status=details["workflow"], checked=None,
                   actual="", log="", result="unknown", comparison=None)
        return await append(repo, row, who.login, "edit")
    return row


@router.post("/{key}/test")
async def test_item(key: str, body: Test, environment: Env, who: Principal = Depends(require_admin), repo=Depends(get_repo)):
    row = await current(repo, environment, key)
    if row["version"] != body.version:
        raise conflict()
    if row["type"] == "auto":
        if body.outcome or body.actual or body.log or body.comparison:
            raise HTTPException(422, "Автоматична перевірка сама формує доказ.")
        result, actual = await run_probe(key, repo)
        log = actual
    else:
        if not body.outcome or not body.actual or not body.log:
            raise HTTPException(422, "Запишіть результат, спостереження та доказ нового тесту.")
        if key in RIVALS and not body.comparison:
            raise HTTPException(422, "Запишіть спостереження для кожного магазину.")
        result, actual, log = body.outcome, body.actual, body.log
        if result == "pass" and row["log"] == log:
            raise HTTPException(422, "Додайте доказ нового запуску: час, ID тесту або посилання на журнал.")
    status = {"fail": "failed", "pass": "retest", "unknown": "inconclusive"}[result]
    if result == "pass" and row.get("build") == release_id() and row["result"] in ("fail", "pass"):
        status = "fixed" if row["failed"] else "verified"
    row["comparison"] = body.comparison.model_dump() if body.comparison else None
    row.update(build=release_id(), result=result, actual=actual, log=log, status=status,
               checked=datetime.now(timezone.utc).isoformat(), attempts=row["attempts"] + 1,
               failed=row["failed"] or result == "fail")
    return await append(repo, row, who.login, "test")


@router.get("/{key}/history")
async def history(key: str, environment: Env, before: int | None = Query(None, ge=1), repo=Depends(get_repo)):
    query = select(Event).where(Event.environment == environment, Event.item == key)
    if before:
        query = query.where(Event.version < before)
    events = await repo.s.scalars(query.order_by(Event.version.desc()).limit(30))
    return [dict(actor=e.actor, action=e.action, date=e.created, row=e.snapshot) for e in events]
