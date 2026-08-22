from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"]


def test_unhandled_exception_does_not_leak_internals() -> None:
    """A crash must not echo exception text to the caller.

    Exception messages routinely embed connection strings, file paths, and SQL
    fragments. This asserts the secret in the raised error never appears in the
    response body.
    """
    settings = Settings(environment="local", log_level="CRITICAL")
    app: FastAPI = create_app(settings)

    async def boom() -> None:
        raise RuntimeError("postgresql://user:hunter2@db.internal:5432/secrets")

    app.add_api_route("/boom", boom, methods=["GET"])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.text
    assert "hunter2" not in body
    assert "db.internal" not in body
    assert response.json()["error"]["code"] == "internal_error"
    assert response.json()["error"]["request_id"]


def test_validation_error_uses_error_envelope(client: TestClient) -> None:
    """Pydantic's message describes only what the client sent, so it is safe
    to return; the shape still matches every other error."""
    settings = Settings(environment="local", log_level="CRITICAL")
    app: FastAPI = create_app(settings)

    async def needs_int(count: int) -> dict[str, int]:
        return {"count": count}

    app.add_api_route("/needs-int", needs_int, methods=["GET"])

    client_ = TestClient(app)
    response = client_.get("/needs-int", params={"count": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "count" in error["message"]
    assert error["request_id"]
