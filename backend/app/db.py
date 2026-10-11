import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.config import load_environment
from app.schemas import ChatRequest, ChatResult, GenerationResult


def create_pool(url):
    return ConnectionPool(
        url,
        min_size=0,
        max_size=4,
        timeout=3,
        open=True,
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": 3,
            "options": "-c statement_timeout=5000",
        },
    )


def migrate(url):
    with psycopg.connect(url, connect_timeout=3) as connection:
        connection.execute("SET LOCAL statement_timeout = '10s'")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        versions = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for path in sorted((Path(__file__).parents[1] / "migrations").glob("*.sql")):
            if path.name not in versions:
                connection.execute(path.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,)
                )


def create_run(
    pool,
    run_id,
    request: ChatRequest,
    mode="mock",
    version="mock-v1",
    benchmark_job_id=None,
):
    with pool.connection() as connection:
        connection.execute(
            "INSERT INTO runs (id, mode, status, messages, config_version, "
            "benchmark_job_id) "
            "VALUES (%s, %s, 'running', %s, %s, %s)",
            (
                run_id,
                mode,
                Jsonb(request.model_dump()["messages"]),
                version,
                benchmark_job_id,
            ),
        )


def record_analysis(pool, run_id, result):
    payload = result.model_dump(mode="json")
    with pool.connection() as connection:
        connection.execute(
            "UPDATE runs SET analysis=%s WHERE id=%s", (Jsonb(payload), run_id)
        )
        if result.called:
            connection.execute(
                "INSERT INTO calls (id, run_id, sequence, stage, provider, model_id, "
                "attempt, status, latency_ms, cost_usd, cost_source, output, error, "
                "input_tokens, output_tokens, raw_usage, price_snapshot) "
                "VALUES (%s, %s, 1, 'classify', 'jev', %s, 1, %s, %s, %s, %s, "
                "%s, %s, %s, %s, %s, %s)",
                (
                    uuid4(),
                    run_id,
                    result.model_id,
                    "error" if result.error_category else "done",
                    result.latency_ms,
                    result.cost_usd,
                    result.cost_source,
                    Jsonb(payload),
                    Jsonb(
                        {"code": result.error_category}
                        if result.error_category
                        else None
                    ),
                    (result.raw_usage or {}).get("input_tokens"),
                    (result.raw_usage or {}).get("output_tokens"),
                    Jsonb(result.raw_usage),
                    Jsonb(result.price_snapshot),
                ),
            )


def record_call(pool, run_id, sequence, stage, attempt, generation, evaluation=None):
    payload = generation.model_dump(mode="json")
    if evaluation is not None:
        payload["evaluation"] = (
            evaluation.model_dump(mode="json")
            if hasattr(evaluation, "model_dump")
            else evaluation
        )
    error_category = generation.error_category or (
        payload.get("evaluation", {}).get("error_category")
    )
    with pool.connection() as connection:
        connection.execute(
            "INSERT INTO calls (id, run_id, sequence, stage, provider, model_id, "
            "attempt, status, latency_ms, cost_usd, cost_source, output, error, "
            "input_tokens, output_tokens, raw_usage, price_snapshot) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                run_id,
                sequence,
                stage,
                generation.provider,
                generation.model_id,
                attempt,
                "error" if error_category else "done",
                generation.latency_ms,
                generation.cost_usd,
                generation.cost_source,
                Jsonb(payload),
                Jsonb({"code": error_category} if error_category else None),
                generation.input_tokens,
                generation.output_tokens,
                Jsonb(generation.raw_usage),
                Jsonb(generation.price_snapshot),
            ),
        )


def finish_run(
    pool, result: ChatResult, generation: GenerationResult | None, started, error=None
):
    if generation is not None:
        record_call(
            pool,
            result.run_id,
            2 if result.analysis and result.analysis.get("called") else 1,
            "generate",
            1,
            generation,
        )
    with pool.connection() as connection:
        connection.execute(
            "UPDATE runs SET status=%s, final_answer=%s, final_model=%s, "
            "total_latency_ms=%s, total_cost_usd=%s, known_cost_usd=%s, "
            "cost_complete=%s, error=%s, analysis=%s, route_decisions=%s, "
            "policy_version=%s, evaluations=%s, escalation_reason=%s, "
            "reserved_cost_usd=%s, rubric_version=%s WHERE id=%s",
            (
                result.status,
                result.answer,
                result.final_model,
                result.total_latency_ms,
                result.total_cost_usd,
                result.known_cost_usd,
                result.cost_complete,
                Jsonb(error),
                Jsonb(result.analysis),
                Jsonb(result.route_decisions),
                result.route_decisions[0].get("policy_version")
                if result.route_decisions
                else None,
                Jsonb(result.evaluations),
                result.escalation_reason,
                result.reserved_cost_usd,
                "rubric-v1" if result.evaluations or result.route_decisions else None,
                result.run_id,
            ),
        )

    result.total_latency_ms = round((perf_counter() - started) * 1000)
    with pool.connection() as connection:
        connection.execute(
            "UPDATE runs SET total_latency_ms=%s WHERE id=%s",
            (result.total_latency_ms, result.run_id),
        )


def recent_runs(pool, limit):
    with pool.connection() as connection:
        return connection.execute(
            "SELECT id, created_at, mode, status, final_model, total_latency_ms, "
            "total_cost_usd, known_cost_usd, cost_complete FROM runs "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()


def read_run(pool, run_id):
    with pool.connection() as connection:
        run = connection.execute("SELECT * FROM runs WHERE id=%s", (run_id,)).fetchone()
        if run:
            run["calls"] = connection.execute(
                "SELECT * FROM calls WHERE run_id=%s ORDER BY sequence", (run_id,)
            ).fetchall()
        return run


if __name__ == "__main__":
    load_environment()
    migrate(os.environ["DATABASE_URL"])
    print("Migrations applied.")
