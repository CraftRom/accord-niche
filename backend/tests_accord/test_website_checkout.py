"""Website checkout against real SQL, including pricing and retry recovery."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker

from api.routers import website_shop as web
from shop import models as m
from shop.config import settings
from shop.repo.factory import get_repo
from shop.repo.sql import SqlRepository
from shop.services import shop_settings

TOKEN='w'*48
CSRF='a'*48

@pytest_asyncio.fixture
async def checkout(monkeypatch):
    monkeypatch.setattr(settings,'bot_token','')
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as connection:
        await connection.run_sync(m.Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as session:
        repo=SqlRepository(session)
        app=FastAPI();app.include_router(web.router,prefix='/api/web')
        app.dependency_overrides[get_repo]=lambda:repo
        session.add_all([m.User(id=1,tg_id=-1001,referral_code='WEB-CHECKOUT'),m.User(id=2,tg_id=-1002,referral_code='OTHER-WEB')])
        session.add(m.Product(id=1,sku='LIVE-SKU',name='Аромат 5 мл',brand='Бренд',volume_ml=5,price=Decimal('100'),stock=5))
        await session.commit()
        session.add(m.WebsiteAccount(id=1,user_id=1))
        session.add(m.WebsiteSession(account_id=1,token_hash=hashlib.sha256(TOKEN.encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        await session.commit()
        shop_settings.prime_cache(shop_settings.ShopSettings.from_env())
        notifications=[]
        async def notify(*args):notifications.append(args[2].id)
        from shop.services import notifications as notification_service
        monkeypatch.setattr(notification_service,'notify_new_order',notify)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://accordniche.pp.ua') as client:
            client.cookies.set('__Host-accord_session',TOKEN);client.cookies.set('__Host-accord_csrf',CSRF)
            client.headers.update({'Origin':'https://accordniche.pp.ua','X-CSRF-Token':CSRF})
            yield client,session,notifications
    await engine.dispose()


async def quote(client,qty=1):
    response=await client.post('/api/web/checkout/quote',json={'items':[{'product_id':1,'qty':qty}]})
    assert response.status_code==200,response.text
    return response.json()


def payload(q,**changes):
    return {'checkout_key':'website-checkout-test-0001','quote_token':q['quote_token'],
        'contact_surname':'Покупець','contact_name':'Дмитро','contact_phone':'0671234567',
        'city':'Київ','address':'Відділення №1','delivery_method':'warehouse',
        'payment_method':'cod','terms_accepted':True,**changes}


@pytest.mark.asyncio
async def test_quote_precedes_consent_and_returns_actual_line_prices(checkout):
    client,session,_=checkout
    result=await quote(client,2)
    assert result['subtotal']=='200.00' and result['total']=='200.00'
    assert result['items']==[{'product_id':1,'qty':2,'name':'Аромат 5 мл','unit_price':'100.00','line_total':'200.00'}]
    assert (await session.scalar(select(func.count()).select_from(m.Order)))==0
    assert (await session.get(m.Product,1)).stock==5


@pytest.mark.asyncio
async def test_price_change_requires_fresh_confirmation_without_creating_order(checkout):
    client,session,_=checkout
    old=await quote(client)
    product=await session.get(m.Product,1);product.price=150
    await session.commit()
    rejected=await client.post('/api/web/checkout',json=payload(old))
    assert rejected.status_code==409,rejected.text
    assert rejected.json()['code']=='checkout_changed'
    assert (await session.scalar(select(func.count()).select_from(m.Order)))==0
    assert (await session.get(m.Product,1)).stock==5
    fresh=await quote(client)
    assert fresh['total']=='150.00'
    accepted=await client.post('/api/web/checkout',json=payload(fresh))
    assert accepted.status_code==200,accepted.text
    assert Decimal(accepted.json()['total'])==150


@pytest.mark.asyncio
async def test_lost_response_retry_creates_exactly_one_order_stock_change_and_notification(checkout):
    client,session,notifications=checkout
    q=await quote(client,2)
    first=await client.post('/api/web/checkout',json=payload(q))
    assert first.status_code==200,first.text
    again=await client.post('/api/web/checkout',json=payload(q))
    assert again.status_code==200,again.text
    assert again.json()['order_id']==first.json()['order_id'] and again.json()['replayed']
    status=await client.get('/api/web/checkout/status',params={'checkout_key':payload(q)['checkout_key']})
    assert status.json()['found'] and status.json()['order_id']==first.json()['order_id']
    assert (await session.scalar(select(func.count()).select_from(m.Order)))==1
    assert (await session.scalar(select(func.count()).select_from(m.CartItem)))==0
    assert (await session.get(m.Product,1)).stock==3
    assert notifications==[first.json()['order_id']]


@pytest.mark.asyncio
async def test_status_does_not_reveal_another_buyers_order(checkout):
    client,session,_=checkout
    session.add(m.Order(user_id=2,checkout_key='someone-elses-checkout'))
    await session.commit()
    response=await client.get('/api/web/checkout/status?checkout_key=someone-elses-checkout')
    assert response.status_code==200 and response.json()=={'found':False}
    client.cookies.delete('__Host-accord_session')
    assert (await client.get('/api/web/checkout/status?checkout_key=someone-elses-checkout')).status_code==401


@pytest.mark.asyncio
async def test_order_requires_quote_retry_key_consent_and_consistent_delivery(checkout):
    client,session,_=checkout
    q=await quote(client)
    for field in ['quote_token','checkout_key']:
        data=payload(q);data.pop(field)
        assert (await client.post('/api/web/checkout',json=data)).status_code==422
    for changes in [{'terms_accepted':False},{'delivery_warehouse_ref':'branch-without-city'},
                    {'contact_phone':'12345'},{'contact_phone':'067123456٧'},{'contact_name':'   '},
                    {'contact_surname':'а'*64,'contact_name':'б'*128,'contact_patronymic':'в'*64}]:
        response=await client.post('/api/web/checkout',json=payload(q,**changes))
        assert response.status_code==422,response.text
    assert (await session.scalar(select(func.count()).select_from(m.Order)))==0


@pytest.mark.asyncio
async def test_acquisition_campaign_is_stored_alongside_fixed_website_channel(checkout):
    client,session,_=checkout
    q=await quote(client)
    response=await client.post('/api/web/checkout',json=payload(q,attribution={'source':'Google Ads!','medium':' cpc ','campaign':'Autumn'}))
    assert response.status_code==200,response.text
    row=await session.get(m.Order,response.json()['order_id'])
    assert row.attribution['source']=='google_ads_' and row.attribution['medium']=='cpc'
    assert row.attribution['campaign']=='Autumn' and row.attribution['channel']=='accord_website'


@pytest.mark.asyncio
async def test_modified_or_insufficient_cart_cannot_be_submitted_with_old_quote(checkout):
    client,session,_=checkout
    q=await quote(client,2)
    await quote(client,1)
    assert (await client.post('/api/web/checkout',json=payload(q))).status_code==409
    p=await session.get(m.Product,1);p.stock=0
    await session.commit()
    assert (await client.post('/api/web/checkout',json=payload(q))).status_code==409
    assert (await session.scalar(select(func.count()).select_from(m.Order)))==0


@pytest.mark.asyncio
async def test_whitespace_only_profile_name_is_rejected(checkout):
    client,session,_=checkout
    account=await session.get(m.WebsiteAccount,1);account.google_sub='verified-google'
    await session.commit()
    assert (await client.patch('/api/web/profile',json={'display_name':'   '})).status_code==422


@pytest.mark.asyncio
async def test_login_display_name_is_not_assumed_to_be_the_shipping_first_name(checkout):
    client,session,_=checkout
    account=await session.get(m.WebsiteAccount,1)
    account.display_name='Sebas / Дмитро Галицький';account.verified_phone='+380671234567'
    await session.commit()
    defaults=(await client.get('/api/web/checkout/defaults')).json()
    assert defaults['contact_name']=='' and defaults['contact_phone']=='+380671234567'
