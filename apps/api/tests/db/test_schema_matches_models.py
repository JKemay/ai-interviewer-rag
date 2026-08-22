"""The ORM models and the migrations must describe the same database.

Alembic migrations and SQLAlchemy models are two independent descriptions of one
schema. Nothing forces them to agree: a hand-written migration can add a column
the models never learn about, and an edited model produces no error until a
query references a column that does not exist.

This is the database counterpart of the OpenAPI drift check — it fails at
`pytest` time rather than at the first query in production.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import Base
from app.db.models import AppUser, SessionToken
from app.db.session import unscoped_session

# Every table the models declare must exist in the database.
EXPECTED_TABLES = {"app_user", "session_token"}


def test_models_declare_the_expected_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert AppUser.__tablename__ == "app_user"
    assert SessionToken.__tablename__ == "session_token"


async def test_every_model_table_exists_in_the_database(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with unscoped_session(migrator_sessions) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                    )
                )
            )
            .scalars()
            .all()
        )

    actual = {str(name) for name in rows}
    missing = set(Base.metadata.tables) - actual
    extra = actual - set(Base.metadata.tables)

    assert not missing, f"models declare tables the migrations never created: {missing}"
    assert not extra, (
        f"migrations created tables the models do not know about: {extra}. "
        "Add the model, or the ORM cannot query them."
    )


async def test_model_columns_match_the_database(
    migrator_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Column-level drift, which is the common case.

    A migration adding a column without a matching model attribute is silent
    until something needs it.
    """

    def collect(connection: Connection) -> dict[str, set[str]]:
        inspector = inspect(connection)
        return {
            table: {column["name"] for column in inspector.get_columns(table)}
            for table in Base.metadata.tables
        }

    async with unscoped_session(migrator_sessions) as session:
        connection = await session.connection()
        actual = await connection.run_sync(collect)

    for table_name, table in Base.metadata.tables.items():
        declared = {column.name for column in table.columns}
        found = actual[table_name]
        assert declared == found, (
            f"{table_name} columns differ.\n"
            f"  only in models:   {sorted(declared - found)}\n"
            f"  only in database: {sorted(found - declared)}"
        )
