"""A single error envelope for every failure the API returns.

Clients should never have to branch on response shape to find out what went
wrong. Every non-2xx response — validation failure, missing resource, unhandled
crash — has the same body:

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

The `request_id` is the point: a user reports "it broke", quotes the ID, and it
maps to exactly one request in the logs.

Handlers are module-level and registered explicitly rather than defined inline
with decorators, so each one can be unit-tested on its own.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.context import get_request_id
from app.logging import get_logger

logger = get_logger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


def resolve_request_id(request: Request) -> str:
    """request.state first, contextvar second.

    Handlers registered for `Exception` run inside ServerErrorMiddleware, which
    sits outside the middleware that populates the contextvar, so request.state
    is the reliable source on that path.
    """
    state_value: object = getattr(request.state, "request_id", "")
    if isinstance(state_value, str) and state_value:
        return state_value
    return get_request_id()


def error_response(status_code: int, code: str, message: str, request_id: str = "") -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=request_id or get_request_id())
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - guard
        return await handle_unhandled_exception(request, exc)
    code = _STATUS_CODES.get(exc.status_code, "error")
    return error_response(exc.status_code, code, str(exc.detail), resolve_request_id(request))


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - guard
        return await handle_unhandled_exception(request, exc)
    # Pydantic's error list is genuinely useful to a client fixing its request,
    # and it describes only what the client itself sent — no server internals
    # leak through it.
    first: dict[str, Any] | None = next(iter(exc.errors()), None)
    message = "Request validation failed"
    if first is not None:
        location = ".".join(str(part) for part in first.get("loc", ()))
        message = f"{location}: {first.get('msg', 'invalid')}"
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", message)


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    # The exception is logged in full, with traceback, server-side. The client
    # gets a generic message: exception text routinely contains connection
    # strings, file paths, and query fragments, and echoing it to an
    # unauthenticated caller is an information-disclosure bug.
    request_id = resolve_request_id(request)
    logger.exception("unhandled_exception", exc_info=exc, extra={"request_id": request_id})
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred.",
        request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unhandled_exception)
