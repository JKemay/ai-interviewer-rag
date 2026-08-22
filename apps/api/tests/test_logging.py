"""Tests for structured logging.

The logger is a security boundary as much as an observability one: it is the
component that must never emit resume text or interview answers. These tests
pin its contract.
"""

import json
import logging

from app.context import request_id_var
from app.logging import JsonFormatter


def _record(**kwargs: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something_happened",
        args=(),
        exc_info=None,
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def test_output_is_valid_json() -> None:
    payload = json.loads(JsonFormatter().format(_record()))
    assert payload["message"] == "something_happened"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert "timestamp" in payload


def test_request_id_is_included_when_set() -> None:
    token = request_id_var.set("req-123")
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-123"


def test_request_id_is_omitted_when_unset() -> None:
    token = request_id_var.set("")
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_var.reset(token)
    assert "request_id" not in payload


def test_extra_fields_are_merged() -> None:
    payload = json.loads(JsonFormatter().format(_record(document_id="doc-9")))
    assert payload["document_id"] == "doc-9"


def test_non_serializable_values_do_not_crash_logging() -> None:
    """A logger that raises while formatting takes the request down with it."""

    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    payload = json.loads(JsonFormatter().format(_record(thing=Opaque())))
    assert payload["thing"] == "<opaque>"


def test_exception_is_rendered_into_the_record() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]
