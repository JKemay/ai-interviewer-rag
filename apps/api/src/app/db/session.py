"""Database engines and owner-scoped sessions.

Every session that touches user data must run inside a transaction that has
declared which owner it acts for. This module is the only place that opens
sessions, so "did we remember to scope this query?" is answered once, here,
rather than at every call site.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# `SET LOCAL app.owner_id = :value` is not valid SQL — the SET command does not
# accept bind parameters, so using it would mean interpolating a value into a
# statement string. `set_config(name, value, is_local => true)` is the function
# form: identical effect, but the value travels as a bound parameter and cannot
# alter the statement.
_SET_OWNER = text("SELECT set_config('app.owner_id', :owner_id, true)")
_SET_STATEMENT_TIMEOUT = text("SELECT set_config('statement_timeout', :ms, true)")


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        url,
        echo=echo,
        # Verifies a pooled connection is alive before handing it out. Without
        # it, the first request after a database restart or an idle-timeout
        # reaping fails with a stale-connection error.
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def owner_scoped_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    owner_id: uuid.UUID,
    *,
    statement_timeout_ms: int = 15_000,
) -> AsyncGenerator[AsyncSession]:
    """Open a transaction bound to a single owner.

    Both settings are transaction-local (`is_local => true`), which is what
    makes this safe behind a transaction pooler: they are discarded at COMMIT
    or ROLLBACK and cannot leak into whichever request borrows the connection
    next.

    The transaction commits on clean exit and rolls back on any exception.
    """
    async with sessionmaker() as session, session.begin():
        await session.execute(_SET_STATEMENT_TIMEOUT, {"ms": str(statement_timeout_ms)})
        await session.execute(_SET_OWNER, {"owner_id": str(owner_id)})
        yield session


@asynccontextmanager
async def unscoped_session(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    statement_timeout_ms: int = 15_000,
) -> AsyncGenerator[AsyncSession]:
    """Open a transaction with **no** owner set.

    Deliberately blunt name: this is not a convenience, it is the documented
    exception from ADR-0003. Exactly two callers are legitimate — the worker
    claiming a job from the global queue, and the two authentication lookups
    that run before an owner is known.

    It is not a hole. `app.owner_id` is unset, so `app_current_owner()` returns
    NULL and every owner-scoped policy evaluates to NULL rather than true: a
    query issued here against user data returns **zero rows**, not all of them.
    The only rows reachable are those whose policy does not reference the owner
    at all, which is the `job` table for the worker role.
    """
    async with sessionmaker() as session, session.begin():
        await session.execute(_SET_STATEMENT_TIMEOUT, {"ms": str(statement_timeout_ms)})
        yield session
