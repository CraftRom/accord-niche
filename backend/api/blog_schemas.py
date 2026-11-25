"""Explicit blog input/output projections. Raw HTML is never a rendering format."""
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

PostStatus = Literal['draft','published','archived']
CommentStatus = Literal['pending','approved','rejected','deleted']


class PostIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=3, max_length=200)
    slug: str = Field('', max_length=180)
    excerpt: str = Field('', max_length=500)
    body: str = Field('', max_length=60000)
    cover_url: str = Field('', max_length=512)
    author_name: str = Field('Редакція ACCORD NICHE', min_length=1, max_length=120)
    status: PostStatus = 'draft'
    comments_enabled: bool = True
    published_at: datetime | None = None
    # SEO: empty = built from the title and the excerpt.
    seo_title: str = Field('', max_length=120)
    seo_description: str = Field('', max_length=300)
    focus_keyword: str = Field('', max_length=80)
    cover_alt: str = Field('', max_length=200)
    noindex: bool = False

    @field_validator('title', 'slug', 'excerpt', 'body', 'cover_url', 'author_name', 'seo_title',
                     'seo_description', 'focus_keyword', 'cover_alt', mode='before')
    @classmethod
    def clean(cls, value):
        if not isinstance(value, str):
            raise ValueError('Потрібен текст')
        if any(ord(char)<32 and char not in '\n\t\r' for char in value):
            raise ValueError('Недопустимі керівні символи')
        return value.strip()

    @field_validator('published_at')
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError('Дата має містити часовий пояс')
        return value

    @field_validator('cover_url')
    @classmethod
    def image(cls, value):
        if not value:
            return ''
        if re.fullmatch(r'/media/[A-Za-z0-9_-]+\.(?:png|jpe?g|gif|webp)', value):
            return value
        try:
            parts = urlsplit(value)
            if parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password:
                return value
        except ValueError:
            pass
        raise ValueError('Обкладинка: завантажене зображення або HTTPS-адреса')


class PostUpdate(PostIn):
    version: int = Field(gt=0)


class PostCard(BaseModel):
    id: int
    slug: str
    title: str
    excerpt: str
    cover_url: str
    author_name: str
    published_at: datetime | None
    updated_at: datetime
    reading_minutes: int
    comment_count: int


class PublicPost(PostCard):
    body: str
    comments_enabled: bool
    cover_alt: str = ''


class AdminPost(PublicPost):
    status: PostStatus
    version: int
    seo_title: str = ''
    seo_description: str = ''
    focus_keyword: str = ''
    noindex: bool = False
    created_by: str
    updated_by: str
    created_at: datetime


class CommentIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    body: str = Field(min_length=2, max_length=2000)
    parent_id: int | None = Field(None, gt=0)
    client_key: str = Field(min_length=12, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('body', mode='before')
    @classmethod
    def clean(cls, value):
        if not isinstance(value, str):
            raise ValueError('Потрібен текст')
        if any(ord(char)<32 and char not in '\n\t\r' for char in value):
            raise ValueError('Недопустимі керівні символи')
        return value.strip()


class CommentEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    body: str = Field(min_length=2, max_length=2000)
    version: int = Field(gt=0)
    _clean = field_validator('body', mode='before')(CommentIn.clean.__func__)


class CommentDelete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(gt=0)


class Moderation(CommentDelete):
    status: Literal['approved','rejected']
    note: str = Field('', max_length=500)


class BulkModeration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[int] = Field(min_length=1, max_length=100)
    action: Literal['approve','reject','delete']
    note: str = Field('', max_length=500)


class BanIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_id: int = Field(gt=0)
    reason: str = Field('', max_length=500)
    # None — безстрокове блокування.
    days: int | None = Field(None, ge=1, le=3650)
    # none — лишити коментарі; hide — відхилити очікувані й схвалені; delete — видалити всі.
    comments: Literal['none','hide','delete'] = 'hide'


class BanOut(BaseModel):
    user_id: int
    author_name: str
    reason: str
    banned_by: str
    expires_at: datetime | None
    created_at: datetime
    comment_count: int = 0


class ModerationSettingsIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['manual','trusted'] = 'manual'
    trusted_after: int = Field(3, ge=1, le=100)
    stop_words: str = Field('', max_length=5000)
    stop_word_action: Literal['hold','reject'] = 'hold'
    hold_links: bool = True


class ModerationSettingsOut(ModerationSettingsIn):
    updated_by: str = ''
    updated_at: datetime | None = None


class PublicComment(BaseModel):
    id: int
    parent_id: int | None
    author_name: str
    is_staff: bool
    body: str
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0


class OwnComment(PublicComment):
    status: CommentStatus
    version: int


class AdminComment(OwnComment):
    post_id: int
    post_title: str
    post_slug: str = ''
    moderation_note: str
    moderated_by: str | None
    moderated_at: datetime | None = None
    author_user_id: int | None = None
    flags: str = ''
    author_banned: bool = False
    author_approved: int = 0
    author_rejected: int = 0


class PostPage(BaseModel):
    items: list[PostCard]
    total: int
    limit: int
    offset: int


class CommentPage(BaseModel):
    items: list[PublicComment]
    total: int
    limit: int
    offset: int
