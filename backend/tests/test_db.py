import os
from time import perf_counter
from uuid import uuid4

import pytest

from app import db
from app.schemas import ChatRequest, ChatResult, GenerationResult


@pytest.fixture
def pool():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    db.migrate(url)
    db.migrate(url)
    with db.create_pool(url) as pool:
        yield pool


def test_round_trip_and_reconnect(pool):
    run_id = uuid4()
    request = ChatRequest(messages=[{"role": "user", "content": "It's mock 🧪"}])
    generation = GenerationResult(
        text="Mock reply", cost_usd=0, cost_source="estimated"
    )
    result = ChatResult(
        run_id=run_id,
        answer=generation.text,
        status="unverified",
        final_model="mock-v1",
        attempts=[generation],
    )
    try:
        db.create_run(pool, run_id, request)
        db.finish_run(pool, result, generation, perf_counter())
        with db.create_pool(os.environ["TEST_DATABASE_URL"]) as reconnected:
            run = db.read_run(reconnected, run_id)
            assert run["messages"] == request.model_dump()["messages"]
            assert run["mode"] == "mock"
            assert run["final_answer"] == "Mock reply"
            assert run["cost_complete"] and run["total_cost_usd"] == 0
            assert run["calls"][0]["provider"] == "mock"
            assert run["calls"][0]["output"]["text"] == "Mock reply"
            assert "messages" not in db.recent_runs(reconnected, 1)[0]
            assert db.read_run(reconnected, uuid4()) is None
            with reconnected.connection() as connection:
                assert (
                    connection.execute(
                        "SELECT count(*) AS n FROM schema_migrations"
                    ).fetchone()["n"]
                    == 2
                )
    finally:
        with pool.connection() as connection:
            connection.execute("DELETE FROM calls WHERE run_id=%s", (run_id,))
            connection.execute("DELETE FROM runs WHERE id=%s", (run_id,))


def test_evaluation_calls_survive_reconnect_before_finalization(pool):
    from decimal import Decimal

    run_id = uuid4()
    db.create_run(
        pool,
        run_id,
        ChatRequest(messages=[{"role": "user", "content": "test"}]),
        "live",
    )
    generation = GenerationResult(
        text="answer",
        model_key="openai",
        provider="openai",
        model_id="model",
        cost_usd=Decimal(".001"),
    )
    judge = GenerationResult(
        text='{"correctness":3}',
        model_key="anthropic",
        provider="anthropic",
        model_id="judge",
        cost_usd=Decimal(".002"),
    )
    evaluation = {
        "status": "pass",
        "correctness": 3,
        "relevance": 4,
        "completeness": 4,
        "reason": "ok",
    }
    db.record_call(pool, run_id, 1, "generate", 1, generation)
    db.record_call(pool, run_id, 2, "evaluate", 1, judge, evaluation)
    with db.create_pool(os.environ["TEST_DATABASE_URL"]) as reconnected:
        partial = db.read_run(reconnected, run_id)
        assert partial["status"] == "running"
        assert [c["stage"] for c in partial["calls"]] == ["generate", "evaluate"]
        assert partial["calls"][1]["output"]["evaluation"] == evaluation
    result = ChatResult(
        run_id=run_id,
        mode="live",
        answer="answer",
        final_model="openai",
        status="passed",
        attempts=[generation],
        evaluations=[evaluation],
        total_cost_usd=Decimal(".003"),
        known_cost_usd=Decimal(".003"),
        reserved_cost_usd=Decimal(".04"),
    )
    db.finish_run(pool, result, None, perf_counter())
    stored = db.read_run(pool, run_id)
    assert stored["evaluations"] == [evaluation]
    assert stored["rubric_version"] == "rubric-v1"
    assert stored["reserved_cost_usd"] == Decimal(".04")
    assert len(stored["calls"]) == 2
