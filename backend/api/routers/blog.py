"""Blog CMS, public reading and authenticated moderated comments.

Uses existing staff authorization, browser sessions, CSRF and customer identities.
No new authentication, network or financial-statistics subsystem is introduced.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import math
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, select, update, func, or_, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from api.auth import Principal, require_admin
from api.blog_schemas import (PostIn, PostUpdate, PostCard, PublicPost, AdminPost, PostPage,
    CommentIn, CommentEdit, CommentDelete, Moderation, PublicComment, OwnComment, AdminComment, CommentPage,
    BulkModeration, BanIn, BanOut, ModerationSettingsIn, ModerationSettingsOut)
from api.routers.website_shop import _account, _require_csrf
from shop import models as m, security_log
from shop.repo.base import Repository
from shop.repo.factory import get_repo
from shop.services import comment_moderation as rules
from shop.services.website_identity import _owned_user_ids

admin = APIRouter(dependencies=[Depends(require_admin)])
public = APIRouter()
web = APIRouter()


def now():
    return datetime.now(timezone.utc)


def visible_post():
    return (m.BlogPost.status == 'published', m.BlogPost.published_at <= now())


def visible_comment():
    parent = aliased(m.BlogComment)
    parent_ok = exists(select(parent.id).where(parent.id == m.BlogComment.parent_id,
        parent.post_id == m.BlogComment.post_id, parent.status == 'approved')).correlate(m.BlogComment)
    return (m.BlogComment.status == 'approved', or_(m.BlogComment.parent_id.is_(None), parent_ok))


async def get_post(repo, post_id=None, slug=None, published=False):
    query = select(m.BlogPost)
    if slug is not None:
        query = query.join(m.BlogSlug, m.BlogSlug.post_id == m.BlogPost.id).where(m.BlogSlug.slug == slug)
    else:
        query = query.where(m.BlogPost.id == post_id)
    if published:
        query = query.where(*visible_post())
    post = await repo.s.scalar(query)
    if post is None:
        raise HTTPException(404, 'Публікацію не знайдено')
    return post


async def post_out(repo, post, model=PublicPost, count=None):
    if count is None:
        count = await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(
            m.BlogComment.post_id == post.id, *visible_comment()))
    values = {column.name:getattr(post, column.name) for column in m.BlogPost.__table__.columns}
    values = {key:(value.replace(tzinfo=timezone.utc) if isinstance(value,datetime) and value.tzinfo is None else value) for key,value in values.items()}
    values.update(comment_count=count or 0, reading_minutes=max(1, math.ceil(len(post.body.split()) / 200)))
    return model(**values)


def slug_for(title, supplied):
    slug = (supplied or title).strip().casefold()
    slug = re.sub(r'[^a-z0-9а-яіїєґ]+', '-', slug).strip('-')
    if not slug or len(slug)>180:
        raise HTTPException(422, 'Задайте коротку адресу статті літерами й цифрами')
    return slug


def post_values(data):
    values = data.model_dump(exclude={'version'})
    values['slug'] = slug_for(data.title, data.slug)
    values['search_text'] = (data.title + ' ' + data.excerpt).casefold()
    if data.status == 'published':
        if len(data.body.strip()) < 20:
            raise HTTPException(422, 'Перед публікацією додайте текст статті')
        values['published_at'] = data.published_at or now()
    return values


async def commit(repo):
    try:
        await repo.s.commit()
    except IntegrityError:
        await repo.s.rollback()
        raise HTTPException(409, 'Адреса або ключ запиту вже використані; оновіть дані') from None


def published(post):
    """Sitemaps rebuild now; search engines hear about a live, indexable article."""
    from shop.services import indexnow, seo
    seo.invalidate()
    at = post.published_at
    live = post.status == 'published' and at is not None and (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) <= now()
    if live and not post.noindex:
        indexnow.notify(seo.post_url(post), seo.ORIGIN + '/blog')


async def reserve_slug(repo, slug, post_id):
    existing = await repo.s.get(m.BlogSlug, slug)
    if existing and existing.post_id != post_id:
        raise HTTPException(409, 'Ця адреса вже належить іншій статті')
    if not existing:
        repo.s.add(m.BlogSlug(slug=slug, post_id=post_id))


@public.get('', response_model=PostPage)
async def posts(response: Response, q: str = Query('', max_length=120),
                limit: int = Query(12, ge=1, le=30), offset: int = Query(0, ge=0),
                repo: Repository = Depends(get_repo)):
    filters = [*visible_post()]
    if q.strip():
        term = '%' + q.strip().casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        filters.append(m.BlogPost.search_text.like(term, escape='\\'))
    total = await repo.s.scalar(select(func.count()).select_from(m.BlogPost).where(*filters))
    rows = (await repo.s.scalars(select(m.BlogPost).where(*filters).order_by(
        m.BlogPost.published_at.desc(), m.BlogPost.id.desc()).limit(limit).offset(offset))).all()
    counts = dict((await repo.s.execute(select(m.BlogComment.post_id, func.count()).where(
        m.BlogComment.post_id.in_([p.id for p in rows]), *visible_comment()).group_by(m.BlogComment.post_id))).all()) if rows else {}
    response.headers['Cache-Control'] = 'no-store'
    return PostPage(items=[await post_out(repo,p,PostCard,counts.get(p.id,0)) for p in rows],
                    total=total or 0, limit=limit, offset=offset)


@public.get('/{slug}', response_model=PublicPost)
async def read_post(slug: str, response: Response, repo: Repository = Depends(get_repo)):
    response.headers['Cache-Control'] = 'no-store'
    return await post_out(repo, await get_post(repo,slug=slug,published=True))


@public.get('/{slug}/comments', response_model=CommentPage)
async def comments(slug: str, response: Response, parent_id: int | None = Query(None,gt=0),
                   limit: int = Query(10,ge=1,le=30), offset: int = Query(0,ge=0),
                   repo: Repository = Depends(get_repo)):
    post = await get_post(repo,slug=slug,published=True)
    if parent_id:
        parent = await repo.s.scalar(select(m.BlogComment).where(m.BlogComment.id == parent_id,
            m.BlogComment.post_id == post.id, m.BlogComment.status == 'approved', m.BlogComment.parent_id.is_(None)))
        if not parent:
            raise HTTPException(404, 'Коментар не знайдено')
    filters = [m.BlogComment.post_id == post.id, m.BlogComment.parent_id == parent_id, *visible_comment()]
    total = await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(*filters))
    rows = (await repo.s.scalars(select(m.BlogComment).where(*filters).order_by(
        m.BlogComment.id.asc()).offset(offset).limit(limit))).all()
    counts = dict((await repo.s.execute(select(m.BlogComment.parent_id,func.count()).where(
        m.BlogComment.parent_id.in_([r.id for r in rows]), m.BlogComment.status == 'approved')
        .group_by(m.BlogComment.parent_id))).all()) if rows else {}
    response.headers['Cache-Control'] = 'no-store'
    return CommentPage(items=[comment_out(row,reply_count=counts.get(row.id,0)) for row in rows],
                       total=total or 0,limit=limit,offset=offset)


@admin.get('/posts')
async def admin_posts(q: str = Query('',max_length=120), status: str = Query('',pattern='^(|draft|published|archived)$'),
                      limit: int = Query(20,ge=1,le=50), offset: int = Query(0,ge=0),
                      repo: Repository = Depends(get_repo)):
    filters = []
    if status:
        filters.append(m.BlogPost.status == status)
    if q.strip():
        term = '%' + q.strip().casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        filters.append(m.BlogPost.search_text.like(term,escape='\\'))
    rows = (await repo.s.scalars(select(m.BlogPost).where(*filters).order_by(
        m.BlogPost.updated_at.desc(),m.BlogPost.id.desc()).offset(offset).limit(limit))).all()
    total = await repo.s.scalar(select(func.count()).select_from(m.BlogPost).where(*filters))
    pending = await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(m.BlogComment.status == 'pending'))
    # The list deliberately omits body; the editor fetches it only when opened.
    return {'items':[dict((await post_out(repo,p,PostCard)).model_dump(),status=p.status,version=p.version) for p in rows],
            'total':total or 0,'pending_comments':pending or 0}


@admin.get('/posts/{post_id}',response_model=AdminPost)
async def admin_post(post_id: int,repo: Repository = Depends(get_repo)):
    return await post_out(repo,await get_post(repo,post_id),AdminPost)


@admin.post('/posts',response_model=AdminPost,status_code=201)
async def create_post(data: PostIn, who: Principal = Depends(require_admin), repo: Repository = Depends(get_repo)):
    post = m.BlogPost(**post_values(data),created_by=who.login,updated_by=who.login)
    repo.s.add(post)
    try:
        await repo.s.flush()
        await reserve_slug(repo,post.slug,post.id)
        await commit(repo)
    except IntegrityError:
        await repo.s.rollback()
        raise HTTPException(409,'Ця адреса вже використана') from None
    except HTTPException:
        await repo.s.rollback()
        raise
    security_log.record('blog.post.created',actor=who.login,role=who.role.value,reason=str(post.id))
    published(post)
    return await post_out(repo,post,AdminPost)


@admin.put('/posts/{post_id}',response_model=AdminPost)
async def update_post(post_id: int,data: PostUpdate,who: Principal = Depends(require_admin),
                      repo: Repository = Depends(get_repo)):
    await get_post(repo,post_id)
    values=post_values(data)
    try:
        result = await repo.s.execute(update(m.BlogPost).where(m.BlogPost.id == post_id,
            m.BlogPost.version == data.version).values(**values,version=data.version+1,updated_at=now(),updated_by=who.login)
            .returning(m.BlogPost))
        post = result.scalar_one_or_none()
        if post is None:
            raise HTTPException(409,'Статтю вже змінено. Збережіть свій текст і завантажте поточну версію.')
        await reserve_slug(repo,post.slug,post.id)
        await commit(repo)
    except IntegrityError:
        await repo.s.rollback()
        raise HTTPException(409,'Ця адреса вже використана') from None
    except HTTPException:
        await repo.s.rollback()
        raise
    security_log.record('blog.post.changed',actor=who.login,role=who.role.value,reason=str(post.id))
    published(post)
    return await post_out(repo,post,AdminPost)


def comment_out(row,model=PublicComment,**extra):
    values={c.name:getattr(row,c.name) for c in m.BlogComment.__table__.columns}
    values={key:(value.replace(tzinfo=timezone.utc) if isinstance(value,datetime) and value.tzinfo is None else value) for key,value in values.items()}
    return model(**{**values,**extra})


async def member(request,repo):
    account=await _account(request,repo)
    if account is None or not (account.google_sub or account.verified_phone or account.linked_telegram_user_id):
        raise HTTPException(401,'Коментарі доступні після входу в особистий кабінет')
    return account


async def writable_post(repo,post_id):
    post=await repo.s.scalar(select(m.BlogPost).where(m.BlogPost.id == post_id,*visible_post()).with_for_update())
    if post is None:
        raise HTTPException(404,'Публікацію не знайдено')
    if not post.comments_enabled:
        raise HTTPException(409,'Коментарі до цієї статті закрито')
    return post


@web.get('/posts/{post_id}/mine',response_model=list[OwnComment])
async def own_comments(post_id: int,request: Request,response: Response,repo: Repository = Depends(get_repo)):
    await get_post(repo,post_id,published=True)
    account=await member(request,repo)
    owned=await _owned_user_ids(repo,account)
    rows=(await repo.s.scalars(select(m.BlogComment).where(m.BlogComment.post_id == post_id,
        m.BlogComment.author_user_id.in_(owned),m.BlogComment.status != 'deleted')
        .order_by(m.BlogComment.id.desc()).limit(100))).all()
    response.headers['Cache-Control']='no-store'
    return [comment_out(r,OwnComment) for r in rows]


async def insert_comment(repo,post_id,data,*,user_id=None,identity_ids=None,name,staff=False,actor=''):
    identities=identity_ids or [user_id]
    def retry_key(identity):
        return hashlib.sha256(identity.encode()+b':'+data.client_key.encode()).hexdigest()
    key=retry_key('staff:'+actor if staff else 'user:'+str(user_id))
    keys=[key] if staff else [retry_key('user:'+str(identity)) for identity in identities]
    previous=await repo.s.scalar(select(m.BlogComment).where(m.BlogComment.post_id == post_id,m.BlogComment.client_key.in_(keys)))
    if previous:
        if previous.body != data.body or previous.parent_id != data.parent_id:
            raise HTTPException(409,'Ключ цього запиту вже використано для іншого коментаря')
        return previous
    if data.parent_id:
        parent=await repo.s.scalar(select(m.BlogComment).where(m.BlogComment.id == data.parent_id,
            m.BlogComment.post_id == post_id,m.BlogComment.parent_id.is_(None),m.BlogComment.status == 'approved'))
        if not parent:
            raise HTTPException(409,'Відповідь доступна тільки до схваленого коментаря цієї статті')
    status,flags,note='approved' if staff else 'pending','',''
    if not staff:
        ban=await rules.active_ban(repo,identities)
        if ban:
            raise HTTPException(403,rules.ban_message(ban))
        status,flags,note=await rules.decide(repo,data.body,identities)
        latest=await repo.s.scalar(select(func.max(m.BlogComment.created_at)).where(m.BlogComment.author_user_id.in_(identities)))
        if latest:
            aware=latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
            if now()-aware < timedelta(seconds=20):
                raise HTTPException(429,'Між коментарями має минути щонайменше 20 секунд',headers={'Retry-After':'20'})
        count=await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(
            m.BlogComment.author_user_id.in_(identities),m.BlogComment.created_at > now()-timedelta(hours=1)))
        if count >= 10:
            raise HTTPException(429,'Досягнуто ліміт коментарів за годину',headers={'Retry-After':'3600'})
    row=m.BlogComment(post_id=post_id,parent_id=data.parent_id,author_user_id=user_id,
        author_name=' '.join(name.split())[:120] or 'Покупець',body=data.body,is_staff=staff,
        status=status,client_key=key,flags=flags,moderation_note=note,
        moderated_by=actor if staff else ('auto' if status!='pending' else None),
        moderated_at=now() if staff or status!='pending' else None)
    repo.s.add(row)
    await commit(repo)
    return row


@web.post('/posts/{post_id}/comments',response_model=OwnComment)
async def create_comment(post_id: int,data: CommentIn,request: Request,repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    account=await member(request,repo)
    # Serialize rate-limit checks with checkout/profile operations on this user.
    await repo.s.scalar(select(m.User.id).where(m.User.id == account.user_id).with_for_update())
    await writable_post(repo,post_id)
    row=await insert_comment(repo,post_id,data,user_id=account.user_id,identity_ids=await _owned_user_ids(repo,account),name=account.display_name or 'Покупець')
    return comment_out(row,OwnComment)


async def owned_comment(repo,request,comment_id):
    account=await member(request,repo)
    owned=await _owned_user_ids(repo,account)
    row=await repo.s.scalar(select(m.BlogComment).where(m.BlogComment.id == comment_id,
        m.BlogComment.author_user_id.in_(owned),m.BlogComment.status != 'deleted',m.BlogComment.is_staff.is_(False)))
    if row is None:
        raise HTTPException(404,'Коментар не знайдено')
    return row


@web.put('/comments/{comment_id}',response_model=OwnComment)
async def edit_comment(comment_id: int,data: CommentEdit,request: Request,repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    row=await owned_comment(repo,request,comment_id)
    await writable_post(repo,row.post_id)
    identities=await _owned_user_ids(repo,await member(request,repo))
    ban=await rules.active_ban(repo,identities)
    if ban:
        raise HTTPException(403,rules.ban_message(ban))
    status,flags,note=await rules.decide(repo,data.body,identities)
    changed=await repo.s.execute(update(m.BlogComment).where(m.BlogComment.id == row.id,
        m.BlogComment.version == data.version).values(body=data.body,status=status,version=data.version+1,flags=flags,
        updated_at=now(),moderated_by='auto' if status!='pending' else None,
        moderated_at=now() if status!='pending' else None,moderation_note=note).returning(m.BlogComment))
    result=changed.scalar_one_or_none()
    if result is None:
        await repo.s.rollback()
        raise HTTPException(409,'Коментар вже змінено; оновіть сторінку')
    await commit(repo)
    return comment_out(result,OwnComment)


@web.delete('/comments/{comment_id}')
async def delete_comment(comment_id: int,data: CommentDelete,request: Request,repo: Repository = Depends(get_repo)):
    _require_csrf(request)
    row=await owned_comment(repo,request,comment_id)
    changed=await repo.s.execute(update(m.BlogComment).where(m.BlogComment.id == row.id,
        m.BlogComment.version == data.version).values(body='',status='deleted',version=data.version+1,updated_at=now()))
    if changed.rowcount != 1:
        await repo.s.rollback()
        raise HTTPException(409,'Коментар вже змінено; оновіть сторінку')
    await commit(repo)
    return {'deleted':True}


def _like(value):
    return '%' + value.strip().casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'


async def admin_comments(repo,rows):
    """AdminComment rows with the author's history and ban state."""
    authors={r.author_user_id for r,_,_ in rows if r.author_user_id}
    banned=set((await repo.s.scalars(select(m.BlogCommentBan.user_id).where(m.BlogCommentBan.user_id.in_(authors),
        or_(m.BlogCommentBan.expires_at.is_(None),m.BlogCommentBan.expires_at > now())))).all()) if authors else set()
    history={}
    if authors:
        for author,status,count in (await repo.s.execute(select(m.BlogComment.author_user_id,m.BlogComment.status,func.count())
                .where(m.BlogComment.author_user_id.in_(authors)).group_by(m.BlogComment.author_user_id,m.BlogComment.status))).all():
            history.setdefault(author,{})[status]=count
    return [comment_out(r,AdminComment,post_title=title,post_slug=slug,author_banned=r.author_user_id in banned,
                        author_approved=history.get(r.author_user_id,{}).get('approved',0),
                        author_rejected=history.get(r.author_user_id,{}).get('rejected',0)) for r,title,slug in rows]


@admin.get('/comments')
async def moderation_queue(status: str = Query('pending',pattern='^(|all|pending|approved|rejected|deleted)$'),
                           post_id: int | None = Query(None,gt=0),author_user_id: int | None = Query(None,gt=0),
                           q: str = Query('',max_length=120),flagged: bool = False,
                           limit: int = Query(20,ge=1,le=50),
                           offset: int = Query(0,ge=0),repo: Repository = Depends(get_repo)):
    filters=[]
    if post_id: filters.append(m.BlogComment.post_id == post_id)
    if author_user_id: filters.append(m.BlogComment.author_user_id == author_user_id)
    if flagged: filters.append(m.BlogComment.flags != '')
    if q.strip():
        term=_like(q)
        filters.append(or_(func.lower(m.BlogComment.body).like(term,escape='\\'),
                           func.lower(m.BlogComment.author_name).like(term,escape='\\')))
    counts=dict((await repo.s.execute(select(m.BlogComment.status,func.count()).where(*filters)
        .group_by(m.BlogComment.status))).all())
    if status and status != 'all': filters.append(m.BlogComment.status == status)
    rows=(await repo.s.execute(select(m.BlogComment,m.BlogPost.title,m.BlogPost.slug).join(m.BlogPost)
        .where(*filters).order_by(m.BlogComment.created_at.desc(),m.BlogComment.id.desc())
        .offset(offset).limit(limit))).all()
    total=await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(*filters))
    return {'items':await admin_comments(repo,rows),'total':total or 0,
            'counts':{key:counts.get(key,0) for key in ('pending','approved','rejected','deleted')}}


@admin.post('/comments/{comment_id}/moderate',response_model=AdminComment)
async def moderate(comment_id: int,data: Moderation,who: Principal = Depends(require_admin),
                   repo: Repository = Depends(get_repo)):
    row=await repo.s.get(m.BlogComment,comment_id)
    if row is None: raise HTTPException(404,'Коментар не знайдено')
    if row.status == 'deleted': raise HTTPException(409,'Автор видалив цей коментар')
    result=await repo.s.execute(update(m.BlogComment).where(m.BlogComment.id == comment_id,
        m.BlogComment.version == data.version,m.BlogComment.status != 'deleted')
        .values(status=data.status,version=data.version+1,moderated_by=who.login,moderated_at=now(),
                moderation_note=data.note,updated_at=now()).returning(m.BlogComment))
    changed=result.scalar_one_or_none()
    if changed is None:
        await repo.s.rollback()
        raise HTTPException(409,'Коментар вже змінено; оновіть чергу')
    await commit(repo)
    security_log.record('blog.comment.moderated',actor=who.login,role=who.role.value,reason=str(comment_id)+':'+data.status)
    post=await get_post(repo,row.post_id)
    return (await admin_comments(repo,[(changed,post.title,post.slug)]))[0]


async def remove_comments(repo,ids):
    """Permanent removal by the editors; replies go with their comment."""
    ids=list(ids)
    if not ids:
        return 0
    replies=(await repo.s.scalars(select(m.BlogComment.id).where(m.BlogComment.parent_id.in_(ids)))).all()
    gone=set(ids)|set(replies)
    nested=await repo.s.execute(delete(m.BlogComment).where(m.BlogComment.parent_id.in_(list(gone))))
    result=await repo.s.execute(delete(m.BlogComment).where(m.BlogComment.id.in_(list(gone))))
    return (nested.rowcount or 0)+(result.rowcount or 0)


@admin.delete('/comments/{comment_id}')
async def delete_comment_admin(comment_id: int,who: Principal = Depends(require_admin),repo: Repository = Depends(get_repo)):
    if await repo.s.get(m.BlogComment,comment_id) is None:
        raise HTTPException(404,'Коментар не знайдено')
    removed=await remove_comments(repo,[comment_id])
    await commit(repo)
    security_log.record('blog.comment.deleted',actor=who.login,role=who.role.value,reason=str(comment_id))
    return {'deleted':removed}


@admin.post('/comments/bulk')
async def bulk_moderation(data: BulkModeration,who: Principal = Depends(require_admin),repo: Repository = Depends(get_repo)):
    ids=sorted(set(data.ids))
    if data.action == 'delete':
        changed=await remove_comments(repo,ids)
    else:
        status='approved' if data.action == 'approve' else 'rejected'
        result=await repo.s.execute(update(m.BlogComment).where(m.BlogComment.id.in_(ids),m.BlogComment.status != 'deleted',
            m.BlogComment.status != status).values(status=status,version=m.BlogComment.version+1,moderated_by=who.login,
            moderated_at=now(),updated_at=now(),moderation_note=data.note))
        changed=result.rowcount or 0
    await commit(repo)
    security_log.record('blog.comment.bulk',actor=who.login,role=who.role.value,reason=data.action+':'+str(len(ids)))
    return {'changed':changed}


async def ban_out(repo,row):
    count=await repo.s.scalar(select(func.count()).select_from(m.BlogComment).where(m.BlogComment.author_user_id == row.user_id))
    values={c.name:getattr(row,c.name) for c in m.BlogCommentBan.__table__.columns}
    values={k:(v.replace(tzinfo=timezone.utc) if isinstance(v,datetime) and v.tzinfo is None else v) for k,v in values.items()}
    return BanOut(**values,comment_count=count or 0)


@admin.get('/bans',response_model=list[BanOut])
async def list_bans(repo: Repository = Depends(get_repo)):
    rows=(await repo.s.scalars(select(m.BlogCommentBan).order_by(m.BlogCommentBan.created_at.desc(),m.BlogCommentBan.id.desc()).limit(200))).all()
    return [await ban_out(repo,row) for row in rows]


@admin.post('/bans',response_model=BanOut,status_code=201)
async def ban_author(data: BanIn,who: Principal = Depends(require_admin),repo: Repository = Depends(get_repo)):
    if await repo.s.get(m.User,data.user_id) is None:
        raise HTTPException(404,'Покупця не знайдено')
    name=await repo.s.scalar(select(m.BlogComment.author_name).where(m.BlogComment.author_user_id == data.user_id)
        .order_by(m.BlogComment.id.desc()).limit(1)) or ''
    row=await repo.s.scalar(select(m.BlogCommentBan).where(m.BlogCommentBan.user_id == data.user_id))
    if row is None:
        row=m.BlogCommentBan(user_id=data.user_id)
        repo.s.add(row)
    row.author_name,row.reason,row.banned_by=name,data.reason,who.login
    row.expires_at=now()+timedelta(days=data.days) if data.days else None
    row.created_at=now()
    if data.comments == 'hide':
        await repo.s.execute(update(m.BlogComment).where(m.BlogComment.author_user_id == data.user_id,
            m.BlogComment.status.in_(('pending','approved'))).values(status='rejected',version=m.BlogComment.version+1,
            moderated_by=who.login,moderated_at=now(),updated_at=now(),moderation_note='Автор заблокований'))
    elif data.comments == 'delete':
        ids=(await repo.s.scalars(select(m.BlogComment.id).where(m.BlogComment.author_user_id == data.user_id))).all()
        await remove_comments(repo,ids)
    await commit(repo)
    security_log.record('blog.author.banned',actor=who.login,role=who.role.value,reason=str(data.user_id)+':'+data.comments)
    return await ban_out(repo,row)


@admin.delete('/bans/{user_id}')
async def unban_author(user_id: int,who: Principal = Depends(require_admin),repo: Repository = Depends(get_repo)):
    result=await repo.s.execute(delete(m.BlogCommentBan).where(m.BlogCommentBan.user_id == user_id))
    if not result.rowcount:
        raise HTTPException(404,'Блокування не знайдено')
    await commit(repo)
    security_log.record('blog.author.unbanned',actor=who.login,role=who.role.value,reason=str(user_id))
    return {'unbanned':True}


@admin.get('/moderation-settings',response_model=ModerationSettingsOut)
async def get_moderation_settings(repo: Repository = Depends(get_repo)):
    return ModerationSettingsOut(**await rules.load_settings(repo))


@admin.put('/moderation-settings',response_model=ModerationSettingsOut)
async def put_moderation_settings(data: ModerationSettingsIn,who: Principal = Depends(require_admin),
                                  repo: Repository = Depends(get_repo)):
    saved=await rules.save_settings(repo,data.model_dump(),who.login)
    security_log.record('blog.moderation.settings',actor=who.login,role=who.role.value,reason=data.mode)
    return ModerationSettingsOut(**saved)


@admin.post('/posts/{post_id}/reply',response_model=AdminComment)
async def staff_reply(post_id: int,data: CommentIn,who: Principal = Depends(require_admin),
                       repo: Repository = Depends(get_repo)):
    await writable_post(repo,post_id)
    if not data.parent_id: raise HTTPException(422,'Виберіть коментар для відповіді')
    post=await get_post(repo,post_id)
    # writable_post already holds the post lock for persistent retry keys.
    row=await insert_comment(repo,post_id,data,name=who.name or 'Редакція ACCORD NICHE',staff=True,actor=who.login)
    return comment_out(row,AdminComment,post_title=post.title,post_slug=post.slug)
