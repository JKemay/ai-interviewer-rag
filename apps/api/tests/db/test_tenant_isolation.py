"""Row-Level Security must hold even when application code is wrong.

Every test here is a *negative* test: it asserts that something an attacker (or
a bug) would want to happen does not. Positive tests confirm the feature works;
these confirm the guarantee survives the feature being used incorrectly.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import owner_scoped_session, unscoped_session


async def test_unscoped_query_returns_nothing(
    app_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The fail-closed property.

    With `app.owner_id` unset, `app_current_owner()` is NULL and every policy
    predicate evaluates to NULL rather than true. A query that forgot to scope
    itself therefore returns zero rows — a visibly broken feature in
    development, rather than a silent cross-tenant leak in production.
    """
    async with unscoped_session(app_sessions) as session:
        count = (await session.execute(text("SELECT count(*) FROM app_user"))).scalar_one()
    assert count == 0


async def test_owner_sees_only_itself(
    app_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    alice, _bob = two_users
    async with owner_scoped_session(app_sessions, alice) as session:
        rows = (await session.execute(text("SELECT id FROM app_user"))).scalars().all()
    assert [uuid.UUID(str(r)) for r in rows] == [alice]


async def test_owner_cannot_read_another_tenant(
    app_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Even naming the other user's primary key directly returns nothing."""
    alice, bob = two_users
    async with owner_scoped_session(app_sessions, bob) as session:
        row = (
            await session.execute(
                text("SELECT id FROM app_user WHERE id = :target"), {"target": alice}
            )
        ).first()
    assert row is None


async def test_owner_cannot_write_for_another_tenant(
    app_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """`WITH CHECK` governs writes; `USING` alone would not stop this.

    Without a WITH CHECK clause a caller can insert rows *belonging to someone
    else* — invisible to them afterwards, but present, and attributed to a
    victim.
    """
    alice, bob = two_users
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with owner_scoped_session(app_sessions, bob) as session:
            await session.execute(
                text(
                    "INSERT INTO session_token (owner_id, token_hash, expires_at) "
                    "VALUES (:owner, '\\x00'::bytea, now() + interval '1 day')"
                ),
                {"owner": alice},
            )


async def test_owner_cannot_escalate_by_changing_the_setting(
    app_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """`app.owner_id` is set by our own code, never from user input.

    This test documents the boundary: whoever controls the setting controls the
    tenant. It is why the value comes from a validated session lookup and never
    from a header, query parameter, or request body.
    """
    alice, bob = two_users
    async with owner_scoped_session(app_sessions, bob) as session:
        await session.execute(
            text("SELECT set_config('app.owner_id', :v, true)"), {"v": str(alice)}
        )
        rows = (await session.execute(text("SELECT id FROM app_user"))).scalars().all()
    assert [uuid.UUID(str(r)) for r in rows] == [alice]


async def test_soft_deleted_rows_are_invisible_to_the_application(
    app_sessions: async_sessionmaker[AsyncSession],
    migrator_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The predicate lives in the policy, not only in repository queries.

    A hand-written query that forgets `deleted_at IS NULL` then returns too few
    rows rather than resurfacing deleted PII.
    """
    alice, _bob = two_users
    async with migrator_sessions() as session, session.begin():
        await session.execute(
            text("UPDATE app_user SET deleted_at = now() WHERE id = :id"), {"id": alice}
        )

    async with owner_scoped_session(app_sessions, alice) as session:
        count = (await session.execute(text("SELECT count(*) FROM app_user"))).scalar_one()
    assert count == 0


async def test_worker_still_sees_soft_deleted_rows(
    worker_sessions: async_sessionmaker[AsyncSession],
    migrator_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """Otherwise nothing could ever purge them.

    The worker keeps tenant scoping; it only loses the soft-delete filter.
    """
    alice, _bob = two_users
    async with migrator_sessions() as session, session.begin():
        await session.execute(
            text("UPDATE app_user SET deleted_at = now() WHERE id = :id"), {"id": alice}
        )

    async with owner_scoped_session(worker_sessions, alice) as session:
        count = (await session.execute(text("SELECT count(*) FROM app_user"))).scalar_one()
    assert count == 1


async def test_worker_is_still_tenant_scoped(
    worker_sessions: async_sessionmaker[AsyncSession],
    two_users: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """The worker's extra capability is soft-delete visibility and the queue —
    not cross-tenant access to user data."""
    alice, bob = two_users
    async with owner_scoped_session(worker_sessions, bob) as session:
        row = (
            await session.execute(
                text("SELECT id FROM app_user WHERE id = :target"), {"target": alice}
            )
        ).first()
    assert row is None
