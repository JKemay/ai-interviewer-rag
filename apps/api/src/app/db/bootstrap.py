"""Grant LOGIN and a password to the two runtime database roles.

Migration 0001 creates `ai_app` and `ai_worker` as NOLOGIN with no password, so
that no credential is ever written into a file that gets committed. This command
supplies the credentials afterwards, reading them from the environment.

Run it after `alembic upgrade head` on a fresh database, and again whenever a
password is rotated. It is idempotent.

On a managed provider where roles are created through a console or API, this is
unnecessary — provision the roles there instead.
"""

import sys

import psycopg
from psycopg import sql

from app.config import Settings, get_settings

# The SQLAlchemy dialect prefix is not understood by libpq.
_DIALECT_PREFIX = "postgresql+psycopg://"


def to_libpq_dsn(url: str) -> str:
    return url.replace(_DIALECT_PREFIX, "postgresql://", 1)


def bootstrap_roles(settings: Settings) -> list[str]:
    """Return the roles that were configured."""
    pairs = (
        ("ai_app", settings.db_app_password.get_secret_value()),
        ("ai_worker", settings.db_worker_password.get_secret_value()),
    )
    missing = [role for role, password in pairs if not password]
    if missing:
        raise SystemExit(
            f"No password configured for: {', '.join(missing)}. "
            "Set DB_APP_PASSWORD and DB_WORKER_PASSWORD."
        )

    configured: list[str] = []
    dsn = to_libpq_dsn(settings.effective_migration_database_url)
    with psycopg.connect(dsn, autocommit=True) as conn:
        for role, password in pairs:
            # psycopg's sql composition quotes the identifier and escapes the
            # literal. Neither can be a bind parameter in ALTER ROLE, and
            # f-string interpolation of a password into DDL would both break on
            # a quote character and risk injection.
            conn.execute(
                sql.SQL("ALTER ROLE {role} WITH LOGIN PASSWORD {password}").format(
                    role=sql.Identifier(role),
                    password=sql.Literal(password),
                )
            )
            configured.append(role)
    return configured


def main() -> None:
    configured = bootstrap_roles(get_settings())
    # Names only. Never echo the values.
    print(f"configured login for: {', '.join(configured)}", file=sys.stderr)


if __name__ == "__main__":
    main()
