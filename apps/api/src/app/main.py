"""Application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.errors import register_exception_handlers
from app.logging import configure_logging, get_logger
from app.middleware import REQUEST_ID_HEADER, RequestIDMiddleware
from app.routes import health

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    logger.info("startup", extra={"environment": settings.environment})
    yield
    logger.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    A factory rather than a module-level `app = FastAPI()` so tests can build an
    instance with overridden settings, and so importing this module has no side
    effects.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AI Interviewer API",
        version="0.1.0",
        lifespan=lifespan,
        # Interactive docs are useful locally and are attack surface in
        # production, where the OpenAPI schema is published to the frontend
        # build instead of served at runtime.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_credentials=True,  # the session cookie must be sent cross-origin
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER, "X-CSRF-Token"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
