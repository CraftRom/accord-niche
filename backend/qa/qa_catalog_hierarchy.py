"""HTTP/repository/migration catalog checks: brands replaced categories."""
import asyncio, importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import create_engine, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from qa_common import boot,init_data,Report
test_directory=TemporaryDirectory(prefix='catalog-hierarchy-')
app,Session,_=boot(str(Path(test_directory.name)/'catalog.db')); c=TestClient(app); r=Report('CATALOG HIERARCHY')
A={'Authorization':'Bearer '+c.post('/api/auth/login',json={'login':'admin','password':'secret'}).json()['access_token']}
H=init_data(90123); c.get('/api/shop/config',headers=H)
def req(method,path,data=None):
 response=c.request(method,'/api/catalog'+path,json=data,headers=A)
 assert response.status_code<300,(response.status_code,response.text)
 return response.json() if response.content else None
root=req('POST','/brands',{'name':'Creed'}); other=req('POST','/brands',{'name':'Kilian'})
r.check(c.post('/api/catalog/brands',json={'name':'  creed '},headers=A).status_code==409,'назва бренду унікальна без урахування регістру й пробілів')
groups=[{}, {'brand_id':root['id']}, {'brand_id':root['id']}, {'brand_id':root['id']}, {'brand':'Nasomatto'}]
ps=[req('POST','/products',{'name':f'Аромат {i}','price':'129.90','stock':4,'sku':'USER-ARTICLE',**group}) for i,group in enumerate(groups)]
r.check(all(p['sku'].startswith('ELF-') and p['sku']!='USER-ARTICLE' for p in ps),'автоматичний SKU для товарів з брендом і без')
r.check(ps[1]['sku'].startswith('ELF-CREE-'),'SKU містить код бренду')
r.check(len({p['sku'] for p in ps})==5,'унікальність SKU')
r.check(ps[1]['brand']=='Creed' and ps[1]['brand_id']==root['id'],'товар отримує назву обраного бренду')
naso=next(x for x in req('GET','/brands') if x['name']=='Nasomatto')
r.check(ps[4]['brand_id']==naso['id'],'бренд за назвою (імпорт, старі клієнти) створюється автоматично')
def public(**params): return c.get('/api/shop/products',params=params,headers=H).json()
r.check(len(public())==5,'товари без бренду не губляться')
r.check(len(public(brand_id=root['id']))==3,'відбір бренду')
r.check(next(x for x in req('GET','/brands') if x['id']==root['id'])['products_count']==3,'лічильник товарів бренду')
r.check(c.get('/api/shop/products',params={'category_id':root['id']},headers=H).status_code==200 and len(public(category_id=root['id']))==5,'старий параметр категорії ігнорується, а не ламає вітрину')
mini=c.get('/api/shop/brands',headers=H).json()
r.check({x['name'] for x in mini}=={'Creed','Nasomatto'},'Mini App бачить лише бренди з товарами', mini)
r.check('categories' not in c.get('/api/shop/bootstrap',headers=H).json(),'вітрина більше не отримує категорій')
p=ps[3]; pid=p['id']; ep=f'/products/{pid}'
req('PATCH',ep,{'is_new':True}); r.check(len(public(is_new=True))==1,'новинка збережена й керує API вітрини')
req('PATCH',ep,{'is_sale':True,'old_price':'159.90','price':'129.90'}); r.check(len(public(is_sale=True))==1,'акція збігається в обох API')
r.check(c.patch('/api/catalog'+ep,json={'old_price':'100'},headers=A).status_code==400,'невалідна акційна ціна відхиляється')
x=req('PATCH',ep,{'description':'Новий опис'})
r.check(x['is_new'] and x['is_sale'] and x['stock']==4 and x['price']=='129.90','зміна опису не перезаписує інші блоки')
r.check(x['sku']==p['sku'],'SKU незмінний')
r.check(c.patch('/api/catalog'+ep,json={'sku':'REPLACED'},headers=A).status_code==422,'PATCH забороняє зміну SKU')
r.check(c.patch('/api/catalog'+ep,json={'category_id':other['id']},headers=A).status_code==422,'поля категорії більше не приймаються')
r.check(c.patch('/api/catalog'+ep,json={'brand_id':99999},headers=A).status_code==400,'неіснуючий бренд відхиляється')
moved=req('PATCH',ep,{'brand_id':other['id']})
r.check(moved['brand']=='Kilian' and moved['brand_id']==other['id'],'перенесення товару до іншого бренду')
renamed=c.patch(f"/api/catalog/brands/{other['id']}",json={'name':'By Kilian'},headers=A)
r.check(renamed.status_code==200 and req('GET',ep)['brand']=='By Kilian','перейменування бренду оновлює назву в товарах')
r.check(c.delete(f"/api/catalog/brands/{other['id']}",headers=A).status_code==409,'бренд із товарами не видаляється')
c.patch(f"/api/catalog/brands/{other['id']}",json={'is_active':False},headers=A)
r.check(c.get(f'/api/shop/products/{pid}',headers=H).status_code==404 and req('GET',ep)['is_active'],'прихований бренд ховає товар, не переписуючи його прапорець')
c.patch(f"/api/catalog/brands/{other['id']}",json={'is_active':True},headers=A)
empty=req('POST','/brands',{'name':'Порожній'})
r.check(c.delete(f"/api/catalog/brands/{empty['id']}",headers=A).status_code==204,'бренд без товарів видаляється')
req('PATCH',ep,{'brand':'','is_sale':False}); r.check(not public(is_sale=True) and req('GET',ep)['brand_id'] is None,'порожня назва знімає бренд; вимкнена акція прибрана')
req('PATCH',ep,{'is_active':False}); r.check(c.get(f'/api/shop/products/{pid}',headers=H).status_code==404,'прихований товар недоступний на сторінці вітрини')
req('PATCH',ep,{'is_active':True}); r.check(req('GET',ep)['is_new'],'відновлення видимості зберігає новинку')
async def repository_checks():
 from shop.repo.sql import SqlRepository
 from shop import models as m
 from shop.services.product_io import export_xlsx,parse_salesdrive_xlsx
 from bot import keyboards as kb
 async with Session() as session:
  repo=SqlRepository(session); row=await session.get(m.Product,pid); row.photo_file_id='old-photo'; await session.commit()
 response=c.patch('/api/catalog'+ep,json={'photo_url':'https://example.com/image.png'},headers=A)
 async with Session() as session:
  repo=SqlRepository(session); after=await repo.get_product(pid); article=after.sku
  r.check(after.photo_file_id is None and after.photo_url,'нове фото замінює Telegram фото')
  after=await repo.update_product(pid,{'sku':'OVERRIDE','name':'Змінена назва'})
  r.check(after.sku==article,'SKU захищений також у репозиторії')
  parsed=parse_salesdrive_xlsx(export_xlsx(await repo.list_products()))
  r.check(len(parsed)==5 and all(x['hierarchy'] for x in parsed),'XLSX читає власний експорт')
  r.check({x['brand'] for x in parsed}>={'Creed','Nasomatto'},'XLSX переносить бренд')
  r.check(kb.product_card(await repo.get_product(ps[0]['id'])).inline_keyboard[-1][0].callback_data=='shelf:all','бот повертає товар без бренду до всіх товарів')
  r.check(kb.product_card(await repo.get_product(ps[2]['id'])).inline_keyboard[-1][0].callback_data==f"brand:{root['id']}",'бот повертає товар до його бренду')
  with patch('shop.services.product_io.generate_sku',side_effect=[article,'ELF-GEN-UNIQUE01']):
   created=await repo.create_product({'name':'Колізія','price':Decimal('10')})
  r.check(created.sku=='ELF-GEN-UNIQUE01','колізія під час INSERT повторює генерацію')
asyncio.run(repository_checks())
# Pagination preserves filters and covers products beyond the legacy 500-row cap.
async def seed_large_catalog():
 from shop import models as m
 async with Session() as session:
  session.add_all([m.Product(name=f'Великий каталог {i:04}', name_lower=f'великий каталог {i:04}', sku=f'ELF-PAGE-{i:04}', price=Decimal('10'), stock=1, is_new=i==502) for i in range(503)])
  await session.commit()
asyncio.run(seed_large_catalog())
first=public(search='Великий каталог',limit=500,offset=0)
last=public(search='Великий каталог',limit=500,offset=500)
r.check(len(first)==500 and len(last)==3,'понад 500 товарів доступні наступною сторінкою')
r.check(len({p['id'] for p in first+last})==503,'сторінки не дублюють і не гублять товари')
r.check(last[-1]['is_new'],'новинка за межами першої сторінки збережена')
r.check(public(search='Великий каталог',limit=2,offset=2)==first[2:4],'offset працює разом із пошуком')
r.check(not public(search='Великий каталог',brand_id=root['id'],limit=2),'наступні сторінки поважають бренд')
r.check(c.get('/api/shop/products',params={'limit':0},headers=H).status_code==422,'нульовий розмір сторінки відхиляється')
r.check(c.get('/api/shop/products',params={'limit':501},headers=H).status_code==422,'завеликий розмір сторінки відхиляється')
r.check(c.get('/api/shop/products',params={'offset':-1},headers=H).status_code==422,'від’ємний offset відхиляється')
spec=importlib.util.spec_from_file_location('catalog_migration','alembic/versions/d7a24c10b853_catalog_taxonomy.py'); mig=importlib.util.module_from_spec(spec); spec.loader.exec_module(mig)
with create_engine('sqlite:///:memory:').begin() as conn:
 conn.execute(text('CREATE TABLE categories (id INTEGER PRIMARY KEY,name VARCHAR(128) NOT NULL,description TEXT,sort_order INTEGER NOT NULL,is_active BOOLEAN NOT NULL)'))
 conn.execute(text('CREATE TABLE products (id INTEGER PRIMARY KEY,category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,name VARCHAR(255),sku VARCHAR(32) NOT NULL UNIQUE,price NUMERIC,old_price NUMERIC,is_active BOOLEAN,sort_order INTEGER)'))
 conn.execute(text("INSERT INTO categories VALUES (7,'Сумки','Опис групи',3,1)"))
 for pid,sku in [(1,'VALID-001'),(2,' abc-12 '),(3,'невалідний'),(4,'ABC-12')]:
  conn.execute(text('INSERT INTO products VALUES (:id,7,:name,:sku,100,150,1,0)'),{'id':pid,'name':f'Товар {pid}','sku':sku})
 with Operations.context(MigrationContext.configure(conn)): mig.upgrade()
 rows=conn.execute(text('SELECT id,category_id,subcategory_id,sku,external_sku,is_new,is_sale FROM products ORDER BY id')).all()
 r.check(len(rows)==4 and all(x.category_id is None and x.subcategory_id==7 for x in rows),'міграція зберігає всі товари й зв’язки')
 r.check(conn.scalar(text('SELECT COUNT(*) FROM categories'))==0 and conn.scalar(text('SELECT name FROM subcategories WHERE id=7'))=='Сумки','старі категорії перенесені зі збереженням ID')
 r.check(rows[0].sku=='VALID-001' and rows[3].sku=='ABC-12','коректні SKU збережені')
 r.check(rows[1].sku.startswith('ELF-LEG-') and rows[2].sku.startswith('ELF-LEG-'),'невалідні та конфліктні SKU виправлені')
 r.check(rows[1].external_sku==' abc-12 ' and rows[2].external_sku=='невалідний','початкові артикули не втрачені')
 r.check(all(not x.is_new and x.is_sale for x in rows),'старі акції перенесені, новинки не вигадуються')
 conn.execute(text("INSERT INTO subcategories (name,sort_order,is_active) VALUES ('Нова група',0,1)"))
 r.check(conn.scalar(text('SELECT MAX(id) FROM subcategories'))==8,'нові ID не конфліктують із перенесеними')
# Brands replace categories: the data migration keeps names, hidden goods and promo scope.
spec=importlib.util.spec_from_file_location('brands_migration','alembic/versions/e2b7c4a91d05_brands_replace_categories.py'); brands=importlib.util.module_from_spec(spec); spec.loader.exec_module(brands)
with create_engine('sqlite:///:memory:').begin() as conn:
 conn.execute(text('CREATE TABLE categories (id INTEGER PRIMARY KEY,name VARCHAR(128),description TEXT,sort_order INTEGER,is_active BOOLEAN)'))
 conn.execute(text('CREATE TABLE subcategories (id INTEGER PRIMARY KEY,category_id INTEGER,name VARCHAR(128),description TEXT,sort_order INTEGER,is_active BOOLEAN)'))
 conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY,category_id INTEGER,subcategory_id INTEGER,brand VARCHAR(100) NOT NULL DEFAULT '',is_active BOOLEAN)"))
 conn.execute(text("CREATE TABLE promo_codes (id INTEGER PRIMARY KEY,code VARCHAR(32),is_active BOOLEAN,category_ids JSON NOT NULL DEFAULT '[]')"))
 conn.execute(text("INSERT INTO categories VALUES (1,'Ніша',NULL,0,1),(2,'Прихована',NULL,0,0)"))
 conn.execute(text("INSERT INTO subcategories VALUES (5,1,'Літо',NULL,0,0),(6,2,'Осінь',NULL,0,1)"))
 conn.execute(text("INSERT INTO products VALUES (1,1,NULL,'Creed',1),(2,NULL,NULL,' creed  ',1),(3,2,NULL,'Kilian',1),(4,NULL,5,'Kilian',1),(5,NULL,6,'',1),(6,1,NULL,'Amouage',0)"))
 conn.execute(text("INSERT INTO promo_codes VALUES (1,'ALL',1,'[]'),(2,'NICHE',1,'[1]'),(3,'GHOST',1,'[99]')"))
 with Operations.context(MigrationContext.configure(conn)): brands.upgrade()
 names=dict(conn.execute(text('SELECT name_key,id FROM brands')).all())
 r.check(set(names)=={'creed','kilian','amouage'},'бренди створено з назв товарів без дублів за регістром', names)
 rows={x.id:x for x in conn.execute(text('SELECT id,brand,brand_id,is_active FROM products')).all()}
 r.check(rows[1].brand_id==rows[2].brand_id==names['creed'] and rows[2].brand=='Creed','товари отримали свій бренд, назва нормалізована')
 r.check(rows[5].brand_id is None,'товар без назви бренду лишається без бренду')
 r.check(not rows[3].is_active and not rows[4].is_active and not rows[5].is_active,'товари з прихованих груп лишаються прихованими')
 r.check(rows[1].is_active and not rows[6].is_active,'видимі й окремо приховані товари без змін')
 promos={x.code:x for x in conn.execute(text('SELECT code,is_active,brand_ids FROM promo_codes')).all()}
 import json as _json
 niche=promos['NICHE'].brand_ids; niche=_json.loads(niche) if isinstance(niche,str) else niche
 # Category 1 holds Creed and Amouage directly and Kilian through its subcategory.
 r.check(niche==sorted([names['creed'],names['amouage'],names['kilian']]) and promos['NICHE'].is_active,'промокод категорії став промокодом її брендів', niche)
 r.check(not promos['GHOST'].is_active,'промокод категорії без товарів вимкнено, а не розширено на весь кошик')
 r.check(promos['ALL'].is_active and promos['ALL'].brand_ids in ('[]',[]),'загальний промокод без змін')
 r.check(conn.scalar(text('SELECT COUNT(*) FROM categories'))==2,'старі таблиці категорій не видалено: відкат без втрат')
raise SystemExit(bool(r.done()))
