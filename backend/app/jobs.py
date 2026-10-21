import argparse
import hashlib
import json
import os
import random
import subprocess
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import PoolTimeout
from pydantic import Field

from app import analysis, db, evaluation, history
from app.config import (
    ModelRegistry,
    Settings,
    config_version,
    load_environment,
    load_registry,
    load_settings,
    model_status,
)
from app.pipeline import run_chat
from app.schemas import ChatRequest, ChatResult, GenerationResult


class BenchmarkCase(ChatRequest):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    split: Literal["dev"]
    rubric: str = Field(min_length=1, max_length=2000)
    expected_answer: str | None = Field(default=None, max_length=2000)


def validate_cases(rows):
    from app.grading import ExperimentCase

    cases = [
        (ExperimentCase if "task" in row else BenchmarkCase).model_validate(row)
        for row in rows
    ]
    if any(case.split != "dev" for case in cases):
        raise ValueError("Development jobs reject held-out cases.")
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


def create_job(
    pool, cases, settings, registry, history_snapshot, budget, *, comparison=None
):
    budget = Settings(request_budget_usd=budget).request_budget_usd
    if settings.request_budget_usd is None:
        raise ValueError(
            "Configure a positive per-request budget before creating a job."
        )
    if comparison is None:
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
    if comparison is not None:
        config.update(comparison)
    order = [(case.id, "routed") for case in cases]
    if comparison is not None:
        rng = random.Random(comparison["seed"])
        rng.shuffle(order)
        order = [
            (case_id, strategy)
            for case_id, _ in order
            for strategy in rng.sample(["fixed-cheap", "fixed-strong", "routed"], 3)
        ]
    tasks = [(case_id, strategy, "runtime") for case_id, strategy in order]
    if comparison is not None:
        grading_order = order.copy()
        rng.shuffle(grading_order)
        tasks += [(case_id, strategy, "grading") for case_id, strategy in grading_order]
    with pool.connection() as connection:
        connection.execute(
            "INSERT INTO benchmark_jobs (id, dataset_hash, dataset, config_snapshot, "
            "history_snapshot, spend_ceiling_usd, strategy) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                job_id,
                digest,
                Jsonb(dataset),
                Jsonb(config),
                Jsonb(history_snapshot),
                budget,
                "comparison" if comparison is not None else "routed",
            ),
        )
        for ordinal, (case_id, strategy, stage) in enumerate(tasks):
            connection.execute(
                "INSERT INTO benchmark_cases (job_id, case_id, "
                "ordinal, strategy, stage) VALUES (%s,%s,%s,%s,%s)",
                (job_id, case_id, ordinal, strategy, stage),
            )
    return job_id


def create_comparison(
    pool, cases, settings, registry, history_snapshot, budget, scorer_key, seed=17
):
    from app import grading

    cases = grading.validate_cases([case.model_dump(mode="json") for case in cases])
    if any(case.split != "heldout" for case in cases):
        raise ValueError("Comparison requires held-out cases only.")
    models = {model.key: model for model in registry.models}
    keys = [registry.cheap_baseline_key, registry.strong_baseline_key, scorer_key]
    if any(key not in models for key in keys):
        raise ValueError("Configure both baseline models and a scoring model.")
    if not models[scorer_key].enabled or models[scorer_key].provider != "anthropic":
        raise ValueError("Independent rubric grading requires enabled Anthropic.")
    if settings.mode == "live" and any(
        model_status(models[key]) != "available" for key in keys
    ):
        raise ValueError("Baseline and scoring credentials are required.")
    return create_job(
        pool,
        cases,
        settings,
        registry,
        history_snapshot,
        budget,
        comparison={
            "seed": seed,
            "scorer_key": scorer_key,
            "scoring_version": grading.SCORING_VERSION,
            "comparison_version": "comparison-v1",
            "runtime_fingerprint": runtime_fingerprint(),
            "source_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).parents[2],
                text=True,
            ).strip(),
            "targets": {
                "quality_margin_pp": 5,
                "cost_savings": 0.20,
                "latency_savings": 0.15,
            },
        },
    )


def runtime_fingerprint():
    root = Path(__file__).parent
    paths = [
        root / f"{name}.py"
        for name in (
            "jobs",
            "grading",
            "pipeline",
            "providers",
            "analysis",
            "evaluation",
            "routing",
            "history",
            "config",
            "schemas",
            "db",
        )
    ] + [root.parent / "uv.lock"]
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()


def report_job(pool, job_id):
    with pool.connection() as connection:
        job = connection.execute(
            "SELECT * FROM benchmark_jobs WHERE id=%s", (job_id,)
        ).fetchone()
        if job is None:
            raise ValueError("Unknown benchmark job.")
        cases = connection.execute(
            "SELECT ordinal, case_id, strategy, stage, state, run_id, attempts, "
            "reserved_cost_usd, result, "
            "uncertain_attempts "
            "FROM benchmark_cases WHERE job_id=%s ORDER BY ordinal",
            (job_id,),
        ).fetchall()
        partial = connection.execute(
            "SELECT b.ordinal, b.stage, b.reserved_cost_usd, "
            "COALESCE(sum(c.cost_usd),0) AS known "
            "FROM benchmark_cases b LEFT JOIN calls c ON c.run_id=b.run_id "
            "WHERE b.job_id=%s AND b.state='running' "
            "GROUP BY b.ordinal,b.stage,b.reserved_cost_usd",
            (job_id,),
        ).fetchall()
    partial_by_ordinal = {row["ordinal"]: row for row in partial}
    for case in cases:
        if case["state"] == "running":
            case["result"] = {
                "known_cost_usd": str(partial_by_ordinal[case["ordinal"]]["known"]),
                "total_cost_usd": None,
                "cost_complete": False,
                "total_latency_ms": None,
            }
    pending_cost = sum(row["known"] for row in partial if row["stage"] == "runtime")
    pending_scoring = sum(row["known"] for row in partial if row["stage"] == "grading")
    runtime = [case for case in cases if case["stage"] == "runtime"]
    scoring = [case for case in cases if case["stage"] == "grading"]
    pending_overage = sum(
        max(0, row["known"] - row["reserved_cost_usd"]) for row in partial
    )
    report = {
        "job_id": str(job_id),
        "created_at": job["created_at"].isoformat(),
        "status": job["status"],
        "strategy": job["strategy"],
        "mode": job["config_snapshot"]["settings"]["mode"],
        "dataset_hash": job["dataset_hash"],
        "history_snapshot_id": job["history_snapshot"].get("id"),
        "budget_usd": str(job["spend_ceiling_usd"]),
        "budget_used_usd": str(job["budget_used_usd"] + pending_overage),
        "known_cost_usd": str(job["known_cost_usd"] + pending_cost),
        "cost_complete": job["cost_complete"]
        and not any(case["state"] in {"running", "uncertain"} for case in runtime),
        "scoring_known_cost_usd": str(job["scoring_known_cost_usd"] + pending_scoring),
        "scoring_cost_complete": job["scoring_cost_complete"]
        and not any(case["state"] in {"running", "uncertain"} for case in scoring),
        "quality_basis": (
            "Independent held-out grading; online pass count is not benchmark quality."
            if job["strategy"] == "comparison"
            else "Online judge proxy only; no independent benchmark grading."
        ),
        "case_count": len(runtime),
        "states": {
            state: sum(case["state"] == state for case in runtime)
            for state in ("pending", "running", "done", "error", "uncertain")
        },
        "online_pass_count": sum(
            (case["result"] or {}).get("status") == "passed" for case in runtime
        ),
        "cases": cases,
    }
    if job["strategy"] == "comparison":
        from app.comparison_report import build_report

        metrics = build_report(
            report
            | {
                "dataset": job["dataset"],
                "config_snapshot": job["config_snapshot"],
            }
        )
        report["strategy_metrics"] = metrics["strategies"]
    return report


def experiment_export(pool, job_id):
    report = report_job(pool, job_id)
    with pool.connection() as connection:
        frozen = connection.execute(
            "SELECT dataset, config_snapshot, history_snapshot "
            "FROM benchmark_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
    return report | frozen


def recent_jobs(pool, limit):
    with pool.connection() as connection:
        rows = connection.execute(
            "SELECT id FROM benchmark_jobs ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    summaries = []
    for row in rows:
        summary = report_job(pool, row["id"])
        del summary["cases"]
        summaries.append(summary)
    return summaries


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
        comparison = job["strategy"] == "comparison"
        if comparison:
            from app import grading

            if (
                config.get("scoring_version") != grading.SCORING_VERSION
                or config.get("comparison_version") != "comparison-v1"
                or config.get("runtime_fingerprint") != runtime_fingerprint()
            ):
                raise ValueError("Frozen scoring versions differ from the runtime.")
        settings = Settings.model_validate(config["settings"])
        registry = ModelRegistry.model_validate(config["registry"])
        cases = (
            grading.validate_cases(job["dataset"])
            if comparison
            else validate_cases(job["dataset"])
        )
        if settings.request_budget_usd is None:
            raise ValueError("Frozen job has no request budget.")
        interrupted = connection.execute(
            "SELECT ordinal, stage, run_id, reserved_cost_usd FROM benchmark_cases "
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
                "WHERE job_id=%s AND ordinal=%s",
                (Jsonb([previous]), job_id, case["ordinal"]),
            )
            prefix = "scoring_" if case["stage"] == "grading" else ""
            connection.execute(
                f"UPDATE benchmark_jobs SET {prefix}cost_complete=false, "
                f"{prefix}known_cost_usd={prefix}known_cost_usd+%s, "
                "budget_used_usd=budget_used_usd+%s "
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
        tasks = connection.execute(
            "SELECT * FROM benchmark_cases WHERE job_id=%s ORDER BY ordinal",
            (job_id,),
        ).fetchall()
    cases = {case.id: case for case in cases}
    for task in tasks:
        if task["state"] != "pending":
            continue
        case = cases[task["case_id"]]
        cap = settings.request_budget_usd
        generation = scorer = None
        grading_error = None
        if task["stage"] == "grading":
            with pool.connection() as connection:
                source = connection.execute(
                    "SELECT result FROM benchmark_cases WHERE job_id=%s "
                    "AND case_id=%s AND strategy=%s AND stage='runtime' "
                    "AND state IN ('done','error')",
                    (job_id, case.id, task["strategy"]),
                ).fetchone()
            if source is None:
                continue
            source = source["result"]
            generation = GenerationResult(
                text=source.get("answer") or "",
                provider=source.get("provider", "unknown"),
                finish_reason=source.get("finish_reason") or "error",
                error_category=source.get("error_category"),
            )
            scorer = next(m for m in registry.models if m.key == config["scorer_key"])
            try:
                cap = (
                    grading.grade_reservation(case, generation, scorer)
                    if settings.mode == "live"
                    else Decimal(0)
                )
            except ValueError:
                cap = Decimal(0)
                grading_error = "Scoring input or configuration exceeds grading limits."
        with pool.connection() as connection:
            current = connection.execute(
                "SELECT * FROM benchmark_jobs WHERE id=%s FOR UPDATE", (job_id,)
            ).fetchone()
            if current["budget_used_usd"] + cap > current["spend_ceiling_usd"]:
                continue
            run_id = uuid4()
            connection.execute(
                "UPDATE benchmark_cases SET state='running', "
                "run_id=%s, attempts=attempts+1, "
                "reserved_cost_usd=%s WHERE job_id=%s AND ordinal=%s",
                (run_id, cap, job_id, task["ordinal"]),
            )
            connection.execute(
                "UPDATE benchmark_jobs SET "
                "budget_used_usd=budget_used_usd+%s WHERE id=%s",
                (cap, job_id),
            )
        if task["stage"] == "grading":
            summary = _grade(
                pool,
                job_id,
                run_id,
                case,
                generation,
                scorer,
                settings,
                registry,
                cap,
                grading_error,
            )
        else:
            summary = _generate(pool, job, task, run_id, case, settings, registry)
        complete = summary["cost_complete"] and summary["total_cost_usd"] is not None
        known = Decimal(summary["known_cost_usd"])
        charge = Decimal(summary["total_cost_usd"]) if complete else max(cap, known)
        with pool.connection() as connection:
            connection.execute(
                "UPDATE benchmark_cases SET state=%s, result=%s WHERE "
                "job_id=%s AND ordinal=%s",
                (
                    "error" if summary["status"] == "error" else "done",
                    Jsonb(summary),
                    job_id,
                    task["ordinal"],
                ),
            )
            prefix = "scoring_" if task["stage"] == "grading" else ""
            connection.execute(
                "UPDATE benchmark_jobs SET budget_used_usd=budget_used_usd+%s, "
                f"{prefix}known_cost_usd={prefix}known_cost_usd+%s, "
                f"{prefix}cost_complete={prefix}cost_complete AND %s WHERE id=%s",
                (charge - cap, known, complete, job_id),
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


def _generate(pool, job, task, run_id, case, settings, registry):
    fixed = task["strategy"] != "routed"
    if fixed:
        settings = settings.model_copy(
            update={
                "fixed_model_key": (
                    registry.cheap_baseline_key
                    if task["strategy"] == "fixed-cheap"
                    else registry.strong_baseline_key
                )
            }
        )
    comparison = job["strategy"] == "comparison"
    result = run_chat(
        pool,
        run_id,
        ChatRequest(messages=case.messages),
        settings,
        registry,
        perf_counter(),
        fixed=fixed,
        history_snapshot=job["history_snapshot"],
        benchmark_job_id=job["id"],
        run_mode="baseline" if fixed else "heldout" if comparison else "dev",
    )
    complete = result.cost_complete and result.total_cost_usd is not None
    summary = {
        "status": result.status,
        "final_model": result.final_model,
        "total_latency_ms": result.total_latency_ms,
        "total_cost_usd": str(result.total_cost_usd) if complete else None,
        "known_cost_usd": str(result.known_cost_usd),
        "cost_complete": complete,
        "error_category": result.error_category,
    }
    if comparison:
        final = next(
            (
                attempt
                for attempt in reversed(result.attempts)
                if attempt.model_key == result.final_model
            ),
            None,
        )
        summary.update(
            {
                "answer": result.answer,
                "provider": final.provider if final else "unknown",
                "finish_reason": final.finish_reason if final else "error",
                "first_model": result.attempts[0].model_key
                if result.attempts
                else None,
                "escalated": len(result.attempts) > 1,
            }
        )
    return summary


def _grade(
    pool,
    job_id,
    run_id,
    case,
    generation,
    scorer,
    settings,
    registry,
    cap,
    grading_error=None,
):
    from app import grading

    started = perf_counter()
    db.create_run(
        pool,
        run_id,
        ChatRequest(messages=case.messages),
        "mock" if settings.mode == "mock" else "scoring",
        config_version(settings, registry),
        job_id,
    )
    if grading_error:
        grade, call = (
            {
                "status": "unknown",
                "reason": grading_error,
                "basis": case.grading,
                "scorer_version": grading.SCORING_VERSION,
                "error_category": "input_limit",
            },
            None,
        )
    elif settings.mode == "mock" and case.grading == "rubric":
        grade, call = (
            {
                "status": "unknown",
                "reason": "Mock job; no scoring provider called.",
                "basis": "rubric",
                "scorer_version": grading.SCORING_VERSION,
            },
            None,
        )
    else:
        grade, call = grading.grade_case(
            case,
            generation,
            scorer,
            settings.evaluation_timeout_seconds,
        )
    if call is not None:
        call.price_snapshot = {
            **(call.price_snapshot or {}),
            "reserved_cost_usd": str(cap),
        }
        db.record_call(pool, run_id, 1, "score", 1, call, grade)
    cost = call.cost_usd if call is not None else Decimal(0)
    complete = cost is not None
    known = cost if complete else Decimal(0)
    result = ChatResult(
        run_id=run_id,
        mode=settings.mode,
        status="unverified",
        total_cost_usd=cost,
        known_cost_usd=known,
        cost_complete=complete,
        reserved_cost_usd=cap,
    )
    db.finish_run(pool, result, None, started)
    return grade | {
        "total_cost_usd": str(cost) if complete else None,
        "known_cost_usd": str(known),
        "cost_complete": complete,
    }


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
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--dataset", required=True)
    freeze.add_argument("--budget-usd", required=True)
    freeze.add_argument("--request-budget-usd", required=True)
    freeze.add_argument("--scorer", required=True)
    freeze.add_argument("--seed", type=int, default=17)
    freeze.add_argument("--mock", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("job_id", type=UUID)
    export.add_argument("--output", required=True)
    export.add_argument("--manual-reviews")
    args = parser.parse_args()
    load_environment()
    try:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise ValueError("Set DATABASE_URL first.")
        with db.create_pool(url) as pool:
            if args.command == "report":
                output = report_job(pool, args.job_id)
            elif args.command == "export":
                from app.comparison_report import write_report

                write_report(
                    experiment_export(pool, args.job_id),
                    args.output,
                    manual_reviews=json.loads(Path(args.manual_reviews).read_text())
                    if args.manual_reviews
                    else None,
                )
                return 0
            elif args.command == "freeze":
                from app import grading

                settings = load_settings().model_copy(
                    update={
                        "mode": "mock" if args.mock else "live",
                        "request_budget_usd": Settings(
                            request_budget_usd=args.request_budget_usd,
                        ).request_budget_usd,
                    }
                )
                registry = load_registry()
                cases = grading.read_cases(args.dataset)
                if len(cases) != 30:
                    raise ValueError("Final comparison requires 30 held-out cases.")
                job_id = create_comparison(
                    pool,
                    cases,
                    settings,
                    registry,
                    history.load_history(pool, registry),
                    args.budget_usd,
                    args.scorer,
                    args.seed,
                )
                print(json.dumps({"job_id": str(job_id), "status": "frozen"}))
                return 0
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
