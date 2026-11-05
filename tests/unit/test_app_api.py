from fastapi.testclient import TestClient

from mtg_price_checker.app.api import create_app


def test_health_and_stores_endpoints() -> None:
    client = TestClient(create_app())

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    stores = client.get("/api/stores")
    assert stores.status_code == 200
    ids = {store["store_id"] for store in stores.json()["stores"]}
    assert "imaginaire" in ids
    assert "hobbiesville" in ids


def test_create_job_rejects_empty_decklist() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/jobs",
        json={
            "stores": ["demo"],
            "min_condition": "NM",
            "decklist": "# nothing",
        },
    )

    assert response.status_code == 400
