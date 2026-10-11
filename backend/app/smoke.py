import argparse
import json
import os
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

import psycopg
from psycopg_pool import PoolTimeout

from app import db
from app.config import (
    Settings,
    load_environment,
    load_registry,
    model_status,
    reserve_cost,
)
from app.pipeline import run_chat
from app.schemas import ChatRequest


def smoke(pool, registry, budget, model_keys):
    settings = Settings(mode="live", request_budget_usd=budget)
    body = ChatRequest(
        messages=[{"role": "user", "content": "Reply exactly: smoke OK"}]
    )
    models = [m for m in registry.models if m.key in model_keys]
    if {m.key for m in models} != set(model_keys):
        raise ValueError("Unknown model key.")
    available = [m for m in models if model_status(m) == "available"]
    reservations = {m.key: reserve_cost(m, body.messages) for m in available}
    if sum(reservations.values(), Decimal(0)) > budget:
        raise ValueError("Smoke reservations exceed the explicit total budget.")
    used = Decimal(0)
    outcomes = []
    for model in models:
        status = model_status(model)
        if status != "available":
            outcomes.append({"model": model.key, "status": "blocked", "reason": status})
            continue
        if used + reservations[model.key] > budget:
            outcomes.append(
                {"model": model.key, "status": "blocked", "reason": "budget"}
            )
            continue
        run_id = uuid4()
        settings.fixed_model_key = model.key
        settings.request_budget_usd = min(budget - used, reservations[model.key])
        try:
            result = run_chat(
                pool, run_id, body, settings, registry, perf_counter(), fixed=True
            )
        except (psycopg.Error, PoolTimeout):
            outcomes.append(
                {
                    "model": model.key,
                    "status": "error",
                    "reason": "persistence_error",
                    "run_id": str(run_id),
                }
            )
            break
        used += (
            result.total_cost_usd if result.cost_complete else reservations[model.key]
        )
        outcomes.append(
            {
                "model": model.key,
                "model_id": model.model_id,
                "run_id": str(run_id),
                "status": "ok" if result.status != "error" else "error",
                "answer": result.answer,
                "cost_usd": str(result.total_cost_usd)
                if result.total_cost_usd is not None
                else None,
                "cost_complete": result.cost_complete,
                "reserved_cost_usd": str(reservations[model.key]),
                "error": result.error_category,
            }
        )
    return outcomes


def main():
    parser = argparse.ArgumentParser(description="One bounded live call per model.")
    parser.add_argument("--budget-usd", required=True)
    parser.add_argument(
        "--models", nargs="+", default=["openai", "anthropic", "google"]
    )
    args = parser.parse_args()
    load_environment()
    try:
        budget = Settings(request_budget_usd=args.budget_usd).request_budget_usd
        registry = load_registry()
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError(
                "Set DATABASE_URL and apply migrations before smoke calls."
            )
        with db.create_pool(url) as pool:
            outcomes = smoke(pool, registry, budget, args.models)
    except (ValueError, OSError):
        print(
            "Smoke configuration invalid. "
            "Check database, model keys, and positive budget."
        )
        return 2
    print(json.dumps(outcomes, indent=2))
    return 0 if all(row["status"] == "ok" for row in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
