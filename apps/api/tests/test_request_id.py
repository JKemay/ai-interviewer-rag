from fastapi.testclient import TestClient

from app.middleware import REQUEST_ID_HEADER


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.headers[REQUEST_ID_HEADER]


def test_valid_inbound_request_id_is_preserved(client: TestClient) -> None:
    """Lets a trace span the frontend and the API."""
    response = client.get("/healthz", headers={REQUEST_ID_HEADER: "trace-abc_123"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-abc_123"


def test_malicious_request_ids_are_rejected(client: TestClient) -> None:
    """The header reaches log records, so it is untrusted input.

    A newline would let a caller forge log entries; an oversized value would
    bloat every line in the pipeline. Both are replaced with a generated ID
    rather than echoed.
    """
    hostile = {
        "newline_injection": 'abc\nlevel="ERROR" message="forged"',
        "carriage_return": "abc\r\ninjected",
        "too_long": "a" * 200,
        "empty": "   ",
        "control_chars": "abc\x00def",
    }
    for name, value in hostile.items():
        response = client.get("/healthz", headers={REQUEST_ID_HEADER: value})
        returned = response.headers[REQUEST_ID_HEADER]
        assert returned != value, f"{name} was echoed back verbatim"
        assert "\n" not in returned and "\r" not in returned
        assert len(returned) <= 64
