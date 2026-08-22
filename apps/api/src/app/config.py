"""Application settings, loaded from the environment.

Settings are read once and cached. Anything that varies between local, staging,
and production belongs here rather than being read from `os.environ` at the call
site, so the full configuration surface is visible in one place and typo'd
variable names fail at startup instead of at 3am.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # The .env file is shared with Compose and carries variables this
        # process has no interest in (POSTGRES_*, MINIO_*). Ignore them rather
        # than failing to start.
        extra="ignore",
    )

    environment: Environment = "local"
    log_level: str = "INFO"

    # Browser origins permitted to send credentialed requests. Never "*" —
    # the CORS spec forbids pairing a wildcard origin with credentials, and a
    # reflected-origin allowlist is how CSRF-adjacent bugs get introduced.
    cors_allow_origins: tuple[str, ...] = ("http://localhost:3000",)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor. Tests override by clearing the cache."""
    return Settings()
