"""Application settings, loaded from the environment.

Settings are read once and cached. Anything that varies between local, staging,
and production belongs here rather than being read from `os.environ` at the call
site, so the full configuration surface is visible in one place and typo'd
variable names fail at startup instead of at 3am.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/app/config.py -> app -> src -> api -> apps -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[4]

Environment = Literal["local", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Absolute, so host-side tools (alembic, pytest) find the same file
        # whatever directory they are invoked from. A relative ".env" resolves
        # against the working directory and silently finds nothing when run
        # from apps/api. Missing files are ignored, which is what containers
        # want — there Compose injects the variables directly.
        env_file=(_REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        # The .env file is shared with Compose and carries variables this
        # process has no interest in (POSTGRES_*, MINIO_*). Ignore them rather
        # than failing to start.
        extra="ignore",
    )

    environment: Environment = "local"
    log_level: str = "INFO"

    # Three connection strings, one per database role (see ADR-0003).
    #
    # `database_url` is what request handlers use: the `ai_app` role, which is
    # not a table owner, has no BYPASSRLS, and sees only its own tenant's
    # non-deleted rows.
    #
    # `worker_database_url` is `ai_worker`, which may claim jobs across tenants
    # but scopes itself to the job's owner before touching user data.
    #
    # `migration_database_url` is `ai_migrator`, the table owner. It runs DDL
    # only and must use a direct (unpooled) connection — DDL and advisory locks
    # misbehave under transaction pooling.
    database_url: str = "postgresql+psycopg://ai_app:ai_app@localhost:5432/ai_interviewer"
    worker_database_url: str = ""
    migration_database_url: str = ""

    # Consumed only by `bootstrap-db-roles`, which grants LOGIN to the two
    # runtime roles. Migration 0001 creates them NOLOGIN and without a
    # password, so no credential is ever committed inside a migration.
    db_app_password: SecretStr = SecretStr("")
    db_worker_password: SecretStr = SecretStr("")

    # Statement timeout applied to every application session. An unbounded
    # query holds a connection and a transaction open indefinitely; under load
    # that exhausts the pool long before it surfaces as a slow endpoint.
    statement_timeout_ms: int = 15_000

    # Browser origins permitted to send credentialed requests. Never "*" —
    # the CORS spec forbids pairing a wildcard origin with credentials, and a
    # reflected-origin allowlist is how CSRF-adjacent bugs get introduced.
    cors_allow_origins: tuple[str, ...] = ("http://localhost:3000",)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def effective_worker_database_url(self) -> str:
        """Falls back to the app URL so local development needs one variable."""
        return self.worker_database_url or self.database_url

    @property
    def effective_migration_database_url(self) -> str:
        return self.migration_database_url or self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor. Tests override by clearing the cache."""
    return Settings()
