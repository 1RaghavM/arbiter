import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

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


def create_run(pool, run_id, request: ChatRequest):
    with pool.connection() as connection:
        connection.execute(
            "INSERT INTO runs (id, mode, status, messages, config_version) "
            "VALUES (%s, 'mock', 'running', %s, 'mock-v1')",
            (run_id, Jsonb(request.model_dump()["messages"])),
        )


def finish_run(pool, result: ChatResult, generation: GenerationResult, error=None):
    with pool.connection() as connection:
        connection.execute(
            "INSERT INTO calls (id, run_id, sequence, stage, provider, model_id, "
            "attempt, status, latency_ms, cost_usd, cost_source, output, error) "
            "VALUES (%s, %s, 1, 'generate', 'mock', %s, 1, %s, %s, %s, %s, %s, %s)",
            (
                uuid4(),
                result.run_id,
                generation.model_key,
                "error" if error else "done",
                generation.latency_ms,
                generation.cost_usd,
                generation.cost_source,
                Jsonb(generation.model_dump(mode="json")),
                Jsonb(error),
            ),
        )
        connection.execute(
            "UPDATE runs SET status=%s, final_answer=%s, final_model=%s, "
            "total_latency_ms=%s, total_cost_usd=%s, known_cost_usd=%s, "
            "cost_complete=%s, error=%s WHERE id=%s",
            (
                result.status,
                result.answer,
                result.final_model,
                result.total_latency_ms,
                result.total_cost_usd,
                result.known_cost_usd,
                result.cost_complete,
                Jsonb(error),
                result.run_id,
            ),
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
    migrate(os.environ["DATABASE_URL"])
    print("Migrations applied.")
