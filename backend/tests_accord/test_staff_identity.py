"""Dashboard customer identity reconciliation, with no writable database."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from api.routers.customers import customer_identity

class Rows:
    def all(self): return [4, 7]

class Session:
    async def scalar(self, statement):
        return SimpleNamespace(id=1, user_id=4, google_sub='sub', email='customer@example.invalid',
                               verified_phone=None, linked_telegram_user_id=9)
    async def scalars(self, statement): return Rows()

class Repo:
    s = Session()
    async def get_user(self, user_id):
        return SimpleNamespace(id=user_id) if user_id == 4 else None

@pytest.mark.asyncio
async def test_staff_linked_identities_show_proven_users_without_google_sub():
    data = await customer_identity(4, repo=Repo())
    assert data['linked'] and data['google_connected'] and data['telegram_connected']
    assert data['user_ids'] == [4, 7, 9]
    assert 'sub' not in data

@pytest.mark.asyncio
async def test_staff_identity_requires_existing_customer():
    with pytest.raises(HTTPException) as error:
        await customer_identity(999, repo=Repo())
    assert error.value.status_code == 404
