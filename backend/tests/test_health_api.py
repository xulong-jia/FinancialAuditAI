from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config() -> None:
    response = client.get("/api/v1/config")

    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == "FinancialAuditAI"
    assert body["api_prefix"] == "/api/v1"
