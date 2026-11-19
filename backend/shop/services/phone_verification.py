"""Free phone verification for website accounts, without Twilio.

Two ways, both free of per-message fees:

* **Telegram bot.** The profile opens ``t.me/<bot>?start=vp_<token>``; the bot
  asks for the user's own contact. Telegram only sends a contact with
  ``user_id`` equal to the sender for the sender's own number, so the number
  is proven by Telegram itself — no SMS at all.
* **SMS through the shop's own Android phone** (open-source *SMS Gateway for
  Android*). The shop generates and checks the code itself; the gateway only
  delivers the text from the phone's SIM. Only an HMAC of the code is stored,
  bound to the account and the number, with an expiry and an attempt limit.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from shop import models as m
from shop.config import settings

CODE_TTL = timedelta(minutes=10)
CODE_ATTEMPTS = 5
TELEGRAM_TTL = timedelta(minutes=10)
TELEGRAM_PREFIX = "vp_"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,48}$")


class GatewayError(Exception):
    """The SMS gateway did not accept the message."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


def normalize_ua_phone(raw: str) -> str | None:
    """+380XXXXXXXXX or None: the same rules as the website and the bot."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("380") and len(digits) == 12:
        body = digits[3:]
    elif digits.startswith("80") and len(digits) == 11:
        body = digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        body = digits[1:]
    else:
        return None
    return "+380" + body if body[:1] in set("3456789") else None


# ---------------------------------------------------------------- SMS codes

def _code_digest(account_id: int, phone: str, code: str) -> str:
    key = ("accord-phone-code:" + settings.jwt_secret).encode()
    return hmac.new(key, f"{account_id}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def issue_code(account: m.WebsiteAccount, phone: str) -> str:
    """New 6-digit code for ``phone``; replaces any earlier code."""
    code = f"{secrets.randbelow(10 ** 6):06d}"
    account.phone_code_hash = _code_digest(account.id, phone, code)
    account.phone_code_phone = phone
    account.phone_code_expires_at = _now() + CODE_TTL
    account.phone_code_attempts = 0
    return code


def check_code(account: m.WebsiteAccount, phone: str, code: str) -> str:
    """'ok', 'expired', 'attempts' or 'wrong'. Wrong attempts are counted."""
    expires = _aware(account.phone_code_expires_at)
    if not account.phone_code_hash or account.phone_code_phone != phone or not expires or expires <= _now():
        return "expired"
    if (account.phone_code_attempts or 0) >= CODE_ATTEMPTS:
        return "attempts"
    if not hmac.compare_digest(account.phone_code_hash, _code_digest(account.id, phone, code)):
        account.phone_code_attempts = (account.phone_code_attempts or 0) + 1
        return "wrong"
    clear_code(account)
    return "ok"


def clear_code(account: m.WebsiteAccount) -> None:
    account.phone_code_hash = None
    account.phone_code_phone = None
    account.phone_code_expires_at = None
    account.phone_code_attempts = 0


def sms_text(shop_name: str, code: str) -> str:
    return f"{shop_name}: код підтвердження {code}. Дійсний 10 хвилин. Нікому його не повідомляйте."


async def send_sms(shop, phone: str, text: str) -> None:
    """Deliver ``text`` through SMS Gateway for Android (cloud or own server).

    The address is an https URL set by the system administrator; no redirects
    are followed and the credentials never reach logs or responses.
    """
    url, login, password = (shop.site("sms_gateway_url"), shop.site("sms_gateway_login"),
                            shop.site("sms_gateway_password"))
    if not (url and login and password):
        raise GatewayError("not_configured")
    if not url.startswith("https://"):
        raise GatewayError("insecure_url")
    payload = {"textMessage": {"text": text}, "phoneNumbers": [phone]}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(url, json=payload, auth=(login, password))
    except httpx.HTTPError:
        raise GatewayError("unreachable") from None
    if response.status_code in (401, 403):
        raise GatewayError("auth")
    if not 200 <= response.status_code < 300:
        raise GatewayError(f"http_{response.status_code}")


GATEWAY_PROBLEMS = {
    "not_configured": "Задайте адресу, логін і пароль SMS-шлюзу",
    "insecure_url": "Адреса SMS-шлюзу має починатися з https://",
    "unreachable": "SMS-шлюз не відповідає: перевірте, що телефон у мережі й застосунок запущено",
    "auth": "SMS-шлюз відхилив логін або пароль",
}


def gateway_problem(error: GatewayError) -> str:
    code = str(error)
    if code.startswith("http_"):
        return f"SMS-шлюз повернув помилку {code[5:]}"
    return GATEWAY_PROBLEMS.get(code, "SMS-шлюз недоступний")


# --------------------------------------------------- Telegram confirmation

def telegram_ready() -> bool:
    from shop.links import bot_name
    name = bot_name()
    return bool(settings.bot_token and name and name != "your_shop_bot")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_telegram_request(session, account: m.WebsiteAccount) -> tuple[str, int]:
    """One live confirmation per account: a new request replaces the old one."""
    token = secrets.token_urlsafe(24)  # 192-bit, 32 characters
    row = await session.scalar(select(m.WebsitePhoneConfirmation)
                               .where(m.WebsitePhoneConfirmation.account_id == account.id))
    if row is None:
        row = m.WebsitePhoneConfirmation(account_id=account.id)
        session.add(row)
    row.token_hash = _token_hash(token)
    row.expires_at = _now() + TELEGRAM_TTL
    return token, int(TELEGRAM_TTL.total_seconds())


def token_from_start(payload: str | None) -> str | None:
    if not payload or not payload.startswith(TELEGRAM_PREFIX):
        return None
    token = payload[len(TELEGRAM_PREFIX):]
    return token if _TOKEN.fullmatch(token) else None


async def pending_request(session, token: str) -> m.WebsitePhoneConfirmation | None:
    return await session.scalar(select(m.WebsitePhoneConfirmation).where(
        m.WebsitePhoneConfirmation.token_hash == _token_hash(token),
        m.WebsitePhoneConfirmation.expires_at > _now()))


async def confirm_with_telegram(session, token: str, tg_user_id: int, phone: str) -> str:
    """Confirm the website account's phone with the sender's own contact.

    Returns 'ok', 'ok_linked', 'expired' or 'other_telegram'. Single use:
    the request row is deleted in the same transaction.
    """
    row = await session.scalar(select(m.WebsitePhoneConfirmation).where(
        m.WebsitePhoneConfirmation.token_hash == _token_hash(token),
        m.WebsitePhoneConfirmation.expires_at > _now()).with_for_update())
    if row is None:
        return "expired"
    account = await session.get(m.WebsiteAccount, row.account_id)
    if account is None:
        await session.delete(row)
        await session.commit()
        return "expired"
    if account.linked_telegram_user_id and account.linked_telegram_user_id != tg_user_id:
        return "other_telegram"
    linked = False
    if not account.linked_telegram_user_id:
        owner = await session.scalar(select(m.WebsiteAccount.id).where(
            m.WebsiteAccount.linked_telegram_user_id == tg_user_id,
            m.WebsiteAccount.id != account.id))
        if owner is None:
            account.linked_telegram_user_id = tg_user_id
            linked = True
    account.verified_phone = phone
    clear_code(account)
    await session.delete(row)
    await session.commit()
    return "ok_linked" if linked else "ok"
