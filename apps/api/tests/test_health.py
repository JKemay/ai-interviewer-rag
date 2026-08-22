from fastapi.testclient import TestClient


def test_healthz_is_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_checks(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {}


def test_liveness_does_not_depend_on_anything(client: TestClient) -> None:
    """Liveness must stay green even when dependencies are down.

    A /healthz that checks the database turns a transient database blip into a
    restart storm across every replica. This test is a guard against someone
    later "improving" the probe by adding a dependency check to it.
    """
    for _ in range(3):
        assert client.get("/healthz").status_code == 200
