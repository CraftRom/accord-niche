"""Test mode: the system administrator turns the sandbox on for the whole website."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import Principal, require_sysadmin
from shop import security_log
from shop.services import test_mode

admin = APIRouter(dependencies=[Depends(require_sysadmin)])
public = APIRouter()


class EnableIn(BaseModel):
    hours: int = Field(test_mode.DEFAULT_HOURS, ge=1, le=test_mode.MAX_HOURS)


@admin.get("")
async def status():
    return test_mode.public(test_mode.state())


@admin.post("")
async def enable(data: EnableIn, who: Principal = Depends(require_sysadmin)):
    try:
        created = await test_mode.enable(who.login, data.hours)
    except test_mode.Unavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    security_log.record("system.test_mode.enabled", actor=who.login, role=who.role.value, reason=f"{data.hours}h")
    return test_mode.public(created)


@admin.delete("")
async def disable(who: Principal = Depends(require_sysadmin)):
    await test_mode.disable()
    security_log.record("system.test_mode.disabled", actor=who.login, role=who.role.value, reason="manual")
    return test_mode.public(None)


@public.get("/status", include_in_schema=False)
async def visitor_status(request: Request):
    """For the website banner: is the site in test mode for this visitor, and until when."""
    data = None if test_mode.crawler(request.headers.get("user-agent", "")) else test_mode.current()
    info = test_mode.public(data)
    return {"active": info["active"], "expires_at": info.get("expires_at")}


@public.get("/media/{name}", include_in_schema=False)
async def media(name: str, request: Request):
    path = test_mode.asset(name)
    if path is None or test_mode.current() is None:
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="image/png", headers={
        "Cache-Control": "private, max-age=3600", "X-Robots-Tag": "noindex", "X-Content-Type-Options": "nosniff"})
