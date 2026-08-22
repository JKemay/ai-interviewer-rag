"""Request-scoped context.

A context variable rather than a parameter threaded through every function:
logging and error handling need the request ID at arbitrary depth, and passing
it explicitly through layers that otherwise don't care about it is noise.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return request_id_var.get()
