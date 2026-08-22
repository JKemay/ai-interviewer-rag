"""Guards on the database roles themselves.

Row-Level Security can be switched off from a distance: grant BYPASSRLS, make
the application role a table owner, or add a table without FORCE, and every
isolation test above still passes while the protection is gone.

These tests assert the *conditions* that make RLS effective, so a future
migration cannot quietly remove them.
"""

from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import unscoped_session

RUNTIME_ROLES = ("ai_app", "ai_worker")


async def test_runtime_roles_lack_dangerous_attributes(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """BYPASSRLS or SUPERUSER on a runtime role disables every policy at once."""
    async with unscoped_session(migrator_sessions) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                    "FROM pg_roles WHERE rolname = ANY(:names)"
                ),
                {"names": list(RUNTIME_ROLES)},
            )
        ).all()

    found = {row[0] for row in rows}
    assert found == set(RUNTIME_ROLES), f"missing roles: {set(RUNTIME_ROLES) - found}"

    for name, is_super, bypass, createdb, createrole in rows:
        assert not is_super, f"{name} is SUPERUSER"
        assert not bypass, f"{name} has BYPASSRLS — every policy is inert for it"
        assert not createdb, f"{name} can CREATE DATABASE"
        assert not createrole, f"{name} can CREATE ROLE"


async def test_runtime_roles_do_not_own_tables(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A table owner is exempt from its own policies unless FORCE is set.

    Ownership is therefore a second, quieter way to disable RLS.
    """
    async with unscoped_session(migrator_sessions) as session:
        owned = (
            await session.execute(
                text(
                    "SELECT tablename, tableowner FROM pg_tables "
                    "WHERE schemaname = 'public' AND tableowner = ANY(:names)"
                ),
                {"names": list(RUNTIME_ROLES)},
            )
        ).all()
    assert owned == [], f"runtime roles own tables: {owned}"


async def test_every_public_table_has_rls_enabled_and_forced(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Catches the realistic mistake: a new table shipped without policies.

    `alembic_version` is excluded — it holds no user data and is written by the
    migration role only.
    """
    async with unscoped_session(migrator_sessions) as session:
        rows = (
            await session.execute(
                text("""
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                  AND c.relname <> 'alembic_version'
                ORDER BY c.relname
                """)
            )
        ).all()

    assert rows, "no tables found — did migrations run?"
    for name, enabled, forced in rows:
        assert enabled, f"{name} does not have ROW LEVEL SECURITY enabled"
        assert forced, (
            f"{name} is not FORCE ROW LEVEL SECURITY: an application connecting "
            f"as the table owner would bypass every policy silently"
        )


async def test_every_secured_table_has_a_policy_for_each_runtime_role(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """RLS with no policy denies everything.

    A table given FORCE but only one role's policy is invisible to the other —
    which surfaces as a confusing empty result, often much later.
    """
    async with unscoped_session(migrator_sessions) as session:
        rows = (
            await session.execute(
                text("""
                SELECT c.relname, p.polname, r.rolname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_policy p ON p.polrelid = c.oid
                LEFT JOIN pg_roles r ON r.oid = ANY(p.polroles)
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                  AND c.relname <> 'alembic_version'
                """)
            )
        ).all()

    by_table: dict[str, set[str]] = {}
    for table, _policy, role in rows:
        by_table.setdefault(table, set())
        if role:
            by_table[table].add(role)

    for table, roles in by_table.items():
        missing = set(RUNTIME_ROLES) - roles
        assert not missing, f"{table} has no policy for: {', '.join(sorted(missing))}"


async def test_security_definer_functions_pin_search_path(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A SECURITY DEFINER function without a pinned search_path is escalation.

    A caller able to create objects in an earlier schema can shadow a table or
    operator the body references and have it execute with the definer's
    privileges.
    """
    async with unscoped_session(migrator_sessions) as session:
        rows = (
            await session.execute(
                text("""
                SELECT p.proname, p.proconfig
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.prosecdef
                ORDER BY p.proname
                """)
            )
        ).all()

    assert rows, "expected SECURITY DEFINER functions for the auth lookups"
    for name, config in rows:
        # proconfig is a text[] of "key=value" strings, or NULL when the
        # function sets nothing.
        raw: object = config
        entries: list[str] = []
        if isinstance(raw, list):
            typed_raw = cast(list[object], raw)
            entries = [str(value) for value in typed_raw]
        assert any(e.startswith("search_path=") for e in entries), (
            f"{name} is SECURITY DEFINER without a pinned search_path"
        )


async def test_security_definer_functions_are_not_executable_by_public(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Functions are executable by PUBLIC by default.

    A SECURITY DEFINER function left open to PUBLIC runs with the definer's
    privileges for anyone who can reach the database, which is the whole point
    of revoking it.

    In a Postgres ACL each entry is `grantee=privileges/grantor`, and PUBLIC is
    written as an entry with an **empty** grantee — `=X/owner`. The owner's own
    entry is expected and not a finding.
    """
    async with unscoped_session(migrator_sessions) as session:
        rows = (
            await session.execute(
                text("""
                SELECT p.proname, p.proacl::text, pg_get_userbyid(p.proowner)
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public' AND p.prosecdef
                """)
            )
        ).all()

    assert rows, "expected SECURITY DEFINER functions for the auth lookups"
    for name, acl, owner in rows:
        assert acl is not None, f"{name} still carries the default PUBLIC EXECUTE"
        entries = [e for e in acl.strip("{}").split(",") if e]
        grantees = {e.split("=", 1)[0] for e in entries}

        assert "" not in grantees, f"{name} is executable by PUBLIC: {acl}"
        assert grantees <= {owner, "ai_app"}, (
            f"{name} grants EXECUTE beyond the owner and ai_app: {sorted(grantees)}"
        )
