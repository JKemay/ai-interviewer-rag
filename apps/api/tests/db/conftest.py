"""Fixtures for tests that need a real database.

These run against Postgres with pgvector — the same image production uses — not
an in-memory substitute. SQLite has neither RLS, nor pgvector, nor tsvector, so
testing against it would verify a system we do not ship.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.session import create_engine, create_sessionmaker


@pytest.fixture
def db_settings() -> Settings:
    return Settings()


def _maker(url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_engine(url)
    return engine, create_sessionmaker(engine)


@pytest.fixture
async def app_sessions(
    db_settings: Settings,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Sessions as `ai_app`: tenant-scoped, no BYPASSRLS, not a table owner."""
    engine, maker = _maker(db_settings.database_url)
    yield maker
    await engine.dispose()


@pytest.fixture
async def worker_sessions(
    db_settings: Settings,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Sessions as `ai_worker`: sees soft-deleted rows, cross-tenant on `job`."""
    engine, maker = _maker(db_settings.effective_worker_database_url)
    yield maker
    await engine.dispose()


@pytest.fixture
async def migrator_sessions(
    db_settings: Settings,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Sessions as the table owner. Used only to arrange test data."""
    engine, maker = _maker(db_settings.effective_migration_database_url)
    yield maker
    await engine.dispose()


@pytest.fixture
async def two_users(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[tuple[uuid.UUID, uuid.UUID]]:
    """Two unrelated users, removed afterwards.

    Emails are randomised so parallel runs cannot collide on the unique index.
    """
    alice_email = f"alice-{uuid.uuid4().hex}@example.test"
    bob_email = f"bob-{uuid.uuid4().hex}@example.test"

    async with migrator_sessions() as session, session.begin():
        alice = (
            await session.execute(
                text("SELECT auth_register_user(:email, 'not-a-real-hash')"),
                {"email": alice_email},
            )
        ).scalar_one()
        bob = (
            await session.execute(
                text("SELECT auth_register_user(:email, 'not-a-real-hash')"),
                {"email": bob_email},
            )
        ).scalar_one()

    yield uuid.UUID(str(alice)), uuid.UUID(str(bob))

    async with migrator_sessions() as session, session.begin():
        await session.execute(
            text("DELETE FROM app_user WHERE email IN (:a, :b)"),
            {"a": alice_email, "b": bob_email},
        )
