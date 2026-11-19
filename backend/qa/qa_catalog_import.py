"""Import round trip, external articles and photo parity with neutral goods."""
from qa_paths import qa_db_path, qa_db_url
from io import BytesIO
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
import asyncio
from openpyxl import Workbook
from fastapi.testclient import TestClient
from qa_common import boot,init_data,Report
app,Session,_=boot(qa_db_path('catalog_import_validation.db')); c=TestClient(app); r=Report('CATALOG IMPORT')
A={'Authorization':'Bearer '+c.post('/api/auth/login',json={'login':'admin','password':'secret'}).json()['access_token']}
H=init_data(12342); c.get('/api/shop/config',headers=H); c.post('/api/shop/age-confirm',headers=H)
def req(method,path,data=None):
 response=c.request(method,'/api/catalog'+path,json=data,headers=A)
 assert response.status_code<300,(response.status_code,response.text)
 return response.json() if response.content else None
def xlsx(rows):
 wb=Workbook(); ws=wb.active
 for row in rows: ws.append(row)
 out=BytesIO(); wb.save(out); return out.getvalue()
def finished(response):
 # A02: a new import is a durable job (202); a repeat returns its receipt (200).
 assert response.status_code in (200,202),response.text
 data=response.json()
 if response.status_code==202:
  job=c.get('/api/catalog/product-transfer/import/'+data['job_id'],headers=A).json()
  assert job['status']=='done',job
  return {**job['result'],'replayed':False}
 return data
def upload(rows,prices='both',force=False):
 data={'mode':'upsert','prices':prices,**({'force':'true'} if force else {})}
 return finished(c.post('/api/catalog/product-transfer/import',headers=A,files={'file':('goods.xlsx',xlsx(rows),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data=data))
sheet=[['Товар/Послуга','SKU','Категорія','Ціна','Ціна зі знижкою','Новинка','Активний','Залишок'],['Нейтральний аксесуар','зовнішній артикул','Група імпорту',100,80,'Так','Так',7]]
result=upload(sheet); item=next(p for p in req('GET','/products') if p['name']=='Нейтральний аксесуар')
r.check(result['created']==1 and not result['errors'] and item['sku'].startswith('ELF-') and item['external_sku']=='зовнішній артикул','імпорт генерує системний SKU та зберігає зовнішній')
r.check(item['brand_id'] is None and item['is_new'] and item['is_sale'] and item['stock']==7,'файл SalesDrive без колонки «Бренд» не вигадує бренду й зберігає позначки')
result=upload(sheet)
r.check(result['replayed'] and len([p for p in req('GET','/products') if p['name']=='Нейтральний аксесуар'])==1,'повтор того самого файла повертає квитанцію без повторного застосування')
result=upload(sheet,force=True)
r.check(not result['replayed'] and result['created']==0 and result['updated']==1 and req('GET',f"/products/{item['id']}")['sku']==item['sku'],'повторний імпорт не створює дубль і не змінює SKU')
result=upload([sheet[0],['Без ціни','NO-PRICE',None,10,None,'Так','Так',1]],prices='none')
unpriced=next(p for p in req('GET','/products') if p['name']=='Без ціни')
r.check(result['created']==1 and not unpriced['is_active'],'новий товар без імпорту ціни залишається прихованим')
root=req('POST','/brands',{'name':'Колекції'})
only_sub=req('POST','/products',{'name':'Сумка','brand_id':root['id'],'price':'129.90','stock':5})
inactive_sale=req('POST','/products',{'name':'Без активної акції','price':'200','old_price':'150','is_sale':False})
export=c.get('/api/catalog/product-transfer/export',headers=A)
result=finished(c.post('/api/catalog/product-transfer/import',headers=A,files={'file':('own.xlsx',export.content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data={'mode':'upsert','prices':'both'}))
r.check(result['created']==0 and not result['errors'],'власний експорт повертається без дублювання')
after=req('GET',f"/products/{only_sub['id']}")
r.check(after['brand_id']==root['id'] and after['brand']=='Колекції' and after['price']=='129.90','XLSX зберігає бренд і точну ціну')
result=upload([['Товар','SKU','Бренд','Ціна'],['Новий аромат','BRAND-NEW-001','  Xerjoff ','99']])
fresh=next(p for p in req('GET','/products') if p['name']=='Новий аромат')
brand=next(x for x in req('GET','/brands') if x['name']=='Xerjoff')
r.check(result['created']==1 and fresh['brand_id']==brand['id'] and fresh['brand']=='Xerjoff','колонка «Бренд» створює бренд і привʼязує товар')
unchanged=req('GET',f"/products/{inactive_sale['id']}")
r.check(unchanged['price']=='200.00' and unchanged['old_price']=='150.00' and not unchanged['is_sale'],'XLSX не підміняє поточну ціну старою для вимкненої акції')
result=upload([['Товар','SKU','Субкатегорія','Ціна','Зовнішній артикул'],['Новий аксесуар','EXPORT-COPY-001',None,'73.50','ORIGIN-COPY']])
copied=next(p for p in req('GET','/products') if p['name']=='Новий аксесуар')
r.check(result['created']==1 and copied['sku']!='EXPORT-COPY-001' and copied['external_sku']=='ORIGIN-COPY','перенесення власного XLSX зберігає зовнішній артикул і генерує системний')
from shop.formatting import money
r.check(money(Decimal('129.90'))=='129,90' and money(Decimal('100'))=='100,00','грошовий формат зберігає копійки')
r.check(c.post('/api/catalog/brands',json={'name':'   '},headers=A).status_code==422,'порожня назва бренду відхиляється')
async def photo_setup():
 from shop.repo.sql import SqlRepository
 async with Session() as session: await SqlRepository(session).update_product(item['id'],{'photo_file_id':'sample-photo','photo_url':None})
asyncio.run(photo_setup())
class PhotoBot:
 async def get_file(self,fid): return SimpleNamespace(file_path='photo.jpg')
 async def download_file(self,path): return BytesIO(b'\xff\xd8sample\xff\xd9')
with patch('api.routers.orders._bot',return_value=PhotoBot()):
 private=c.get(f"/api/catalog/products/{item['id']}/photo",headers=A); public=c.get(f"/api/shop/products/{item['id']}/photo",headers=H)
 r.check(private.status_code==200 and private.content==public.content,'dashboard і вітрина отримують те саме Telegram фото через проксі')
r.check(c.get(f"/api/catalog/products/{item['id']}/photo").status_code==401,'фото dashboard потребує авторизації')
raise SystemExit(bool(r.done()))
