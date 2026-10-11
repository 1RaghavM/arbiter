import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db, providers
from app.main import app


@pytest.fixture
def client(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    monkeypatch.setenv("DATABASE_URL", url)
    db.migrate(url)
    with TestClient(app) as client:
        yield client


def test_chat_context_persistence_and_read_endpoints(client):
    messages = [{"role": "user", "content": "My project is called Arbiter."}]
    first = client.post("/api/chat", json={"messages": messages}).json()
    messages.extend(
        [
            {"role": "assistant", "content": first["answer"]},
            {"role": "user", "content": "What did I call my project?"},
        ]
    )
    second = client.post("/api/chat", json={"messages": messages})
    assert second.status_code == 200
    result = second.json()
    assert "Earlier you said: My project is called Arbiter." in result["answer"]
    assert result["status"] == "unverified" and result["mode"] == "mock"
    assert result["analysis"] is None and result["route_decisions"] == []
    stored = client.get(f"/api/runs/{result['run_id']}").json()
    assert stored["messages"] == messages
    assert stored["calls"][0]["status"] == "done"
    assert stored["calls"][0]["provider"] == "mock"
    recent = client.get("/api/runs?limit=1").json()
    assert len(recent) == 1 and "messages" not in recent[0]
    assert client.get("/api/runs?limit=101").status_code == 422
    assert client.get(f"/api/runs/{uuid4()}").status_code == 404
    assert client.get("/api/runs/not-a-uuid").status_code == 422


def test_generation_failure_is_saved(client, monkeypatch):
    def fail(messages):
        raise RuntimeError("private exception text")

    monkeypatch.setattr(providers, "generate_mock", fail)
    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == 503
    assert "private" not in response.text
    stored = client.get(f"/api/runs/{response.json()['run_id']}").json()
    assert stored["status"] == "error"
    assert stored["calls"][0]["error"]["code"] == "generation_failed"


def test_database_failure_after_generation_is_explicit(client, monkeypatch):
    def fail(*args):
        raise psycopg.OperationalError("private database details")

    monkeypatch.setattr(db, "finish_run", fail)
    response = client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "persistence_error"
    assert response.json()["run_id"]
    assert "private" not in response.text


@pytest.mark.parametrize("url", [None, "postgresql://localhost:1/missing"])
def test_missing_database_prevents_generation(monkeypatch, url):
    if url:
        monkeypatch.setenv("DATABASE_URL", url)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    called = False

    def generate(messages):
        nonlocal called
        called = True
        raise AssertionError("Must not generate")

    monkeypatch.setattr(providers, "generate_mock", generate)
    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "test"}],
            },
        )
        assert response.status_code == 503
        assert client.get("/api/health").status_code == 200
    assert not called


def test_invalid_input_before_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        for body in [b"{", b"x" * 160001, b'{"messages": []}']:
            assert client.post("/api/chat", content=body).status_code == 422
