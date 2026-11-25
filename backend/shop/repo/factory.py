"""Доступ до бази.

Реалізація одна — Postgres через SQLAlchemy. Раніше тут був вибір між SQL
і Firestore; Firestore прибрано разом із serverless-розгортанням, бо на
власному сервері зовнішня база — це ще один сервіс, який може відмовити
незалежно від магазину, і ще один рахунок.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from shop.repo.base import Repository


@asynccontextmanager
async def open_repo() -> AsyncIterator[Repository]:
    from shop.db import SessionMaker
    from shop.repo.sql import SqlRepository

    from shop.services import test_mode
    sandbox = test_mode.active()
    # Website requests of the system administrator's test mode go to the
    # sandbox database; everything else (and every other visitor) uses the shop's.
    maker = test_mode.session_maker(sandbox) if sandbox else SessionMaker
    async with maker() as session:
        yield SqlRepository(session)


async def get_repo() -> AsyncIterator[Repository]:
    """Залежність для FastAPI."""
    async with open_repo() as repo:
        yield repo
