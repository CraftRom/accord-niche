"""Blog comment moderation rules: bans, stop words, links and trusted authors.

The decision for a new or edited customer comment is made here, so the public
endpoint and the editor share one rule set:

1. a banned customer (any of their linked identities) cannot post or edit;
2. stop words either reject the comment at once or hold it with a flag;
3. links and contact details (phone, e-mail) always hold it for a moderator;
4. in "trusted" mode an author with N approved comments and no rejected ones
   is published immediately; otherwise every comment waits in the queue.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from shop import models as m

_LINK = re.compile(r"(?:https?://|www\.)\S+|\b[a-z0-9-]{2,}\.(?:com|net|org|ua|ru|io|me|info|shop|store|site|top|xyz|link|ly)\b",
                   re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s()-]*){10,13}(?!\d)")
DEFAULTS = dict(mode="manual", trusted_after=3, stop_words="", stop_word_action="hold", hold_links=True,
                updated_by="", updated_at=None)


def now():
    return datetime.now(timezone.utc)


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


async def load_settings(repo) -> dict:
    row = await repo.s.get(m.BlogModerationSettings, 1)
    if row is None:
        return dict(DEFAULTS)
    return {key: getattr(row, key) for key in DEFAULTS}


async def save_settings(repo, values: dict, actor: str) -> dict:
    row = await repo.s.get(m.BlogModerationSettings, 1)
    if row is None:
        row = m.BlogModerationSettings(id=1)
        repo.s.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_by, row.updated_at = actor, now()
    await repo.s.commit()
    return await load_settings(repo)


def stop_words(raw: str) -> list[str]:
    words = re.split(r"[\n,;]+", raw or "")
    return sorted({w.strip().casefold() for w in words if len(w.strip()) >= 2})


def scan(body: str, rules: dict) -> list[str]:
    """Flags for a comment text: stop_word, link, contact."""
    text = (body or "").casefold()
    flags = []
    for word in stop_words(rules.get("stop_words", "")):
        # Whole words (or phrases); 'ass' never matches 'classic'.
        if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text):
            flags.append("stop_word")
            break
    if rules.get("hold_links", True) and _LINK.search(body or ""):
        flags.append("link")
    if _EMAIL.search(body or "") or _PHONE.search(body or ""):
        flags.append("contact")
    return flags


async def active_ban(repo, identity_ids) -> m.BlogCommentBan | None:
    ids = [i for i in identity_ids if i]
    if not ids:
        return None
    return await repo.s.scalar(select(m.BlogCommentBan).where(
        m.BlogCommentBan.user_id.in_(ids),
        or_(m.BlogCommentBan.expires_at.is_(None), m.BlogCommentBan.expires_at > now())).limit(1))


def ban_message(ban) -> str:
    until = _aware(ban.expires_at)
    when = f" до {until.astimezone().strftime('%d.%m.%Y')}" if until else ""
    return f"Редакція обмежила вам можливість коментувати{when}."


async def author_history(repo, identity_ids) -> tuple[int, int]:
    rows = dict((await repo.s.execute(select(m.BlogComment.status, func.count()).where(
        m.BlogComment.author_user_id.in_(list(identity_ids)), m.BlogComment.is_staff.is_(False))
        .group_by(m.BlogComment.status))).all())
    return rows.get("approved", 0), rows.get("rejected", 0)


async def decide(repo, body: str, identity_ids) -> tuple[str, str, str]:
    """(status, flags, note) for a customer comment."""
    rules = await load_settings(repo)
    flags = scan(body, rules)
    if "stop_word" in flags and rules["stop_word_action"] == "reject":
        return "rejected", ",".join(flags), "Автоматично: стоп-слово"
    if flags:
        return "pending", ",".join(flags), ""
    if rules["mode"] == "trusted":
        approved, rejected = await author_history(repo, identity_ids)
        if approved >= rules["trusted_after"] and rejected == 0:
            return "approved", "", "Автоматично: довірений автор"
    return "pending", "", ""
