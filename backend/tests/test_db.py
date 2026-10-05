import os
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
    generation = GenerationResult(text="Mock reply")
    result = ChatResult(
        run_id=run_id,
        answer=generation.text,
        status="unverified",
        final_model="mock-v1",
        attempts=[generation],
    )
    try:
        db.create_run(pool, run_id, request)
        db.finish_run(pool, result, generation)
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
                    == 1
                )
    finally:
        with pool.connection() as connection:
            connection.execute("DELETE FROM calls WHERE run_id=%s", (run_id,))
            connection.execute("DELETE FROM runs WHERE id=%s", (run_id,))
