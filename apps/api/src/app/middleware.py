"""HTTP middleware."""

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.context import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"

# An inbound request ID is accepted so a trace can span the frontend and the
# API, but it is client-controlled input that ends up in log records. Bounding
# the length and character set stops a caller from injecting newlines (forging
# log entries) or megabyte strings (bloating every line of a log pipeline).
_MAX_REQUEST_ID_LENGTH = 64
_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def _sanitize(candidate: str | None) -> str | None:
    if candidate is None:
        return None
    trimmed = candidate.strip()
    if not trimmed or len(trimmed) > _MAX_REQUEST_ID_LENGTH:
        return None
    if not set(trimmed) <= _ALLOWED:
        return None
    return trimmed


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign every request an ID, expose it in logs and the response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _sanitize(request.headers.get(REQUEST_ID_HEADER)) or uuid.uuid4().hex

        # Deliberately NOT reset in a `finally`. Starlette handles unhandled
        # exceptions in ServerErrorMiddleware, which sits *outside* this
        # middleware — resetting on the way out clears the ID before the 500
        # handler and its log line can read it, which is precisely the request
        # you most need to correlate. Each request runs in its own task with
        # its own context copy, so the value cannot leak between requests.
        request_id_var.set(request_id)

        # Mirrored onto request.state so exception handlers, which receive the
        # Request but may run in a different context, can read it directly.
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
