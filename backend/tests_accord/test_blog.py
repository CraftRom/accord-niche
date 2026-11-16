"""Real SQL/API checks for publication, identity, moderation and edit conflicts."""
from datetime import datetime, timedelta, timezone
import hashlib

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from api.auth import Principal, require_admin
from api.routers import blog
from shop import models as m
from shop.entities import OperatorRole
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository

ADMIN=Principal(login='owner',name='Редактор',role=OperatorRole.SYSADMIN,operator_id=0)
TOKEN='s'*48
CSRF='a'*48

@pytest_asyncio.fixture
async def api():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        repo=SqlRepository(session)
        app=FastAPI()
        app.include_router(blog.admin,prefix='/api/blog')
        app.include_router(blog.public,prefix='/api/public/blog')
        app.include_router(blog.web,prefix='/api/web/blog')
        app.dependency_overrides[get_repo]=lambda:repo
        app.dependency_overrides[require_admin]=lambda:ADMIN
        session.add_all([m.User(id=1,tg_id=1,referral_code='BLOG1'),m.User(id=2,tg_id=2,referral_code='BLOG2')])
        await session.commit()
        session.add_all([m.WebsiteAccount(id=1,user_id=1,google_sub='verified-google',display_name='Покупець'),
                         m.WebsiteAccount(id=2,user_id=2,display_name='Гість')])
        session.add(m.WebsiteSession(account_id=1,token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        await session.commit()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://accordniche.pp.ua') as client:
            client.cookies.set('__Host-accord_session',TOKEN)
            client.cookies.set('__Host-accord_csrf',CSRF)
            client.headers.update({'Origin':'https://accordniche.pp.ua','X-CSRF-Token':CSRF})
            yield client,session,app
    await engine.dispose()


def article(**changes):
    return dict(title='Живий блог',slug='real-blog',excerpt='Опис статті',body='Справжній зміст статті про аромати та магазин.',status='published',**changes)


async def post(client,**changes):
    data=article()
    data.update(changes)
    response=await client.post('/api/blog/posts',json=data)
    assert response.status_code==201,response.text
    return response.json()


async def send(client,post_id,**changes):
    data=dict(body='Мій коментар',client_key='comment-test-key-0001')
    data.update(changes)
    return await client.post('/api/web/blog/posts/'+str(post_id)+'/comments',json=data)


@pytest.mark.asyncio
async def test_drafts_scheduled_and_archived_posts_never_leak(api):
    client,_,_=api
    draft=await post(client,status='draft',slug='draft')
    scheduled=await post(client,slug='future',published_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    archived=await post(client,status='archived',slug='archive')
    visible=await post(client)
    response=await client.get('/api/public/blog')
    assert response.status_code==200
    assert [p['id'] for p in response.json()['items']]==[visible['id']]
    for slug in ['draft','future','archive']:
        assert (await client.get('/api/public/blog/'+slug)).status_code==404
    assert 'created_by' not in response.text and '"body"' not in response.text


@pytest.mark.asyncio
async def test_slug_changes_keep_old_links_and_old_slugs_cannot_be_stolen(api):
    client,_,_=api
    item=await post(client)
    changed=await client.put('/api/blog/posts/'+str(item['id']),json={**article(), 'slug':'new-address','version':item['version']})
    assert changed.status_code==200,changed.text
    assert (await client.get('/api/public/blog/real-blog')).json()['slug']=='new-address'
    assert (await client.get('/api/public/blog/new-address')).json()['id']==item['id']
    duplicate=await client.post('/api/blog/posts',json=article())
    assert duplicate.status_code==409
    assert (await client.get('/api/public/blog')).json()['total']==1


@pytest.mark.asyncio
async def test_stale_edits_and_duplicate_slug_roll_back_without_lost_content(api):
    client,_,_=api
    item=await post(client)
    other=await post(client,slug='other')
    first=await client.put('/api/blog/posts/'+str(item['id']),json={**article(),'title':'Збережений текст','version':1})
    assert first.status_code==200
    stale=await client.put('/api/blog/posts/'+str(item['id']),json={**article(),'title':'Старе редагування','version':1})
    assert stale.status_code==409
    duplicate=await client.put('/api/blog/posts/'+str(item['id']),json={**article(),'slug':'other','version':2})
    assert duplicate.status_code==409
    assert (await client.get('/api/blog/posts/'+str(item['id']))).json()['title']=='Збережений текст'


@pytest.mark.asyncio
async def test_comment_lifecycle_requires_moderation_and_edit_returns_to_pending(api):
    client,_,_=api
    item=await post(client)
    response=await send(client,item['id'])
    assert response.status_code==200,response.text
    comment=response.json()
    assert comment['status']=='pending'
    assert (await client.get('/api/public/blog/real-blog/comments')).json()['total']==0
    approved=await client.post('/api/blog/comments/'+str(comment['id'])+'/moderate',json={'status':'approved','version':1})
    assert approved.status_code==200,approved.text
    visible=(await client.get('/api/public/blog/real-blog/comments')).json()
    assert visible['total']==1
    assert 'author_user_id' not in str(visible) and 'moderation_note' not in str(visible) and 'client_key' not in str(visible)
    edited=await client.put('/api/web/blog/comments/'+str(comment['id']),json={'body':'Оновлений текст','version':2})
    assert edited.status_code==200 and edited.json()['status']=='pending'
    assert (await client.get('/api/public/blog/real-blog/comments')).json()['total']==0


@pytest.mark.asyncio
async def test_guest_session_is_not_comment_authorization(api):
    client,session,_=api
    item=await post(client)
    account=await session.get(m.WebsiteAccount,1)
    account.google_sub=None
    await session.commit()
    assert (await send(client,item['id'])).status_code==401
    client.cookies.delete('__Host-accord_session')
    assert (await send(client,item['id'])).status_code==401


@pytest.mark.asyncio
async def test_csrf_blocked_identity_and_closed_comments_are_enforced(api):
    client,session,_=api
    item=await post(client)
    client.headers['X-CSRF-Token']='b'*48
    assert (await send(client,item['id'])).status_code==403
    client.headers['X-CSRF-Token']=CSRF
    user=await session.get(m.User,1)
    user.is_blocked=True
    await session.commit()
    assert (await send(client,item['id'])).status_code==403
    user.is_blocked=False
    await session.commit()
    closed=await post(client,slug='closed',comments_enabled=False)
    assert (await send(client,closed['id'])).status_code==409


@pytest.mark.asyncio
async def test_retry_is_idempotent_and_new_spam_is_rate_limited(api):
    client,_,_=api
    item=await post(client)
    first=await send(client,item['id'])
    again=await send(client,item['id'])
    assert first.json()['id']==again.json()['id']
    assert (await send(client,item['id'],body='Інший текст')).status_code==409
    assert (await send(client,item['id'],client_key='another-comment-key')).status_code==429
    assert (await client.get('/api/blog/comments')).json()['total']==1


@pytest.mark.asyncio
async def test_thread_integrity_and_parent_moderation_hide_replies(api):
    client,_,_=api
    item=await post(client)
    root=(await send(client,item['id'])).json()
    await client.post('/api/blog/comments/'+str(root['id'])+'/moderate',json={'status':'approved','version':1})
    reply=await client.post('/api/blog/posts/'+str(item['id'])+'/reply',json={'body':'Відповідь редакції','parent_id':root['id'],'client_key':'staff-reply-key-0001'})
    assert reply.status_code==200,reply.text
    again=await client.post('/api/blog/posts/'+str(item['id'])+'/reply',json={'body':'Відповідь редакції','parent_id':root['id'],'client_key':'staff-reply-key-0001'})
    assert again.json()['id']==reply.json()['id']
    public=(await client.get('/api/public/blog/real-blog/comments')).json()
    assert public['items'][0]['reply_count']==1
    assert (await client.get('/api/public/blog/real-blog')).json()['comment_count']==2
    await client.post('/api/blog/comments/'+str(root['id'])+'/moderate',json={'status':'rejected','version':2})
    assert (await client.get('/api/public/blog/real-blog')).json()['comment_count']==0
    assert (await client.get('/api/public/blog/real-blog/comments?parent_id='+str(root['id']))).status_code==404


@pytest.mark.asyncio
async def test_ownership_delete_and_reserved_urls_cannot_be_bypassed(api):
    client,session,_=api
    item=await post(client)
    comment=(await send(client,item['id'])).json()
    session.add(m.WebsiteSession(account_id=2,token_hash=hashlib.sha256(('t'*48).encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    account=await session.get(m.WebsiteAccount,2)
    account.google_sub='second-google'
    await session.commit()
    client.cookies.set('__Host-accord_session','t'*48)
    assert (await client.put('/api/web/blog/comments/'+str(comment['id']),json={'body':'Чужа зміна','version':1})).status_code==404
    client.cookies.set('__Host-accord_session',TOKEN)
    deleted=await client.request('DELETE','/api/web/blog/comments/'+str(comment['id']),json={'version':1})
    assert deleted.status_code==200,deleted.text
    assert (await client.post('/api/blog/comments/'+str(comment['id'])+'/moderate',json={'status':'approved','version':2})).status_code==409
    assert (await client.get('/api/web/blog/posts/'+str(item['id'])+'/mine')).json()==[]


@pytest.mark.asyncio
async def test_staff_authorization_guard_is_used_on_all_admin_routes(api):
    client,_,app=api
    def forbidden():
        raise HTTPException(403,'Лише адміністратор')
    app.dependency_overrides[require_admin]=forbidden
    for path in ['/api/blog/posts','/api/blog/posts/1','/api/blog/comments']:
        assert (await client.get(path)).status_code==403
    assert (await client.post('/api/blog/posts',json=article())).status_code==403


@pytest.mark.asyncio
async def test_validation_rejects_unsafe_cover_naive_dates_and_empty_publications(api):
    client,_,_=api
    for changes in [{'cover_url':'javascript:alert(1)'},{'cover_url':'//evil.test/x.jpg'},
                    {'cover_url':'/media/../../private.jpg'},{'published_at':'2026-11-16T12:00:00'},
                    {'body':' '},{'status':'invented'}]:
        response=await client.post('/api/blog/posts',json={**article(),**changes})
        assert response.status_code==422,response.text
    assert (await client.get('/api/public/blog')).json()['total']==0


@pytest.mark.asyncio
async def test_ukrainian_search_is_case_insensitive_and_wildcards_are_literal(api):
    client,_,_=api
    await post(client,title='Українські аромати 100%',excerpt='Серія niche_1')
    await post(client,slug='unrelated',title='Інший матеріал')
    for q in ['УКРАЇНСЬКІ','аромати','100%','niche_1']:
        for path in ['/api/public/blog','/api/blog/posts']:
            result=await client.get(path,params={'q':q})
            assert result.status_code==200,result.text
            assert result.json()['total']==1
    assert (await client.get('/api/public/blog',params={'q':'niche_2'})).json()['total']==0


@pytest.mark.asyncio
async def test_moderation_rejects_stale_versions_and_delete_hides_thread(api):
    client,_,_=api
    item=await post(client)
    root=(await send(client,item['id'])).json()
    url='/api/blog/comments/'+str(root['id'])+'/moderate'
    assert (await client.post(url,json={'status':'approved','version':1,'note':'Внутрішня примітка'})).status_code==200
    assert (await client.post(url,json={'status':'rejected','version':1})).status_code==409
    reply=await client.post('/api/blog/posts/'+str(item['id'])+'/reply',json={'body':'Редакція відповідає','parent_id':root['id'],'client_key':'editorial-reply-0001'})
    assert reply.status_code==200
    visible=await client.get('/api/public/blog/real-blog/comments')
    assert 'Внутрішня примітка' not in visible.text
    assert visible.headers['Cache-Control']=='no-store'
    assert (await client.request('DELETE','/api/web/blog/comments/'+str(root['id']),json={'version':1})).status_code==409
    assert (await client.request('DELETE','/api/web/blog/comments/'+str(root['id']),json={'version':2})).status_code==200
    assert (await client.get('/api/public/blog/real-blog')).json()['comment_count']==0
    assert (await client.get('/api/public/blog/real-blog/comments')).json()['total']==0


@pytest.mark.asyncio
async def test_cross_post_replies_and_deep_threads_are_rejected(api):
    client,_,_=api
    one=await post(client)
    two=await post(client,slug='another-post')
    root=(await send(client,one['id'])).json()
    await client.post('/api/blog/comments/'+str(root['id'])+'/moderate',json={'status':'approved','version':1})
    data={'body':'Відповідь редакції','parent_id':root['id'],'client_key':'editorial-reply-0001'}
    assert (await client.post('/api/blog/posts/'+str(two['id'])+'/reply',json=data)).status_code==409
    reply=(await client.post('/api/blog/posts/'+str(one['id'])+'/reply',json=data)).json()
    assert (await client.post('/api/blog/posts/'+str(one['id'])+'/reply',json={**data,'parent_id':reply['id'],'client_key':'editorial-reply-0002'})).status_code==409


@pytest.mark.asyncio
async def test_comment_ownership_survives_proven_account_merge(api):
    from shop.services.website_identity import attach_guest_identity
    client,session,_=api
    item=await post(client)
    guest=await session.get(m.WebsiteAccount,1)
    guest.google_sub=None
    guest.verified_phone='+380501234567'
    target=await session.get(m.WebsiteAccount,2)
    target.google_sub='merged-google'
    await session.commit()
    comment=(await send(client,item['id'])).json()
    await attach_guest_identity(SqlRepository(session),target,guest)
    session.add(m.WebsiteSession(account_id=2,token_hash=hashlib.sha256(('m'*48).encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    await session.commit()
    client.cookies.set('__Host-accord_session','m'*48)
    own=await client.get('/api/web/blog/posts/'+str(item['id'])+'/mine')
    assert [row['id'] for row in own.json()]==[comment['id']]
    assert (await send(client,item['id'])).json()['id']==comment['id']
    assert (await send(client,item['id'],client_key='new-account-retry-key')).status_code==429
    assert (await client.put('/api/web/blog/comments/'+str(comment['id']),json={'body':'Зміна після входу через Google','version':1})).status_code==200
    assert (await session.get(m.BlogComment,comment['id'])).author_user_id==1


@pytest.mark.asyncio
async def test_hourly_limit_counts_hidden_comments_and_media_references_include_drafts(api):
    client,session,_=api
    item=await post(client,status='draft',cover_url='/media/cover-123.jpg',body='Текст із зображенням ![Кадр](/media/inline-456.webp)')
    repo=SqlRepository(session)
    assert (await repo.media_references('/media/cover-123.jpg'))['blog']==1
    assert (await repo.media_references('/media/inline-456.webp'))['blog']==1
    live=await post(client,slug='live-article')
    session.add_all([m.BlogComment(post_id=live['id'],author_user_id=1,author_name='Автор',body='Коментар',status='rejected',created_at=datetime.now(timezone.utc)-timedelta(minutes=5)) for _ in range(10)])
    await session.commit()
    assert (await send(client,live['id'])).status_code==429
