import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import db, jobs
from app.config import Settings, load_registry
from app.main import app
from app.schemas import ChatResult, GenerationResult


@pytest.fixture
def pool():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for real PostgreSQL job tests")
    db.migrate(url)
    db.migrate(url)
    with db.create_pool(url) as pool:
        yield pool


def cases(n=2):
    return jobs.validate_cases(
        [
            {
                "id": f"case-{i}",
                "split": "dev",
                "rubric": "Return blue.",
                "messages": [{"role": "user", "content": "Return blue."}],
            }
            for i in range(n)
        ]
    )


def new_job(pool, n=2, budget="1", mode="live"):
    return jobs.create_job(
        pool,
        cases(n),
        Settings(mode=mode, request_budget_usd=".25"),
        load_registry(),
        {"id": "frozen-test", "entries": []},
        Decimal(budget),
    )


def install_runner(monkeypatch, cost=".01", crash_at=None):
    calls = []

    def run(pool, run_id, body, settings, registry, started, **kwargs):
        calls.append((run_id, body, settings, registry, kwargs))
        # Reservation must be committed and visible through another connection.
        with pool.connection() as connection:
            row = connection.execute(
                "SELECT state, run_id FROM benchmark_cases "
                "WHERE job_id=%s AND run_id=%s",
                (kwargs["benchmark_job_id"], run_id),
            ).fetchone()
            assert row["state"] == "running" and row["run_id"] == run_id
        if crash_at == len(calls):
            raise RuntimeError("controlled interruption")
        return ChatResult(
            run_id=run_id,
            mode=settings.mode,
            status="unverified",
            answer="blue",
            final_model="offline",
            total_cost_usd=Decimal(cost) if cost else None,
            known_cost_usd=Decimal(cost) if cost else Decimal(".005"),
            cost_complete=bool(cost),
        )

    monkeypatch.setattr(jobs, "run_chat", run)
    return calls


def test_dataset_validation_and_six_synthetic_cases():
    rows = jobs.read_cases(Path(__file__).parents[2] / "benchmarks/dev.jsonl")
    assert len(rows) == 6 and all(case.split == "dev" for case in rows)
    with pytest.raises(ValueError, match="unique"):
        jobs.validate_cases([cases(1)[0].model_dump()] * 2)
    for changes in [{"split": "heldout"}, {"id": "../escape"}, {"messages": []}]:
        with pytest.raises(ValidationError):
            jobs.validate_cases([cases(1)[0].model_dump() | changes])


def test_completed_job_uses_frozen_data_and_resume_skips_done(pool, monkeypatch):
    calls = install_runner(monkeypatch)
    job_id = new_job(pool)
    result = jobs.run_job(pool, job_id)
    assert result["status"] == "completed" and result["states"]["done"] == 2
    assert Decimal(result["budget_used_usd"]) == Decimal(".02")
    assert result["cost_complete"] and result["history_snapshot_id"] == "frozen-test"
    assert calls[0][4]["run_mode"] == "dev" and calls[0][4]["history_snapshot"] == {
        "id": "frozen-test",
        "entries": [],
    }
    monkeypatch.setenv("REQUEST_BUDGET_USD", "999")
    monkeypatch.setattr(
        jobs,
        "load_registry",
        lambda: (_ for _ in ()).throw(AssertionError("live registry read")),
    )
    assert jobs.run_job(pool, job_id)["status"] == "completed"
    assert len(calls) == 2 and calls[0][2].request_budget_usd == Decimal(".25")
    json.dumps(result, default=str)


def test_known_and_unknown_costs_control_aggregate_ceiling(pool, monkeypatch):
    calls = install_runner(monkeypatch, cost=None)
    job_id = new_job(pool, budget=".49")
    result = jobs.run_job(pool, job_id)
    assert len(calls) == 1 and result["status"] == "blocked"
    assert Decimal(result["budget_used_usd"]) == Decimal(".25")
    assert Decimal(result["known_cost_usd"]) == Decimal(".005")
    assert not result["cost_complete"] and result["states"]["pending"] == 1
    jobs.run_job(pool, job_id)
    assert len(calls) == 1


def test_interrupted_case_requires_explicit_retry_and_keeps_old_reservation(
    pool, monkeypatch
):
    calls = install_runner(monkeypatch, crash_at=2)
    job_id = new_job(pool, budget=".60")
    with pytest.raises(RuntimeError, match="controlled"):
        jobs.run_job(pool, job_id)
    result = jobs.run_job(pool, job_id)
    assert result["status"] == "uncertain" and result["states"]["done"] == 1
    assert result["states"]["uncertain"] == 1 and len(calls) == 2
    assert Decimal(result["budget_used_usd"]) == Decimal(".26")
    result = jobs.run_job(pool, job_id, retry_uncertain=True)
    assert result["status"] == "completed" and len(calls) == 3
    assert calls[1][0] != calls[2][0]
    assert result["cases"][1]["attempts"] == 2
    assert Decimal(result["budget_used_usd"]) == Decimal(".27")
    assert not result["cost_complete"]


def test_retry_needs_new_budget_and_concurrent_runner_is_rejected(pool, monkeypatch):
    calls = install_runner(monkeypatch, crash_at=1)
    job_id = new_job(pool, n=1, budget=".25")
    with pytest.raises(RuntimeError):
        jobs.run_job(pool, job_id)
    result = jobs.run_job(pool, job_id, retry_uncertain=True)
    assert result["status"] == "blocked" and len(calls) == 1
    assert Decimal(result["budget_used_usd"]) == Decimal(".25")
    with pool.connection() as lease:
        lease.execute(
            "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (str(job_id),)
        )
        lease.commit()
        try:
            with pytest.raises(ValueError, match="already has a runner"):
                jobs.run_job(pool, job_id)
        finally:
            lease.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (str(job_id),)
            )
            lease.commit()


def test_real_mock_pipeline_persists_job_run_link_and_freezes_snapshot(pool):
    job_id = new_job(pool, n=1, mode="mock")
    result = jobs.run_job(pool, job_id)
    assert result["status"] == "completed" and result["known_cost_usd"] == "0"
    run = db.read_run(pool, result["cases"][0]["run_id"])
    assert run["mode"] == "mock" and run["benchmark_job_id"] == job_id
    assert run["calls"][0]["provider"] == "mock"


def test_observed_cost_over_cap_stops_before_next_case(pool, monkeypatch):
    calls = install_runner(monkeypatch, cost=".51")
    result = jobs.run_job(pool, new_job(pool, budget=".50"))
    assert len(calls) == 1 and result["status"] == "blocked"
    assert Decimal(result["budget_used_usd"]) == Decimal(".51")


def test_invalid_budgets_and_empty_data_are_rejected_before_creation(pool):
    for budget in ("0", "-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            new_job(pool, budget=budget)
    with pytest.raises(ValueError):
        jobs.create_job(
            pool,
            [],
            Settings(request_budget_usd=".25"),
            load_registry(),
            {},
            Decimal(1),
        )


@pytest.mark.parametrize(
    "module,constant",
    [
        (jobs.history, "POLICY_VERSION"),
        (jobs.evaluation, "RUBRIC_VERSION"),
        (jobs.analysis, "POLICY_VERSION"),
    ],
)
def test_resume_rejects_changed_runtime_versions_before_mutation(
    pool, monkeypatch, module, constant
):
    calls = install_runner(monkeypatch)
    job_id = new_job(pool)
    monkeypatch.setattr(module, constant, "future-version")
    with pytest.raises(ValueError, match="versions differ"):
        jobs.run_job(pool, job_id)
    assert not calls and jobs.report_job(pool, job_id)["status"] == "pending"


def test_partial_call_cost_and_run_id_survive_crash_and_repeated_resume(
    pool, monkeypatch
):
    def interrupted(pool, run_id, body, settings, registry, started, **kwargs):
        db.create_run(pool, run_id, body, "dev", "offline", kwargs["benchmark_job_id"])
        db.record_call(
            pool,
            run_id,
            1,
            "generate",
            1,
            GenerationResult(text="partial", cost_usd=Decimal(".03")),
        )
        raise RuntimeError("interrupted after recorded paid stage")

    monkeypatch.setattr(jobs, "run_chat", interrupted)
    job_id = new_job(pool, n=1)
    with pytest.raises(RuntimeError):
        jobs.run_job(pool, job_id)
    immediate = jobs.report_job(pool, job_id)
    assert immediate["states"]["running"] == 1 and not immediate["cost_complete"]
    assert Decimal(immediate["known_cost_usd"]) == Decimal(".03")
    prior_id = str(immediate["cases"][0]["run_id"])
    first = jobs.run_job(pool, job_id)
    second = jobs.run_job(pool, job_id)
    assert first == second and first["status"] == "uncertain"
    assert Decimal(first["known_cost_usd"]) == Decimal(".03")
    assert Decimal(first["budget_used_usd"]) == Decimal(".25")
    assert first["cases"][0]["uncertain_attempts"] == [
        {"run_id": prior_id, "reserved_cost_usd": "0.25", "known_cost_usd": "0.03"}
    ]
    install_runner(monkeypatch)
    retried = jobs.run_job(pool, job_id, retry_uncertain=True)
    assert retried["cases"][0]["uncertain_attempts"][0]["run_id"] == prior_id
    assert Decimal(retried["known_cost_usd"]) == Decimal(".04")
    assert Decimal(retried["budget_used_usd"]) == Decimal(".26")
    assert not retried["cost_complete"]


def test_benchmark_read_endpoints_return_safe_summaries_and_real_mock_results(
    pool, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    new_job(pool, n=1, mode="mock")
    job_id = new_job(pool, n=1, mode="mock")
    jobs.run_job(pool, job_id)
    with TestClient(app) as client:
        response = client.get("/api/benchmarks?limit=1")
        assert response.status_code == 200
        summary = response.json()[0]
        assert len(response.json()) == 1 and summary["job_id"] == str(job_id)
        assert summary["created_at"]
        assert summary["mode"] == "mock" and summary["status"] == "completed"
        assert summary["case_count"] == 1 and summary["states"]["done"] == 1
        assert summary["online_pass_count"] == 0
        assert summary["known_cost_usd"] == "0" and summary["cost_complete"]
        assert "no independent benchmark grading" in summary["quality_basis"]
        detail = client.get(f"/api/benchmarks/{job_id}")
        assert detail.status_code == 200
        report = detail.json()
        cases = report.pop("cases")
        assert report == summary
        assert cases[0]["state"] == "done"
        assert cases[0]["result"]["status"] == "unverified"
        assert cases[0]["attempts"] == 1
        assert not {"dataset", "config_snapshot", "history_snapshot"} & report.keys()
        assert "Return blue." not in detail.text
        for limit in (0, 101):
            assert client.get(f"/api/benchmarks?limit={limit}").status_code == 422
        assert client.get("/api/benchmarks/not-a-uuid").status_code == 422
        missing = client.get(f"/api/benchmarks/{uuid4()}")
        assert missing.status_code == 404 and missing.json()["code"] == "not_found"
        assert client.post("/api/benchmarks", json={}).status_code == 405


def test_benchmark_http_preserves_unknown_costs(pool, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    install_runner(monkeypatch, cost=None)
    job_id = new_job(pool, n=1)
    jobs.run_job(pool, job_id)
    with TestClient(app) as client:
        report = client.get(f"/api/benchmarks/{job_id}").json()
        assert not report["cost_complete"]
        assert Decimal(report["known_cost_usd"]) == Decimal(".005")
        assert report["cases"][0]["result"]["total_cost_usd"] is None
        assert not client.get("/api/benchmarks?limit=1").json()[0]["cost_complete"]


def test_benchmark_reads_without_database_return_safe_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(app) as client:
        for path in ("/api/benchmarks", f"/api/benchmarks/{uuid4()}"):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["code"] == "database_unavailable"
