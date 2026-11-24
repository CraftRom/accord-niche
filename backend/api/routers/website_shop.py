"""ACCORD website checkout, Google identity and verified cross-channel history.

Runs without Telegram, Google or an SMS gateway (guest orders still work).
All payments, discounts, inventory reservations and CRM queueing reuse shop_service.
The website shares users/orders/products with the bot and Mini App, not a copy.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import case, delete, func, or_, select, update

from api.routers.shop import AttributionIn, CheckoutIn, _orders_payload
from api.webapp_auth import InitDataError, parse_init_data
from shop import models as m
from shop.config import settings
from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services import shop_service as svc
from shop.services import novaposhta as np
from shop.services import phone_verification
from shop.services.shop_settings import get_shop_settings
from shop.services.website_identity import _owned_user_ids, attach_guest_identity
from shop.services.attribution import clean_attribution

log = logging.getLogger(__name__)
router = APIRouter()
SESSION_NAME = 'accord_session'
CSRF_NAME = 'accord_csrf'


def _session_cookie(request: Request):
    return '__Host-accord_session' if _secure(request) else SESSION_NAME

def _csrf_cookie(request: Request):
    return '__Host-accord_csrf' if _secure(request) else CSRF_NAME
SESSION_DAYS = 14
_GOOGLE_CERTS_URL = 'https://www.googleapis.com/oauth2/v3/certs'
_google_jwks = None
_google_jwks_until = 0.0


def _now():
    return datetime.now(timezone.utc)


def _hash(raw: str):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _secure(request: Request):
    # Never let an untrusted client spoof X-Forwarded-Proto and trick us into
    # altering cookie security / accepting Google login over plaintext.
    from api.request_log import trusted_proxy
    if trusted_proxy(request):
        return request.headers.get('x-forwarded-proto', request.url.scheme) == 'https'
    return request.url.scheme == 'https'


def _website_origin(request: Request):
    return f"{'https' if _secure(request) else 'http'}://{request.headers.get('host', '')}"


def _require_csrf(request: Request):
    # Both Origin and double-submit cookie required, including guest checkout.
    origin = request.headers.get('origin', '').rstrip('/')
    if not origin or not hmac.compare_digest(origin, _website_origin(request)):
        raise HTTPException(403, 'Запит із непідтвердженого сайту')
    cookie = request.cookies.get(_csrf_cookie(request), '')
    header = request.headers.get('x-csrf-token', '')
    if not cookie or not header or len(cookie) != 48 or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, 'Оновіть сторінку та повторіть дію')


def _set_csrf(request: Request, response: Response):
    existing = request.cookies.get(_csrf_cookie(request), '')
    token = existing if len(existing) == 48 and all(c in '0123456789abcdef' for c in existing) else secrets.token_hex(24)
    response.set_cookie(_csrf_cookie(request), token, path='/', max_age=SESSION_DAYS*86400,
                        samesite='strict', secure=_secure(request), httponly=False)
    return token


async def _account(request: Request, repo: Repository):
    raw = request.cookies.get(_session_cookie(request), '')
    if not (32 <= len(raw) <= 128):
        return None
    entry = await repo.s.scalar(select(m.WebsiteSession).where(
        m.WebsiteSession.token_hash == _hash(raw), m.WebsiteSession.expires_at > _now()
    ))
    if not entry:
        return None
    account = await repo.s.get(m.WebsiteAccount, entry.account_id)
    if not account:
        return None
    user = await repo.get_user(account.user_id)
    if not user or user.is_blocked:
        raise HTTPException(403, 'Профіль заблоковано')
    return account


async def _required_account(request: Request, repo: Repository):
    account = await _account(request, repo)
    if not account:
        raise HTTPException(401, 'Спочатку відкрийте оформлення або увійдіть у профіль')
    return account


async def _new_session(repo: Repository, request: Request, response: Response, account: m.WebsiteAccount):
    token = secrets.token_urlsafe(48)
    repo.s.add(m.WebsiteSession(
        account_id=account.id, token_hash=_hash(token), expires_at=_now()+timedelta(days=SESSION_DAYS)
    ))
    await repo.s.commit()
    response.set_cookie(_session_cookie(request), token, path='/', max_age=SESSION_DAYS*86400,
                        samesite='lax', secure=_secure(request), httponly=True)


async def _guest_account(request: Request, response: Response, repo: Repository,
                         *, issue_session=True, reuse_existing=True):
    # Google account switching MUST create a new user; a signed-in Google
    # account must never be overwritten with the next Google credential.
    if reuse_existing:
        existing = await _account(request, repo)
        if existing:
            return existing
    # Negative Telegram ID is reserved for website-only users; the bot never
    # sees it as a real chat ID, avoiding a schema fork of orders/users.
    for attempt in range(5):
        fake_tg = -(secrets.randbits(61) + 1)
        if not await repo.get_user_by_tg(fake_tg):
            break
    else:
        raise HTTPException(503, 'Не вдалося створити профіль')
    user = await repo.create_user(fake_tg, None, None, None)
    # No Telegram chat exists for an anonymous browser customer.
    await repo.s.execute(update(m.User).where(m.User.id == user.id).values(bot_reachable=False))
    account = m.WebsiteAccount(user_id=user.id)
    repo.s.add(account)
    await repo.s.commit()
    await repo.s.refresh(account)
    if issue_session:
        await _new_session(repo, request, response, account)
    return account


def _display(account):
    if account is None:
        return {'signed_in': False, 'has_session': False}
    return {
        'signed_in': bool(account.google_sub),
        'account_key': _hash('accord-account:'+str(account.id))[:24],
        'has_session': True,
        'name': account.display_name or '',
        'email': account.email if account.google_sub else None,
        'phone': account.verified_phone or None,
        'phone_verified': bool(account.verified_phone),
        'telegram_linked': bool(account.linked_telegram_user_id),
    }


@router.get('/session')
async def session(request: Request, response: Response, repo: Repository = Depends(get_repo)):
    csrf = _set_csrf(request, response)
    account = await _account(request, repo)
    shop = await get_shop_settings(repo)
    return {'csrf': csrf, 'account': _display(account),
            'google_client_id': shop.site('google_client_id'),
            'phone_verification_enabled': shop.sms_ready or phone_verification.telegram_ready(),
            'phone_sms_enabled': shop.sms_ready,
            'phone_telegram_enabled': phone_verification.telegram_ready()}


def android_client_ids() -> frozenset[str]:
    """OAuth client IDs of the shop's own Android app (comma separated env).

    Android Credential Manager asks Google for an ID token for the website's
    (server) client, so ``aud`` is the same web client ID; ``azp`` is the
    Android client that requested it. Only these IDs may stand in for it.
    """
    raw = os.getenv('ACCORD_GOOGLE_ANDROID_CLIENT_IDS', '')
    return frozenset(part.strip() for part in raw.replace(';', ',').split(',')
                     if re.fullmatch(r'[0-9]{6,32}-[a-z0-9]{8,64}\.apps\.googleusercontent\.com', part.strip()))


async def _google_identity(token: str, client_id: str):
    client_id = (client_id or '').strip()
    if not client_id:
        raise HTTPException(503, 'Вхід через Google ще не налаштовано')
    if len(token) > 8192:
        raise HTTPException(400, 'Некоректний Google токен')
    global _google_jwks, _google_jwks_until
    try:
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
            raise ValueError('Unsupported signing algorithm')
        if _google_jwks is None or time.monotonic() >= _google_jwks_until:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
                response = await client.get(_GOOGLE_CERTS_URL)
                response.raise_for_status()
                keys = response.json()
                if not isinstance(keys.get('keys'), list):
                    raise ValueError('Google JWKS malformed')
                _google_jwks = keys
                _google_jwks_until = time.monotonic() + 1800
        match = next((k for k in _google_jwks['keys'] if k.get('kid') == header['kid'] and k.get('kty') == 'RSA'), None)
        if not match:
            # Google rotates keys. Refresh once when kid changes.
            _google_jwks_until = 0
            raise ValueError('Google signing key changed; retry')
        public_key = jwt.PyJWK.from_dict(match).key
        claims = jwt.decode(token, public_key, algorithms=['RS256'],
                            audience=client_id,
                            issuer=['accounts.google.com', 'https://accounts.google.com'],
                            options={'require': ['iss', 'aud', 'exp', 'iat', 'sub']}, leeway=30)
        if not claims.get('email_verified') or not claims.get('sub') or not claims.get('email'):
            raise ValueError('Google email is not verified')
        if claims.get('azp') and claims['azp'] != client_id and claims['azp'] not in android_client_ids():
            raise ValueError('Google authorized party mismatch')
        return claims
    except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, StopIteration) as exc:
        log.warning('Google identity verification failed: %s', type(exc).__name__)
        raise HTTPException(401, 'Не вдалося підтвердити Google-вхід') from None


class GoogleIn(BaseModel):
    credential: str = Field(min_length=100, max_length=8192)


@router.post('/auth/google')
async def google_login(data: GoogleIn, request: Request, response: Response,
                       repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    if not _secure(request) and urlsplit(_website_origin(request)).hostname not in {'localhost','127.0.0.1'}:
        raise HTTPException(403, 'Google-вхід доступний лише через HTTPS')
    identity = await _google_identity(data.credential, (await get_shop_settings(repo)).site('google_client_id'))
    sub = str(identity['sub'])
    account = await repo.s.scalar(select(m.WebsiteAccount).where(m.WebsiteAccount.google_sub == sub))
    previous = await _account(request, repo)
    email = str(identity['email'])[:255]
    name = str(identity.get('name') or email.split('@')[0])[:255]
    if account is None:
        if previous is not None and not previous.google_sub:
            account = previous
        else:
            account = await _guest_account(request, response, repo,
                                           issue_session=False, reuse_existing=False)
        account.google_sub = sub
    elif previous is not None and previous.id != account.id and not previous.google_sub:
        await attach_guest_identity(repo, account, previous)
    account.email = email
    account.display_name = name
    # Rotate only the invoking browser session. Other signed-in devices
    # must remain signed in after a normal Google login.
    old_raw = request.cookies.get(_session_cookie(request), '')
    if old_raw:
        await repo.s.execute(delete(m.WebsiteSession).where(
            m.WebsiteSession.token_hash == _hash(old_raw)))
    await repo.s.commit()
    await _new_session(repo, request, response, account)
    return {'account': _display(account)}


@router.post('/auth/logout')
async def logout(request: Request, response: Response, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    raw = request.cookies.get(_session_cookie(request), '')
    if raw:
        await repo.s.execute(delete(m.WebsiteSession).where(m.WebsiteSession.token_hash == _hash(raw)))
        await repo.s.commit()
    response.delete_cookie(_session_cookie(request), path='/')
    return {'ok': True}


class CartLineIn(BaseModel):
    product_id: int = Field(gt=0)
    qty: int = Field(ge=1, le=99)

class QuoteIn(BaseModel):
    items: list[CartLineIn] = Field(min_length=1, max_length=30)
    promo_code: str | None = Field(None, max_length=64)
    use_bonus: bool = False
    terms_accepted: bool = False


async def _sync_cart(repo, user_id, items):
    if len({line.product_id for line in items}) != len(items):
        raise HTTPException(422, 'Один аромат вказано декілька разів')
    try:
        # One DB transaction, not clear + N independently committed inserts.
        await repo.replace_cart(user_id, [(line.product_id, line.qty) for line in items])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/checkout/quote')
async def quote(data: QuoteIn, request: Request, response: Response, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _guest_account(request, response, repo)
    user = await repo.get_user(account.user_id)
    await _sync_cart(repo, user.id, data.items)
    try:
        q = await svc.checkout_quote(repo, user, promo_code=data.promo_code,
                                     use_bonus=data.use_bonus)
    except svc.CheckoutQuoteError as exc:
        raise HTTPException(409, str(exc)) from exc
    result = q.payload()
    result['items'] = [{'product_id':line.product_id,'qty':line.qty,
                        'name':line.product.name,'unit_price':f'{line.product.price:.2f}',
                        'line_total':f'{line.line_total:.2f}'} for line in q.lines]
    return result


class WebsiteCheckoutIn(CheckoutIn):
    # The website must confirm a server-calculated quote and use durable retries.
    checkout_key: str = Field(min_length=12, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    quote_token: str = Field(pattern=r'^[a-f0-9]{64}$')
    terms_accepted: bool = False

    @field_validator('contact_phone')
    @classmethod
    def ascii_phone(cls,value):
        if not value.isascii():
            raise ValueError('Використовуйте цифри 0–9 у номері телефону')
        return value

    @model_validator(mode='after')
    def full_name_fits_database(self):
        full_name=' '.join(part for part in [self.contact_surname,self.contact_name,self.contact_patronymic] if part)
        if len(full_name)>255:
            raise ValueError('Скоротіть ПІБ: загалом не більше 255 символів')
        return self


@router.get('/checkout/status')
async def checkout_status(request: Request, checkout_key: str = Query(min_length=12,max_length=64,pattern=r'^[A-Za-z0-9_-]+$'),
                          repo: Repository = Depends(get_repo)):
    account = await _required_account(request,repo)
    owned = await _owned_user_ids(repo,account)
    order = await repo.get_order_by_checkout_key(checkout_key)
    if order is None or order.user_id not in owned:
        return {'found':False}
    return {'found':True,'order_id':order.id,'total':order.total,'payment_method':order.payment_method,'replayed':True}


def _client_channel(attribution: dict | None) -> str:
    """Sales channel of a /api/web request: the Android app marks itself, everything else is the website.

    Only reporting depends on it (dashboard channel, funnel); prices, stock and
    permissions are identical for both clients.
    """
    source = str((attribution or {}).get('source') or '').strip().lower()
    return m.APP_CHANNEL if source == m.APP_CHANNEL else m.WEBSITE_CHANNEL


_VISIT_BOT_RE = re.compile(r"bot|crawler|spider|slurp|facebookexternalhit|preview|monitor|uptime|headless", re.I)


class WebsiteVisitIn(BaseModel):
    session_id: str = Field(..., min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    attribution: AttributionIn = Field(default_factory=AttributionIn)


@router.post('/analytics/visit', status_code=204)
async def website_visit(data: WebsiteVisitIn, request: Request, repo: Repository = Depends(get_repo)):
    """First-party visit of the main website: the conversion denominator (A07).

    Anonymous by design: no cookie, IP or user agent is stored, only the
    random per-tab id and the UTM labels. Only the site's own origin may
    record a visit; crawlers are acknowledged but not counted; a repeated
    POST of the same visit is a no-op. Nginx rate-limits the route.
    """
    origin = request.headers.get('origin', '').rstrip('/')
    if not origin or not hmac.compare_digest(origin, _website_origin(request)):
        raise HTTPException(403, 'Запит із непідтвердженого сайту')
    if _VISIT_BOT_RE.search(request.headers.get('user-agent', '')):
        return Response(status_code=204)
    from shop.services.analytics import record_website_visit
    attribution = data.attribution.model_dump(exclude={'session_id'})
    if not attribution.get('source') or attribution['source'] == 'unknown':
        attribution = {**attribution, 'source': 'accord_website', 'medium': attribution.get('medium') or 'website'}
    await record_website_visit(repo.s, data.session_id, attribution, _client_channel(attribution))
    return Response(status_code=204)


@router.post('/checkout')
async def checkout(data: WebsiteCheckoutIn, request: Request, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    user = await repo.get_user(account.user_id)
    if not data.terms_accepted:
        raise HTTPException(422, 'Підтвердьте згоду з умовами замовлення')
    # No duplicates on network retries, including after the cart was cleared.
    if data.checkout_key:
        existing = await repo.get_order_by_checkout_key(data.checkout_key)
        if existing:
            if existing.user_id not in await _owned_user_ids(repo,account):
                raise HTTPException(409, 'Ключ замовлення вже використано')
            return {'order_id': existing.id, 'total': existing.total,
                    'payment_method': existing.payment_method, 'replayed': True}
    shop_now = await get_shop_settings(repo)
    if data.delivery_method == 'courier' and not shop_now.delivery_courier_enabled:
        raise HTTPException(422, 'Курʼєрська доставка недоступна')
    if data.delivery_method in (None, 'warehouse') and not data.address.strip():
        raise HTTPException(422, 'Вкажіть номер та адресу відділення або поштомата')
    if data.delivery_method == 'courier' and data.delivery_warehouse_ref:
        raise HTTPException(422, 'Для курʼєрської доставки не передавайте код відділення')
    if data.delivery_warehouse_ref and not data.delivery_city_ref:
        raise HTTPException(422, 'Для вибраного відділення потрібен населений пункт із довідника')
    # Website attribution must be distinct from Telegram analytics. The visit
    # id is kept only when that visit was really recorded (A07 funnel).
    from shop.services.analytics import website_checkout_session
    channel = _client_channel(data.attribution.model_dump() if data.attribution else None)
    visit_id = await website_checkout_session(repo.s, data.attribution.session_id if data.attribution else None, channel)
    order, error = await svc.create_order(
        repo, user, contact_surname=data.contact_surname, contact_name=data.contact_name,
        contact_patronymic=data.contact_patronymic, contact_phone=data.contact_phone,
        city=data.city, address=data.address, payment_method=data.payment_method,
        delivery_method=data.delivery_method or 'warehouse',
        delivery_city_ref=data.delivery_city_ref, delivery_warehouse_ref=data.delivery_warehouse_ref,
        promo_code=data.promo_code, use_bonus=data.use_bonus, comment=data.comment,
        checkout_key=data.checkout_key, expected_quote=data.quote_token,
        attribution={**clean_attribution(data.attribution.model_dump() if data.attribution else
            {'source':'accord_website','medium':'website'}),'channel':channel,
            **({'session_id': visit_id} if visit_id else {})},
    )
    if error or order is None:
        return JSONResponse(status_code=409,content={
            'detail':error or 'Не вдалося оформити замовлення','code':'checkout_changed'})
    # Same manager notification pipeline as Mini App. Dashboard always gets a
    # durable event, even with no configured Telegram token/process.
    if not getattr(order, 'checkout_replayed', False):
        try:
            from shop.services.notifications import notify_new_order
            bot = None
            if settings.bot_token:
                try:
                    from api.routers.telegram import _instances
                    bot, _ = _instances()
                except Exception:
                    log.warning('Telegram notification unavailable for website order %s', order.id)
            await notify_new_order(bot, repo, order, user)
        except Exception:
            log.exception('Website order %s saved; notification failed', order.id)
    return {'order_id': order.id, 'total': order.total,
            'payment_method': order.payment_method, 'replayed': bool(order.checkout_replayed)}


@router.get('/orders')
async def orders(request: Request, limit: int = Query(30, ge=1, le=60),
                 offset: int = Query(0, ge=0, le=5000),
                 repo: Repository = Depends(get_repo)):
    account = await _required_account(request, repo)
    ids = await _owned_user_ids(repo, account)
    # All proven identities share one timeline. The database merges and pages
    # it (created_at desc, id desc): a deep page no longer reads every earlier
    # order of every identity into memory (A12).
    result = await _orders_payload(repo, ids, limit=limit + 1, offset=offset)
    return {'items': result[:limit], 'has_more': len(result) > limit}


@router.get('/checkout/defaults')
async def checkout_defaults(request: Request, repo: Repository = Depends(get_repo)):
    account = await _required_account(request, repo)
    ids = await _owned_user_ids(repo, account)
    row = await repo.s.scalar(select(m.Order).where(m.Order.user_id.in_(ids))
                              .order_by(m.Order.created_at.desc()).limit(1))
    if not row:
        # Account display names may be nicknames or full Google names. They
        # are not a verified first name for a shipment recipient.
        return {'contact_name':'', 'contact_phone':account.verified_phone or ''}
    # Shipping fields from the customer's own last order, not product/CRM data.
    return {'contact_surname': row.contact_surname or '',
            'contact_name': ((row.contact_name or '').removeprefix((row.contact_surname or '') + ' ').removesuffix(' ' + (row.contact_patronymic or '')) if row.contact_surname else row.contact_name or account.display_name or ''),
            'contact_patronymic':row.contact_patronymic or '',
            'contact_phone': account.verified_phone or row.contact_phone or '',
            'city':row.delivery_city or '', 'address':row.delivery_address or '',
            'delivery_method':row.delivery_method or 'warehouse',
            'delivery_city_ref':row.delivery_city_ref or '',
            'delivery_warehouse_ref':row.delivery_warehouse_ref or '',
            'payment_method':row.payment_method or 'cod'}


@router.post('/orders/{order_id}/cancel')
async def cancel_order(order_id: int, request: Request, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    ids = set(await _owned_user_ids(repo, account))
    row = await repo.get_order(order_id)
    if not row or row.user_id not in ids:
        raise HTTPException(404, 'Замовлення не знайдено')
    from shop.entities import OrderStatus
    if row.status == OrderStatus.CANCELLED:
        return {'cancelled':True}
    if row.status not in {OrderStatus.NEW, OrderStatus.ACCEPTED}:
        raise HTTPException(409,'Замовлення вже в роботі. Зверніться до менеджера')
    try:
        await svc.change_order_status(repo, row, OrderStatus.CANCELLED)
    except svc.OrderStateConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        from shop.services.notifications import notify_cancelled_by_client
        owner = await repo.get_user(row.user_id)
        await notify_cancelled_by_client(None, repo, row, owner)
    except Exception:
        log.warning('Order %s cancelled without Telegram notification', order_id, exc_info=True)
    return {'cancelled':True}


@router.get('/profile')
async def profile(request: Request, repo: Repository = Depends(get_repo)):
    account = await _required_account(request, repo)
    ids = await _owned_user_ids(repo, account)
    details = await repo.get_user(account.user_id)
    # Only the latest order is shown here; the full history is paged by /orders.
    results = await _orders_payload(repo, ids, limit=1)
    recent = results[0] if results else None
    total_orders = await repo.count_filtered_orders(user_id=ids)
    latest_delivery = await checkout_defaults(request, repo)
    return {'account': _display(account), 'orders_count': total_orders,
            'bonus_balance': str(details.bonus_balance or 0),
            'last_order': recent, 'latest_delivery': latest_delivery,
            'history_limited': total_orders > len(results)}


class ProfileIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=100)

    @field_validator('display_name',mode='before')
    @classmethod
    def clean_name(cls,value):
        return value.strip() if isinstance(value,str) else value


@router.patch('/profile')
async def patch_profile(data: ProfileIn, request: Request, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    if not account.google_sub:
        raise HTTPException(401, 'Для редагування профілю потрібен Google-вхід')
    account.display_name = data.display_name.strip()
    await repo.s.commit()
    return {'account': _display(account)}


def _phone(raw: str):
    digits = ''.join(c for c in str(raw) if c.isdigit())
    if digits.startswith('380') and len(digits) == 12:
        body = digits[3:]
    elif digits.startswith('80') and len(digits) == 11:
        body = digits[2:]
    elif digits.startswith('0') and len(digits) == 10:
        body = digits[1:]
    else:
        raise HTTPException(422, 'Номер має бути українським (+380XXXXXXXXX)')
    if not body or body[0] not in '3456789':
        raise HTTPException(422, 'Невірний формат номера')
    return '+380' + body


class PhoneIn(BaseModel):
    phone: str = Field(min_length=10, max_length=32)


class PhoneCheckIn(PhoneIn):
    code: str = Field(min_length=4, max_length=10, pattern=r'^\d{4,10}$')


@router.post('/profile/phone/send')
async def phone_send(data: PhoneIn, request: Request, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    if not account.google_sub:
        raise HTTPException(401, 'Увійдіть через Google для привʼязки номера')
    shop = await get_shop_settings(repo)
    if not shop.sms_ready:
        raise HTTPException(503, 'SMS-підтвердження ще не підключено')
    if not _secure(request) and urlsplit(_website_origin(request)).hostname not in {'localhost','127.0.0.1'}:
        raise HTTPException(403, 'Підтвердження номера доступне лише через HTTPS')
    phone = _phone(data.phone)
    account_id = account.id
    now = _now()
    minute_ago, hour_ago = now - timedelta(seconds=60), now - timedelta(hours=1)
    # One compare-and-set UPDATE: two parallel requests can no longer both pass
    # the minute gate after reading the same row, and the hourly counter
    # cannot lose an increment (lost update) between them.
    window = m.WebsiteAccount.phone_window_at
    fresh_window = or_(window.is_(None), window < hour_ago)
    claimed = await repo.s.execute(update(m.WebsiteAccount).where(
        m.WebsiteAccount.id == account_id,
        or_(m.WebsiteAccount.phone_send_at.is_(None), m.WebsiteAccount.phone_send_at <= minute_ago),
        or_(fresh_window, func.coalesce(m.WebsiteAccount.phone_window_count, 0) < 5),
    ).values(
        phone_send_at=now,
        phone_window_at=case((fresh_window, now), else_=window),
        phone_window_count=case((fresh_window, 1), else_=func.coalesce(m.WebsiteAccount.phone_window_count, 0) + 1),
    ).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        await repo.s.rollback()
        current = await repo.s.get(m.WebsiteAccount, account_id, populate_existing=True)
        sent_at = current.phone_send_at if current else None
        if sent_at is not None and (sent_at if sent_at.tzinfo else sent_at.replace(tzinfo=timezone.utc)) > minute_ago:
            raise HTTPException(429, 'Повторіть запит через хвилину')
        raise HTTPException(429, 'Ліміт SMS на годину вичерпано')
    await repo.s.commit()  # limiter persists even if the gateway fails
    account = await repo.s.get(m.WebsiteAccount, account_id, populate_existing=True)
    code = phone_verification.issue_code(account, phone)
    await repo.s.commit()
    try:
        await phone_verification.send_sms(shop, phone, phone_verification.sms_text(shop.shop_name, code))
    except phone_verification.GatewayError:
        raise HTTPException(502, 'Не вдалося надіслати SMS. Спробуйте підтвердити номер через Telegram') from None
    return {'sent':True}


async def _link_by_phone(repo: Repository, account: m.WebsiteAccount, phone: str):
    # Only match phone stored on canonical Telegram profile, NOT arbitrary
    # delivery recipient numbers from historical orders. Exactly one account.
    rows = list((await repo.s.scalars(select(m.User).where(
        m.User.phone == phone, m.User.phone_verified_at.is_not(None),
        m.User.tg_id > 0).limit(2))).all())
    if len(rows) != 1:
        return False
    user = rows[0]
    owned = await repo.s.scalar(select(m.WebsiteAccount).where(
        m.WebsiteAccount.linked_telegram_user_id == user.id,
        m.WebsiteAccount.id != account.id))
    if owned:
        return False
    account.linked_telegram_user_id = user.id
    return True


@router.post('/profile/phone/check')
async def phone_check(data: PhoneCheckIn, request: Request, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    if not account.google_sub:
        raise HTTPException(401, 'Увійдіть через Google')
    if not _secure(request) and urlsplit(_website_origin(request)).hostname not in {'localhost','127.0.0.1'}:
        raise HTTPException(403, 'Підтвердження номера доступне лише через HTTPS')
    phone = _phone(data.phone)
    # Row lock: two parallel checks cannot both spend the same attempt.
    account = await repo.s.scalar(select(m.WebsiteAccount).where(m.WebsiteAccount.id == account.id)
                                  .with_for_update().execution_options(populate_existing=True))
    result = phone_verification.check_code(account, phone, data.code)
    if result != 'ok':
        await repo.s.commit()  # a wrong attempt is counted even though we refuse
        raise HTTPException(429 if result == 'attempts' else 422, {
            'attempts': 'Забагато спроб. Надішліть новий код',
            'expired': 'Код прострочений або вже використаний. Надішліть новий',
        }.get(result, 'Невірний код'))
    if account.linked_telegram_user_id:
        tg = await repo.s.get(m.User, account.linked_telegram_user_id)
        if tg and tg.phone and tg.phone != phone:
            raise HTTPException(409, 'Номер відрізняється від звʼязаного Telegram-профілю')
    account.verified_phone = phone
    linked = await _link_by_phone(repo, account, phone) if not account.linked_telegram_user_id else True
    await repo.s.commit()
    return {'phone_verified':True, 'telegram_linked': linked,
            'note': 'Історія Mini App підключена' if linked else 'Номер підтверджено. Для історії Mini App може знадобитися привʼязка Telegram.'}


@router.post('/profile/phone/telegram')
async def phone_via_telegram(request: Request, repo: Repository = Depends(get_repo)):
    """Link to the bot that confirms the number with the user's own contact."""
    _require_csrf(request)
    account = await _required_account(request, repo)
    if not account.google_sub:
        raise HTTPException(401, 'Увійдіть через Google для привʼязки номера')
    if not phone_verification.telegram_ready():
        raise HTTPException(503, 'Telegram-бот ще не підключено')
    # A new link replaces the previous one; issuing them in a burst is refused.
    expires = await repo.s.scalar(select(m.WebsitePhoneConfirmation.expires_at)
                                  .where(m.WebsitePhoneConfirmation.account_id == account.id))
    expires = expires if expires is None or expires.tzinfo else expires.replace(tzinfo=timezone.utc)
    if expires and (_now() - (expires - phone_verification.TELEGRAM_TTL)).total_seconds() < 5:
        raise HTTPException(429, 'Зачекайте кілька секунд')
    token, ttl = await phone_verification.create_telegram_request(repo.s, account)
    await repo.s.commit()
    from shop.links import chat_link
    return {'url': chat_link(phone_verification.TELEGRAM_PREFIX + token), 'expires_in_seconds': ttl}


class TelegramCodeIn(BaseModel):
    code: str = Field(min_length=18, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')


@router.post('/profile/link-code')
async def link_telegram_code(data: TelegramCodeIn, request: Request,
                             repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    if not account.google_sub:
        raise HTTPException(401, 'Увійдіть через Google')
    # Atomic single-use: two simultaneous requests cannot claim the same code.
    row = await repo.s.scalar(select(m.WebsiteTelegramLink).where(
        m.WebsiteTelegramLink.code_hash == _hash(data.code),
        m.WebsiteTelegramLink.expires_at > _now()).with_for_update())
    if not row:
        raise HTTPException(422, 'Код недійсний або вже використаний')
    tg = await repo.s.get(m.User, row.tg_user_id)
    if not tg or tg.tg_id <= 0:
        raise HTTPException(422, 'Telegram-профіль не знайдено')
    owner = await repo.s.scalar(select(m.WebsiteAccount).where(
        m.WebsiteAccount.linked_telegram_user_id == tg.id,
        m.WebsiteAccount.id != account.id))
    if owner:
        raise HTTPException(409, 'Цей Telegram уже привʼязаний до іншого профілю')
    if account.verified_phone and tg.phone and account.verified_phone != tg.phone:
        raise HTTPException(409, 'Номер Google-профілю відрізняється від номера Telegram')
    account.linked_telegram_user_id = tg.id
    await repo.s.delete(row)
    await repo.s.commit()
    return {'telegram_linked': True, 'note':'Історію покупок із Mini App підключено'}


class TelegramLinkIn(BaseModel):
    init_data: str = Field(min_length=20, max_length=8192)


@router.post('/profile/link-telegram')
async def link_telegram(data: TelegramLinkIn, request: Request, repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account = await _required_account(request, repo)
    if not account.google_sub:
        raise HTTPException(401, 'Увійдіть через Google')
    if not settings.bot_token:
        raise HTTPException(503, 'Telegram-бот ще не підключено')
    try:
        info = parse_init_data(data.init_data, settings.bot_token)
        tg_id = int((info.get('user') or {}).get('id') or 0)
    except (InitDataError, ValueError, TypeError):
        raise HTTPException(401, 'Недійсне Telegram-підтвердження') from None
    if not tg_id:
        raise HTTPException(401, 'Недійсне Telegram-підтвердження')
    tg = await repo.get_user_by_tg(tg_id)
    if tg is None:
        raise HTTPException(404, 'Покупок у цьому Telegram-профілі ще немає')
    conflict = await repo.s.scalar(select(m.WebsiteAccount).where(
        m.WebsiteAccount.linked_telegram_user_id == tg.id,
        m.WebsiteAccount.id != account.id))
    if conflict:
        raise HTTPException(409, 'Цей Telegram уже звʼязаний з іншим профілем')
    if account.verified_phone and tg.phone and account.verified_phone != tg.phone:
        raise HTTPException(409, 'Підтверджений номер відрізняється від номера Telegram')
    account.linked_telegram_user_id = tg.id
    await repo.s.commit()
    return {'telegram_linked': True}


@router.get('/delivery/config')
async def delivery_config(repo: Repository = Depends(get_repo)):
    shop = await get_shop_settings(repo)
    return {'courier_enabled': bool(shop.delivery_courier_enabled),
            'novaposhta_enabled': bool(shop.novaposhta_connected)}


@router.get('/delivery/cities')
async def delivery_cities(q: str = Query('', max_length=80), repo: Repository = Depends(get_repo)):
    shop = await get_shop_settings(repo)
    if not shop.novaposhta_api_key:
        return {'items': [], 'manual': True}
    try:
        result = await np.search_settlements(shop.novaposhta_api_key, q)
    except np.NovaPoshtaError:
        return {'items': [], 'manual': True}
    return {'items':[{'ref':x.ref,'settlement_ref':x.settlement_ref,'label':x.label,'name':x.name}
                     for x in result], 'manual':False}


@router.get('/delivery/warehouses')
async def delivery_warehouses(city_ref: str=Query('', max_length=64),
                              settlement_ref: str=Query('', max_length=64),
                              q: str=Query('', max_length=80),
                              repo: Repository=Depends(get_repo)):
    shop = await get_shop_settings(repo)
    if not shop.novaposhta_api_key:
        return {'items': [], 'manual': True}
    try:
        found = await np.warehouses(shop.novaposhta_api_key, city_ref, settlement_ref, q)
    except np.NovaPoshtaError:
        return {'items': [], 'manual': True}
    return {'items':[{'ref':x.ref,'label':x.label,'number':x.number} for x in found], 'manual':False}
