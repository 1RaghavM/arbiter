import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import db, jobs
from app.config import Settings, load_settings
from app.main import app
from app.schemas import ChatResult

HEADERS = {"X-Arbiter-Benchmark": "start"}


@pytest.fixture
def client(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for real PostgreSQL job tests")
    db.migrate(url)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("CHAT_MODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-key")
    monkeypatch.setenv("BENCHMARK_BUDGET_USD", "1.00")
    monkeypatch.setenv("REQUEST_BUDGET_USD", "0.25")
    with TestClient(app) as client:
        yield client


def test_live_is_the_default(monkeypatch):
    monkeypatch.delenv("CHAT_MODE", raising=False)
    assert Settings().mode == load_settings().mode == "live"


def test_button_runs_live_pipeline_with_frozen_caps_using_offline_provider(
    client, monkeypatch
):
    calls = []

    def offline_run(pool, run_id, body, settings, registry, started, **kwargs):
        calls.append(settings)
        return ChatResult(
            run_id=run_id,
            mode=settings.mode,
            status="unverified",
            answer="Offline provider fixture.",
            final_model="offline",
            total_cost_usd=Decimal(".001"),
            known_cost_usd=Decimal(".001"),
        )

    monkeypatch.setattr(jobs, "run_chat", offline_run)
    config = client.get("/api/benchmarks/config").json()
    assert config == {
        "mode": "live",
        "budget_usd": "1.00",
        "request_budget_usd": "0.25",
    }
    assert "offline-key" not in str(config)
    response = client.post("/api/benchmarks", headers=HEADERS)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    report = client.get(f"/api/benchmarks/{job_id}").json()
    assert report["mode"] == "live" and report["strategy"] == "routed"
    assert report["status"] == "completed" and report["states"]["done"] == 30
    assert Decimal(report["budget_used_usd"]) == Decimal(".030")
    assert len(calls) == 30 and all(
        s.request_budget_usd == Decimal(".25") for s in calls
    )
    assert client.get("/api/benchmarks?limit=1").json()[0]["job_id"] == job_id


def test_start_returns_before_runner_finishes_and_rejects_overlap(client, monkeypatch):
    entered, release = Event(), Event()

    def held_run(pool, job_id):
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(jobs, "run_job", held_run)
    with ThreadPoolExecutor() as executor:
        pending = executor.submit(client.post, "/api/benchmarks", headers=HEADERS)
        try:
            assert entered.wait(5)
            # The job is committed and readable while the background task is held.
            assert (
                client.get("/api/benchmarks?limit=1").json()[0]["status"] == "pending"
            )
            assert client.post("/api/benchmarks", headers=HEADERS).status_code == 409
        finally:
            release.set()
        assert pending.result().status_code == 202
    assert not app.state.benchmark_lock.locked()


@pytest.mark.parametrize("budget", ["", "0", "-1", "NaN", "Infinity"])
def test_invalid_budget_blocks_creation(client, monkeypatch, budget):
    monkeypatch.setenv("BENCHMARK_BUDGET_USD", budget)
    monkeypatch.setattr(jobs, "create_job", lambda *a: pytest.fail("No job expected"))
    assert client.get("/api/benchmarks/config").status_code == 503
    assert client.post("/api/benchmarks", headers=HEADERS).status_code == 503


def test_missing_request_budget_and_live_credentials_block_start(client, monkeypatch):
    monkeypatch.delenv("REQUEST_BUDGET_USD")
    assert client.post("/api/benchmarks", headers=HEADERS).status_code == 503
    monkeypatch.setenv("REQUEST_BUDGET_USD", ".25")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert client.post("/api/benchmarks", headers=HEADERS).status_code == 503


def test_start_requires_custom_header(client):
    assert client.post("/api/benchmarks").status_code == 422
    assert (
        client.post(
            "/api/benchmarks", headers={"X-Arbiter-Benchmark": "bad"}
        ).status_code
        == 422
    )
    assert (
        client.options(
            "/api/benchmarks",
            headers={
                "Origin": "https://other.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Arbiter-Benchmark",
            },
        ).status_code
        == 405
    )


def test_creation_and_runner_failures_release_slot(client, monkeypatch):
    create = jobs.create_job

    def fail(*args):
        raise psycopg.OperationalError("private failure")

    monkeypatch.setattr(jobs, "create_job", fail)
    response = client.post("/api/benchmarks", headers=HEADERS)
    assert response.status_code == 503 and "private" not in response.text
    assert not app.state.benchmark_lock.locked()
    monkeypatch.setattr(jobs, "create_job", create)
    monkeypatch.setattr(jobs, "run_job", fail)
    response = client.post("/api/benchmarks", headers=HEADERS)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert client.get(f"/api/benchmarks/{job_id}").json()["status"] == "uncertain"
    assert not app.state.benchmark_lock.locked()


def test_start_without_database_is_safe(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        assert client.post("/api/benchmarks", headers=HEADERS).status_code == 503
