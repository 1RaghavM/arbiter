import json
import os
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from app import db
from app.config import load_registry
from app.history import load_history
from app.schemas import GenerationResult


@pytest.fixture
def history_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    db.migrate(url)
    registry = load_registry()
    prefix = str(uuid4())
    registry.models = [
        m.model_copy(update={"model_id": prefix + m.key}) for m in registry.models
    ]
    generator = registry.models[0]
    judge = next(m for m in registry.models if m.key == registry.judge_key)
    run_ids = []
    with db.create_pool(url) as pool:

        def seed(
            labels=("pass",),
            *,
            mode="live",
            policy="history-v1",
            rubric="rubric-v1",
            state="passed",
            model_id=None,
            judge_id=None,
            paid=True,
            provider=None,
            generation_error=None,
            finish_reason="stop",
            tokens=20,
        ):
            run_id = uuid4()
            run_ids.append(run_id)
            grades = [
                {
                    "attempt": i,
                    "model_key": generator.key,
                    "status": label,
                    "error_category": "incomplete_answer"
                    if finish_reason == "length"
                    else None,
                }
                for i, label in enumerate(labels, 1)
                if label is not None
            ]
            with pool.connection() as connection:
                connection.execute(
                    "INSERT INTO runs (id, mode, status, messages, config_version, "
                    "policy_version, rubric_version, analysis, evaluations) "
                    "VALUES (%s,%s,%s,'[]','fixture',%s,%s,%s,%s)",
                    (
                        run_id,
                        mode,
                        state,
                        policy,
                        rubric,
                        Jsonb({"task": "general", "difficulty": "easy"}),
                        Jsonb(grades),
                    ),
                )
            for attempt, label in enumerate(labels, 1):
                generation = GenerationResult(
                    model_key=generator.key,
                    provider=provider or generator.provider,
                    model_id=model_id or generator.model_id,
                    text="answer",
                    latency_ms=100 * attempt,
                    output_tokens=tokens,
                    error_category=generation_error,
                    finish_reason=finish_reason,
                )
                db.record_call(
                    pool, run_id, attempt * 2, "generate", attempt, generation
                )
                if paid:
                    result = GenerationResult(
                        text="judgment",
                        model_key=judge.key,
                        provider=judge.provider,
                        model_id=judge_id or judge.model_id,
                    )
                    db.record_call(
                        pool, run_id, attempt * 2 + 1, "evaluate", attempt, result
                    )
            return run_id

        try:
            yield pool, registry, seed
        finally:
            with pool.connection() as connection:
                connection.execute(
                    "DELETE FROM calls WHERE run_id = ANY(%s)", (run_ids,)
                )
                connection.execute("DELETE FROM runs WHERE id = ANY(%s)", (run_ids,))


def test_per_attempt_labels_unknowns_and_stable_serializable_snapshot(history_database):
    pool, registry, seed = history_database
    seed(("fail", "pass", "unknown", None))
    snapshot = load_history(pool, registry)
    (entry,) = snapshot["entries"]
    assert (entry["n"], entry["passes"], entry["failures"], entry["unknown_count"]) == (
        2,
        1,
        1,
        2,
    )
    assert entry["latency_ms"] == 150 and entry["output_tokens"] == 20
    assert json.loads(json.dumps(snapshot)) == snapshot
    assert load_history(pool, registry) == snapshot
    seed()
    assert load_history(pool, registry)["id"] != snapshot["id"]


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "mock"},
        {"mode": "heldout"},
        {"mode": "baseline"},
        {"policy": "priors-v1"},
        {"rubric": "old"},
        {"state": "running"},
        {"model_id": "old"},
        {"provider": "other"},
        {"judge_id": "old"},
    ],
)
def test_incompatible_records_are_excluded(history_database, change):
    pool, registry, seed = history_database
    seed(**change)
    assert load_history(pool, registry)["entries"] == []


def test_provider_errors_and_deterministic_failures_need_no_paid_judge(
    history_database,
):
    pool, registry, seed = history_database
    seed((None,), paid=False, generation_error="timeout", state="error", tokens=None)
    seed(("fail",), paid=False, finish_reason="length", tokens=1024)
    seed(("pass",), paid=False, mode="dev")
    (entry,) = load_history(pool, registry)["entries"]
    assert entry["n"] == 2 and entry["failures"] == 2 and entry["passes"] == 0
    assert entry["unknown_count"] == 1 and entry["output_tokens"] == 1024


def test_output_median_uses_only_known_labeled_usage(history_database):
    pool, registry, seed = history_database
    seed(tokens=None)
    seed(tokens=10)
    seed(tokens=31)
    seed(("unknown",), tokens=1000)
    (entry,) = load_history(pool, registry)["entries"]
    assert entry["output_tokens"] == 20.5
