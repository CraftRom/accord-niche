"""Comment moderation: bans, automatic rules, bulk actions, permanent removal, SEO fields."""
import pytest
from sqlalchemy import select

from shop import models as m
from tests_accord.test_blog import api, post, send  # noqa: F401  (fixture and helpers)


async def age(session):
    """Move earlier comments out of the 20-second rate-limit window."""
    from datetime import datetime, timedelta, timezone
    await session.execute(m.BlogComment.__table__.update().values(created_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
    await session.commit()


async def queue(client, **params):
    response = await client.get('/api/blog/comments', params={'status': '', **params})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_banned_author_cannot_comment_or_edit_and_comments_are_hidden(api):
    client, session, _ = api
    article = await post(client)
    sent = await send(client, article['id'])
    assert sent.status_code == 200 and sent.json()['status'] == 'pending'
    ban = await client.post('/api/blog/bans', json={'user_id': 1, 'reason': 'спам', 'days': 7, 'comments': 'hide'})
    assert ban.status_code == 201, ban.text
    assert ban.json()['author_name'] == 'Покупець' and ban.json()['expires_at']
    item = (await queue(client))['items'][0]
    assert item['status'] == 'rejected' and item['author_banned'] is True
    blocked = await send(client, article['id'], client_key='comment-test-key-0002', body='Ще один')
    assert blocked.status_code == 403 and 'обмежила' in blocked.json()['detail']
    edit = await client.put(f"/api/web/blog/comments/{item['id']}", json={'body': 'Змінений', 'version': item['version']})
    assert edit.status_code == 403
    assert [b['user_id'] for b in (await client.get('/api/blog/bans')).json()] == [1]
    assert (await client.delete('/api/blog/bans/1')).status_code == 200
    await age(session)
    again = await send(client, article['id'], client_key='comment-test-key-0003', body='Після розблокування')
    assert again.status_code == 200
    assert (await client.delete('/api/blog/bans/1')).status_code == 404


@pytest.mark.asyncio
async def test_ban_can_delete_every_comment_of_the_author(api):
    client, session, _ = api
    article = await post(client)
    await send(client, article['id'])
    ban = await client.post('/api/blog/bans', json={'user_id': 1, 'comments': 'delete'})
    assert ban.status_code == 201 and ban.json()['expires_at'] is None
    assert (await queue(client))['total'] == 0


@pytest.mark.asyncio
async def test_stop_words_links_and_contacts_are_held_or_rejected(api):
    client, session, _ = api
    article = await post(client)
    saved = await client.put('/api/blog/moderation-settings', json={
        'mode': 'manual', 'trusted_after': 3, 'stop_words': 'казино, дурень', 'stop_word_action': 'reject', 'hold_links': True})
    assert saved.status_code == 200 and saved.json()['updated_by'] == 'owner'
    rejected = await send(client, article['id'], body='Грайте в КАЗИНО тут')
    assert rejected.json()['status'] == 'rejected'
    session.expire_all()
    row = await session.scalar(select(m.BlogComment).where(m.BlogComment.id == rejected.json()['id']))
    assert row.flags == 'stop_word' and row.moderated_by == 'auto'
    # Word boundaries: "classic" style false positives never trigger.
    from shop.services.comment_moderation import scan
    rules = {'stop_words': 'ass', 'hold_links': True}
    assert scan('classic scent', rules) == []
    assert scan('see www.spam.com', rules) == ['link']
    assert scan('пишіть +38 (067) 123-45-67', rules) == ['contact']
    assert scan('mail me a@b.ua', rules) == ['contact']
    flagged = await queue(client, flagged='true')
    assert flagged['total'] == 1 and flagged['counts']['rejected'] == 1


@pytest.mark.asyncio
async def test_trusted_authors_are_published_at_once(api):
    client, session, _ = api
    article = await post(client)
    await client.put('/api/blog/moderation-settings', json={'mode': 'trusted', 'trusted_after': 1, 'stop_words': '',
                                                          'stop_word_action': 'hold', 'hold_links': True})
    first = (await send(client, article['id'])).json()
    assert first['status'] == 'pending'
    approved = await client.post(f"/api/blog/comments/{first['id']}/moderate", json={'status': 'approved', 'version': first['version']})
    assert approved.status_code == 200 and approved.json()['author_approved'] == 1
    from datetime import datetime, timedelta, timezone
    await session.execute(m.BlogComment.__table__.update().values(created_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
    await session.commit()
    second = (await send(client, article['id'], client_key='comment-test-key-0002', body='Вже довіряють')).json()
    assert second['status'] == 'approved'
    await session.execute(m.BlogComment.__table__.update().values(created_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
    await session.commit()
    with_link = (await send(client, article['id'], client_key='comment-test-key-0003', body='Дивіться https://x.example')).json()
    assert with_link['status'] == 'pending', 'links wait for a moderator even from trusted authors'


@pytest.mark.asyncio
async def test_bulk_actions_search_and_permanent_delete_with_replies(api):
    client, session, _ = api
    article = await post(client)
    from datetime import datetime, timedelta, timezone
    ids = []
    for index in range(3):
        await session.execute(m.BlogComment.__table__.update().values(created_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
        await session.commit()
        ids.append((await send(client, article['id'], client_key=f'comment-test-key-010{index}', body=f'Текст номер {index}')).json()['id'])
    bulk = await client.post('/api/blog/comments/bulk', json={'ids': ids, 'action': 'approve'})
    assert bulk.json() == {'changed': 3}
    reply = await client.post(f"/api/blog/posts/{article['id']}/reply",
                              json={'parent_id': ids[0], 'body': 'Відповідь редакції', 'client_key': 'staff-reply-key-01'})
    assert reply.status_code == 200, reply.text
    found = await queue(client, q='номер 1')
    assert [c['id'] for c in found['items']] == [ids[1]]
    assert (await client.delete(f'/api/blog/comments/{ids[0]}')).json() == {'deleted': 2}
    assert (await client.post('/api/blog/comments/bulk', json={'ids': ids[1:], 'action': 'reject'})).json() == {'changed': 2}
    data = await queue(client)
    assert data['total'] == 2 and data['counts'] == {'pending': 0, 'approved': 0, 'rejected': 2, 'deleted': 0}
    assert (await client.delete(f'/api/blog/comments/{ids[0]}')).status_code == 404


@pytest.mark.asyncio
async def test_post_seo_fields_round_trip(api):
    client, _, _ = api
    created = await post(client, seo_title='SEO заголовок', seo_description='Опис для Google', focus_keyword='нішеві аромати',
                         cover_alt='Флакон', noindex=True)
    assert created['seo_title'] == 'SEO заголовок' and created['noindex'] is True and created['cover_alt'] == 'Флакон'
    public = (await client.get('/api/public/blog/real-blog')).json()
    assert public['cover_alt'] == 'Флакон' and 'seo_title' not in public and 'focus_keyword' not in public
