"""Fast, no-network checks for the ACCORD NICHE public feed and schemas.
Run: cd backend && PYTHONPATH=. python qa/qa_accord_public_catalog.py
"""
import asyncio
import os
import tempfile
from pathlib import Path
from decimal import Decimal
from fastapi import HTTPException
from pydantic import ValidationError
from api.routers.public_catalog import public_product, catalog, detail, site_config, local_product_media_name, photo
from api.schemas import ProductIn, ProductPatch
from shop.entities import Product


def perfume(id=12, brand='CREED', active=True, photo='https://images.example/test.jpg'):
    return Product(id=id, name='Aventus 2 мл', category_id=None, price=Decimal('190.00'),
                   brand=brand, gender='male', volume_ml=2, stock=4,
                   is_active=active, is_featured=True, photo_url=photo, photo_file_id='fileid')

class Repo:
    def __init__(self, items): self.items = items; self.kw = {}
    async def list_products(self, **kw):
        self.kw = kw
        return [p for p in self.items if p.is_active and p.brand.strip()]
    async def count_products(self, **kw):
        return len([p for p in self.items if p.is_active and p.brand.strip()])
    async def get_product(self, id): return next((p for p in self.items if p.id == id), None)

async def run():
    p = perfume()
    out = public_product(p)
    assert out.brand == 'CREED' and out.volume_ml == 2 and out.stock == 4
    assert out.price == Decimal('190') and out.photo_endpoint.endswith('/12/photo')
    assert public_product(perfume(photo='javascript:alert(1)')).photo_url is None
    assert public_product(perfume(photo='http://invalid.example')).photo_url is None
    repo = Repo([p, perfume(13,brand=''), perfume(14,active=False)])
    response = await catalog(limit=100,offset=0,repo=repo)
    assert response.total == 1 and len(response.items) == 1
    assert repo.kw['only_active'] and repo.kw['perfume_only']
    assert (await detail(12,repo)).brand == 'CREED'
    for invalid in (13,14,999):
        try: await detail(invalid,repo)
        except HTTPException as error: assert error.status_code == 404
        else: raise AssertionError('Hidden product exposed: '+str(invalid))
    os.environ.pop('ACCORD_MINIAPP_URL',None)
    os.environ.pop('NAMED_MINIAPP_URL',None)
    info=await site_config()
    assert info['miniapp_url'] == '', info
    from shop.config import settings
    previous_token = settings.bot_token
    settings.bot_token = ''
    os.environ['ACCORD_MINIAPP_URL']='https://t.me/accordbot/accordapp'
    assert (await site_config())['miniapp_url'] == '', 'No bot token must not enable checkout'
    settings.bot_token = '123456:validlookingtesttoken'
    assert (await site_config())['miniapp_url'] == 'https://t.me/accordbot/accordapp'
    settings.bot_token = previous_token
    del os.environ['ACCORD_MINIAPP_URL']
    assert local_product_media_name('/media/perfume-abcd1234.jpg') == 'perfume-abcd1234.jpg'
    assert not local_product_media_name('/media/../../private.jpg')
    assert not local_product_media_name('https://elsewhere.example/media/a.png')
    hosted=public_product(perfume(photo='/media/perfume-abcd1234.jpg'))
    assert hosted.photo_url is None and hosted.photo_endpoint == '/api/public/catalog/12/photo' 
    from shop import paths
    from fastapi.responses import FileResponse
    with tempfile.TemporaryDirectory() as directory:
        previous_root = paths.DATA_ROOT
        paths.DATA_ROOT = Path(directory)
        try:
            media = paths.media_dir()
            (media/'perfume-abcd1234.jpg').write_bytes(b'\xff\xd8\xff\xd9')
            local_repo = Repo([perfume(photo='/media/perfume-abcd1234.jpg')])
            reply = await photo(12,local_repo)
            assert isinstance(reply, FileResponse) and reply.status_code == 200
            assert reply.media_type == 'image/jpeg'
        finally:
            paths.DATA_ROOT = previous_root
    ProductIn(name='Aventus',brand='CREED',gender='male',volume_ml=2,price='190',stock=4)
    for field in ('brand','gender','is_featured'):
        try: ProductPatch.model_validate({field: None})
        except ValidationError: pass
        else: raise AssertionError('Nullable field: '+field)
    print('ACCORD_PUBLIC_CATALOG: optional Telegram + catalog + local media checks passed')

if __name__ == '__main__': asyncio.run(run())
