"""Tests for the role bootstrap command."""

import pytest

from app.config import Settings
from app.db.bootstrap import bootstrap_roles, to_libpq_dsn


def test_dsn_strips_the_sqlalchemy_dialect() -> None:
    """libpq does not understand SQLAlchemy's `+driver` suffix."""
    assert to_libpq_dsn("postgresql+psycopg://u:p@host:5432/db") == "postgresql://u:p@host:5432/db"


def test_dsn_leaves_a_plain_url_alone() -> None:
    assert to_libpq_dsn("postgresql://u:p@host/db") == "postgresql://u:p@host/db"


def test_missing_passwords_fail_before_connecting() -> None:
    """Fail with a readable message rather than setting an empty password.

    `ALTER ROLE ... PASSWORD ''` succeeds in Postgres and produces a role that
    cannot authenticate, which is a confusing failure much later.
    """
    settings = Settings(
        environment="local",
        db_app_password="",  # type: ignore[arg-type]
        db_worker_password="",  # type: ignore[arg-type]
    )
    with pytest.raises(SystemExit, match="DB_APP_PASSWORD"):
        bootstrap_roles(settings)
