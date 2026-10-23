import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import db, grading, history, jobs
from app.config import Settings, load_registry
from app.main import app
from app.schemas import ChatResult, GenerationResult


@pytest.fixture
def pool():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for PostgreSQL comparison tests")
    db.migrate(url)
    with db.create_pool(url) as pool:
        yield pool


def comparison(pool, monkeypatch, n=1, budget="2", rubric=False):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.setenv(key, "offline-test-key")
    cases = grading.validate_cases(
        [
            {
                "id": f"heldout-{i}",
                "split": "heldout",
                "task": "general",
                "difficulty": "easy",
                "grading": "rubric" if rubric else "exact",
                "rubric": "Answer blue.",
                "expected_answer": "blue",
                "messages": [{"role": "user", "content": "Return blue."}],
                "provenance": "Synthetic test fixture",
            }
            for i in range(n)
        ]
    )
    registry = load_registry()
    return jobs.create_comparison(
        pool,
        cases,
        Settings(mode="live", request_budget_usd=".25"),
        registry,
        {"id": "frozen-empty", "entries": []},
        budget,
        registry.judge_key,
        seed=17,
    )


def install_generation(monkeypatch):
    calls = []

    def generate(pool, run_id, body, settings, registry, started, **kwargs):
        calls.append((settings.fixed_model_key, kwargs))
        with pool.connection() as connection:
            assert (
                connection.execute(
                    "SELECT state FROM benchmark_cases WHERE run_id=%s",
                    (run_id,),
                ).fetchone()["state"]
                == "running"
            )
        db.create_run(
            pool,
            run_id,
            body,
            kwargs["run_mode"],
            "fixture",
            kwargs["benchmark_job_id"],
        )
        generation = GenerationResult(
            text="blue",
            provider="google",
            model_key=settings.fixed_model_key,
            cost_usd=Decimal(".01"),
            latency_ms=100,
        )
        result = ChatResult(
            run_id=run_id,
            mode="live",
            status="unverified",
            answer="blue",
            final_model=generation.model_key,
            attempts=[generation],
            total_cost_usd=Decimal(".01"),
            known_cost_usd=Decimal(".01"),
            total_latency_ms=120,
        )
        db.finish_run(pool, result, generation, started)
        return result

    monkeypatch.setattr(jobs, "run_chat", generate)
    return calls


def test_frozen_order_baselines_history_exclusion_and_resume(pool, monkeypatch):
    calls = install_generation(monkeypatch)
    first = comparison(pool, monkeypatch, n=2)
    second = comparison(pool, monkeypatch, n=2)

    def order(job_id):
        return [
            (row["case_id"], row["strategy"], row["stage"])
            for row in jobs.report_job(pool, job_id)["cases"]
        ]

    assert order(first) == order(second)
    frozen = jobs.experiment_export(pool, first)
    assert (
        frozen["config_snapshot"]["runtime_fingerprint"] == jobs.runtime_fingerprint()
    )
    assert frozen["config_snapshot"]["source_revision"]
    result = jobs.run_job(pool, first)
    assert result["status"] == "completed" and len(calls) == 6
    assert result["case_count"] == 6 and result["states"]["done"] == 6
    assert Decimal(result["known_cost_usd"]) == Decimal(".06")
    assert Decimal(result["scoring_known_cost_usd"]) == 0
    assert result["scoring_cost_complete"]
    assert all(
        row["result"]["status"] == "pass"
        for row in result["cases"]
        if row["stage"] == "grading"
    )
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    with TestClient(app) as client:
        response = client.get(f"/api/benchmarks/{first}")
        assert response.status_code == 200
        public = response.json()
        assert public["strategy_metrics"]["routed"]["pass_count"] == 2
        assert not {"config_snapshot", "dataset", "history_snapshot"} & public.keys()
        assert "offline-test-key" not in response.text
    registry = load_registry()
    assert sum(kwargs["fixed"] for _, kwargs in calls) == 4
    for key, kwargs in calls:
        assert kwargs["history_snapshot"] == {"id": "frozen-empty", "entries": []}
        assert kwargs["run_mode"] == ("baseline" if kwargs["fixed"] else "heldout")
        if kwargs["fixed"]:
            assert key in {registry.cheap_baseline_key, registry.strong_baseline_key}
    snapshot_before = history.load_history(pool, registry)
    jobs.run_job(pool, first)
    assert len(calls) == 6
    assert history.load_history(pool, registry) == snapshot_before
    with pool.connection() as connection:
        modes = {
            row["mode"]
            for row in connection.execute(
                "SELECT mode FROM runs WHERE benchmark_job_id=%s",
                (first,),
            )
        }
    assert modes == {"heldout", "baseline", "scoring"}


def test_grading_unknown_cost_retains_shared_reservation(pool, monkeypatch):
    install_generation(monkeypatch)
    monkeypatch.setattr(grading, "grade_reservation", lambda *args: Decimal(".25"))
    grading_calls = []

    def grade(*args):
        grading_calls.append(args)
        return {
            "status": "unknown",
            "reason": "timeout",
            "basis": "rubric",
        }, GenerationResult(
            text="",
            cost_usd=None,
            error_category="timeout",
        )

    monkeypatch.setattr(grading, "grade_case", grade)
    job_id = comparison(pool, monkeypatch, budget=".30", rubric=True)
    result = jobs.run_job(pool, job_id)
    assert len(grading_calls) == 1 and result["status"] == "blocked"
    assert Decimal(result["budget_used_usd"]) == Decimal(".28")
    assert result["cost_complete"] and not result["scoring_cost_complete"]
    jobs.run_job(pool, job_id)
    assert len(grading_calls) == 1


def test_grading_crash_is_uncertain_and_keeps_partial_cost_on_retry(pool, monkeypatch):
    install_generation(monkeypatch)
    monkeypatch.setattr(grading, "grade_reservation", lambda *args: Decimal(".10"))
    monkeypatch.setattr(
        grading,
        "grade_case",
        lambda *args: (
            {"status": "pass", "reason": "fixture", "basis": "rubric"},
            GenerationResult(text="fixture", cost_usd=Decimal(".03")),
        ),
    )
    record = db.record_call

    def crash(*args):
        record(*args)
        if args[3] == "score":
            raise RuntimeError("crash after scoring persisted")

    job_id = comparison(pool, monkeypatch, rubric=True)
    monkeypatch.setattr(db, "record_call", crash)
    with pytest.raises(RuntimeError, match="crash"):
        jobs.run_job(pool, job_id)
    immediate = jobs.report_job(pool, job_id)
    assert Decimal(immediate["scoring_known_cost_usd"]) == Decimal(".03")
    assert not immediate["scoring_cost_complete"] and immediate["cost_complete"]
    assert sum(
        Decimal(strategy["known_scoring_cost_usd"])
        for strategy in immediate["strategy_metrics"].values()
    ) == Decimal(".03")
    monkeypatch.setattr(db, "record_call", record)
    recovered = jobs.run_job(pool, job_id)
    uncertain = next(row for row in recovered["cases"] if row["state"] == "uncertain")
    assert len(uncertain["uncertain_attempts"]) == 1
    prior = uncertain["run_id"]
    retried = jobs.run_job(pool, job_id, retry_uncertain=True)
    assert retried["status"] == "completed"
    assert Decimal(retried["known_cost_usd"]) == Decimal(".03")
    assert Decimal(retried["scoring_known_cost_usd"]) == Decimal(".12")
    assert not retried["scoring_cost_complete"]
    retry = next(row for row in retried["cases"] if row["attempts"] == 2)
    assert retry["run_id"] != prior
    assert retry["uncertain_attempts"][0]["run_id"] == str(prior)
    assert Decimal(retried["budget_used_usd"]) == Decimal(".22")


def test_changed_runtime_rejected_before_any_mutation(pool, monkeypatch):
    calls = install_generation(monkeypatch)
    job_id = comparison(pool, monkeypatch)
    monkeypatch.setattr(jobs, "runtime_fingerprint", lambda: "changed-grading-prompt")
    with pytest.raises(ValueError, match="scoring versions"):
        jobs.run_job(pool, job_id)
    assert not calls and jobs.report_job(pool, job_id)["status"] == "pending"


def test_development_runner_rejects_expanded_heldout_data(pool, monkeypatch):
    job_id = comparison(pool, monkeypatch)
    rows = jobs.experiment_export(pool, job_id)["dataset"]
    with pytest.raises(ValueError, match="reject held-out"):
        jobs.validate_cases(rows)


def test_oversized_answer_marks_grade_unknown_without_call_or_blocking_job(
    pool, monkeypatch
):
    install_generation(monkeypatch)
    generate = jobs.run_chat

    def oversized(*args, **kwargs):
        result = generate(*args, **kwargs)
        result.answer = "x" * (grading.evaluation.CANDIDATE_LIMIT + 1)
        return result

    monkeypatch.setattr(jobs, "run_chat", oversized)

    def forbidden(*args):
        raise AssertionError("Oversized answer must not reach the scoring call")

    monkeypatch.setattr(grading, "grade_case", forbidden)
    job_id = comparison(pool, monkeypatch, rubric=True)
    report = jobs.run_job(pool, job_id)
    assert report["status"] == "completed"
    assert Decimal(report["scoring_known_cost_usd"]) == 0
    grades = [row for row in report["cases"] if row["stage"] == "grading"]
    assert all(row["result"]["status"] == "unknown" for row in grades)
    assert all(row["result"]["error_category"] == "input_limit" for row in grades)
