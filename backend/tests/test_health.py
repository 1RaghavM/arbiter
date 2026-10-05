from fastapi.testclient import TestClient

from app.main import app


def test_health_without_database_or_provider_keys():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
