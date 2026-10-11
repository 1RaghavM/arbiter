import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import PoolTimeout
from pydantic import Field

from app import analysis, db, evaluation, history
from app.config import ModelRegistry, Settings, load_registry, load_settings
from app.pipeline import run_chat
from app.schemas import ChatRequest


class BenchmarkCase(ChatRequest):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    split: Literal["dev"]
    rubric: str = Field(min_length=1, max_length=2000)
    expected_answer: str | None = Field(default=None, max_length=2000)


def validate_cases(rows):
    cases = [BenchmarkCase.model_validate(row) for row in rows]
    if not cases or len({case.id for case in cases}) != len(cases):
        raise ValueError("Dataset must contain cases with unique IDs.")
    return cases


def read_cases(path):
    return validate_cases(
        [
            json.loads(line)
            for line in Path(path).read_text().splitlines()
            if line.strip()
        ]
    )


def create_job(pool, cases, settings, registry, history_snapshot, budget):
    budget = Settings(request_budget_usd=budget).request_budget_usd
    if settings.request_budget_usd is None:
        raise ValueError(
            "Configure a positive per-request budget before creating a job."
        )
    cases = validate_cases([case.model_dump(mode="json") for case in cases])
    dataset = [case.model_dump(mode="json") for case in cases]
    digest = hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest()
    job_id = uuid4()
    config = {
        "settings": settings.model_dump(mode="json"),
        "registry": registry.model_dump(mode="json"),
        "job_version": "jobs-v1",
        "policy_version": history.POLICY_VERSION,
        "rubric_version": evaluation.RUBRIC_VERSION,
        "classifier_version": analysis.POLICY_VERSION,
    }
    with pool.connection() as connection:
        connection.execute(
            "INSERT INTO benchmark_jobs (id, dataset_hash, dataset, config_snapshot, "
            "history_snapshot, spend_ceiling_usd) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                job_id,
                digest,
                Jsonb(dataset),
                Jsonb(config),
                Jsonb(history_snapshot),
                budget,
            ),
        )
        for ordinal, case in enumerate(cases):
            connection.execute(
                "INSERT INTO benchmark_cases (job_id, case_id, "
                "ordinal) VALUES (%s,%s,%s)",
                (job_id, case.id, ordinal),
            )
    return job_id


def report_job(pool, job_id):
    with pool.connection() as connection:
        job = connection.execute(
            "SELECT * FROM benchmark_jobs WHERE id=%s", (job_id,)
        ).fetchone()
        if job is None:
            raise ValueError("Unknown benchmark job.")
        cases = connection.execute(
            "SELECT case_id, state, run_id, attempts, reserved_cost_usd, result, "
            "uncertain_attempts "
            "FROM benchmark_cases WHERE job_id=%s ORDER BY ordinal",
            (job_id,),
        ).fetchall()
        partial = connection.execute(
            "SELECT b.case_id, b.reserved_cost_usd, "
            "COALESCE(sum(c.cost_usd),0) AS known "
            "FROM benchmark_cases b LEFT JOIN calls c ON c.run_id=b.run_id "
            "WHERE b.job_id=%s AND b.state='running' "
            "GROUP BY b.case_id,b.reserved_cost_usd",
            (job_id,),
        ).fetchall()
    pending_cost = sum(row["known"] for row in partial)
    pending_overage = sum(
        max(0, row["known"] - row["reserved_cost_usd"]) for row in partial
    )
    return {
        "job_id": str(job_id),
        "status": job["status"],
        "strategy": job["strategy"],
        "mode": job["config_snapshot"]["settings"]["mode"],
        "dataset_hash": job["dataset_hash"],
        "history_snapshot_id": job["history_snapshot"].get("id"),
        "budget_usd": str(job["spend_ceiling_usd"]),
        "budget_used_usd": str(job["budget_used_usd"] + pending_overage),
        "known_cost_usd": str(job["known_cost_usd"] + pending_cost),
        "cost_complete": job["cost_complete"]
        and not any(case["state"] in {"running", "uncertain"} for case in cases),
        "quality_basis": "Online judge proxy only; no independent benchmark grading.",
        "case_count": len(cases),
        "states": {
            state: sum(case["state"] == state for case in cases)
            for state in ("pending", "running", "done", "error", "uncertain")
        },
        "online_pass_count": sum(
            (case["result"] or {}).get("status") == "passed" for case in cases
        ),
        "cases": cases,
    }


def run_job(pool, job_id, retry_uncertain=False):
    # The session lock excludes a second runner without holding a transaction open.
    with pool.connection() as lease:
        locked = lease.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS locked",
            (str(job_id),),
        ).fetchone()["locked"]
        lease.commit()
        if not locked:
            raise ValueError("This benchmark job already has a runner.")
        try:
            _run_cases(pool, job_id, retry_uncertain)
        finally:
            lease.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (str(job_id),)
            )
            lease.commit()
    return report_job(pool, job_id)


def _run_cases(pool, job_id, retry_uncertain):
    with pool.connection() as connection:
        job = connection.execute(
            "SELECT * FROM benchmark_jobs WHERE id=%s FOR UPDATE", (job_id,)
        ).fetchone()
        if job is None:
            raise ValueError("Unknown benchmark job.")
        config = job["config_snapshot"]
        if (
            config.get("job_version") != "jobs-v1"
            or config.get("policy_version") != history.POLICY_VERSION
            or config.get("rubric_version") != evaluation.RUBRIC_VERSION
            or config.get("classifier_version") != analysis.POLICY_VERSION
        ):
            raise ValueError("Frozen job versions differ from the current runtime.")
        interrupted = connection.execute(
            "SELECT case_id, run_id, reserved_cost_usd FROM benchmark_cases "
            "WHERE job_id=%s AND state='running'",
            (job_id,),
        ).fetchall()
        for case in interrupted:
            known = connection.execute(
                "SELECT COALESCE(sum(cost_usd),0) AS cost FROM calls WHERE run_id=%s",
                (case["run_id"],),
            ).fetchone()["cost"]
            previous = {
                "run_id": str(case["run_id"]),
                "reserved_cost_usd": str(case["reserved_cost_usd"]),
                "known_cost_usd": str(known),
            }
            connection.execute(
                "UPDATE benchmark_cases SET state='uncertain', "
                "uncertain_attempts=uncertain_attempts || %s::jsonb "
                "WHERE job_id=%s AND case_id=%s",
                (Jsonb([previous]), job_id, case["case_id"]),
            )
            connection.execute(
                "UPDATE benchmark_jobs SET cost_complete=false, "
                "known_cost_usd=known_cost_usd+%s, budget_used_usd=budget_used_usd+%s "
                "WHERE id=%s",
                (known, max(0, known - case["reserved_cost_usd"]), job_id),
            )
        if retry_uncertain:
            connection.execute(
                "UPDATE benchmark_cases SET state='pending', "
                "result=NULL WHERE job_id=%s AND state='uncertain'",
                (job_id,),
            )
        connection.execute(
            "UPDATE benchmark_jobs SET status='running', "
            "started_at=COALESCE(started_at,now()), "
            "finished_at=NULL WHERE id=%s",
            (job_id,),
        )
    settings = Settings.model_validate(config["settings"])
    registry = ModelRegistry.model_validate(config["registry"])
    cases = validate_cases(job["dataset"])
    cap = settings.request_budget_usd
    if cap is None:
        raise ValueError("Frozen job has no request budget.")
    for case in cases:
        with pool.connection() as connection:
            current = connection.execute(
                "SELECT * FROM benchmark_jobs WHERE id=%s FOR UPDATE", (job_id,)
            ).fetchone()
            row = connection.execute(
                "SELECT state FROM benchmark_cases WHERE job_id=%s AND case_id=%s",
                (job_id, case.id),
            ).fetchone()
            if row["state"] != "pending":
                continue
            if current["budget_used_usd"] + cap > current["spend_ceiling_usd"]:
                break
            run_id = uuid4()
            connection.execute(
                "UPDATE benchmark_cases SET state='running', "
                "run_id=%s, attempts=attempts+1, "
                "reserved_cost_usd=%s WHERE job_id=%s AND case_id=%s",
                (run_id, cap, job_id, case.id),
            )
            connection.execute(
                "UPDATE benchmark_jobs SET "
                "budget_used_usd=budget_used_usd+%s WHERE id=%s",
                (cap, job_id),
            )
        result = run_chat(
            pool,
            run_id,
            ChatRequest(messages=case.messages),
            settings,
            registry,
            perf_counter(),
            history_snapshot=job["history_snapshot"],
            benchmark_job_id=job_id,
            run_mode="dev" if settings.mode == "live" else "mock",
        )
        complete = result.cost_complete and result.total_cost_usd is not None
        charge = result.total_cost_usd if complete else max(cap, result.known_cost_usd)
        summary = {
            "status": result.status,
            "final_model": result.final_model,
            "total_latency_ms": result.total_latency_ms,
            "total_cost_usd": str(result.total_cost_usd) if complete else None,
            "known_cost_usd": str(result.known_cost_usd),
            "cost_complete": complete,
            "error_category": result.error_category,
        }
        with pool.connection() as connection:
            connection.execute(
                "UPDATE benchmark_cases SET state=%s, result=%s WHERE "
                "job_id=%s AND case_id=%s",
                (
                    "error" if result.status == "error" else "done",
                    Jsonb(summary),
                    job_id,
                    case.id,
                ),
            )
            connection.execute(
                "UPDATE benchmark_jobs SET budget_used_usd=budget_used_usd+%s, "
                "known_cost_usd=known_cost_usd+%s, "
                "cost_complete=cost_complete AND %s WHERE id=%s",
                (charge - cap, result.known_cost_usd, complete, job_id),
            )
    with pool.connection() as connection:
        rows = connection.execute(
            "SELECT state FROM benchmark_cases WHERE job_id=%s", (job_id,)
        ).fetchall()
        states = {row["state"] for row in rows}
        status = (
            "uncertain"
            if "uncertain" in states
            else "blocked"
            if "pending" in states
            else "completed"
        )
        connection.execute(
            "UPDATE benchmark_jobs SET status=%s, finished_at=CASE "
            "WHEN %s='completed' THEN now() ELSE NULL END WHERE id=%s",
            (status, status, job_id),
        )


def main():
    parser = argparse.ArgumentParser(
        description="Sequential, bounded development benchmark jobs."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--dataset")
    benchmark.add_argument("--budget-usd")
    benchmark.add_argument("--request-budget-usd")
    benchmark.add_argument("--mock", action="store_true")
    benchmark.add_argument("--resume", type=UUID)
    benchmark.add_argument("--retry-uncertain", action="store_true")
    report = commands.add_parser("report")
    report.add_argument("job_id", type=UUID)
    args = parser.parse_args()
    try:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError("Set DATABASE_URL first.")
        with db.create_pool(url) as pool:
            if args.command == "report":
                output = report_job(pool, args.job_id)
            elif args.resume:
                if (
                    args.dataset
                    or args.budget_usd
                    or args.request_budget_usd
                    or args.mock
                ):
                    raise ValueError("Resume uses the frozen configuration.")
                output = run_job(pool, args.resume, args.retry_uncertain)
            else:
                if not args.dataset or not args.budget_usd or args.retry_uncertain:
                    raise ValueError("New jobs require dataset and total budget.")
                settings = load_settings()
                settings = Settings.model_validate(
                    settings.model_dump()
                    | {
                        "mode": "mock" if args.mock else "live",
                        "request_budget_usd": args.request_budget_usd
                        or settings.request_budget_usd,
                    }
                )
                registry = load_registry()
                snapshot = history.load_history(pool, registry)
                job_id = create_job(
                    pool,
                    read_cases(args.dataset),
                    settings,
                    registry,
                    snapshot,
                    args.budget_usd,
                )
                print(json.dumps({"job_id": str(job_id)}), flush=True)
                output = run_job(pool, job_id)
    except (ValueError, OSError, psycopg.Error, PoolTimeout):
        print(
            "Job stopped. Check arguments, frozen configuration, "
            "database, and budgets; resume requires the job ID."
        )
        return 2
    print(json.dumps(output, indent=2, default=str))
    return 0 if output["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
