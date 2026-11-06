import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import JSONResponse, Response
from psycopg_pool import PoolTimeout
from pydantic import ValidationError

from app import db, history, jobs, summaries
from app.config import (
    Settings,
    load_environment,
    load_registry,
    load_settings,
    model_status,
)
from app.pipeline import run_chat
from app.schemas import ChatRequest, ChatResult

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    load_environment()
    url = os.environ.get("DATABASE_URL")
    app.state.pool = db.create_pool(url) if url else None
    app.state.benchmark_lock = Lock()
    yield
    if app.state.pool:
        app.state.pool.close()


app = FastAPI(title="Arbiter", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_error(request, error):
    return JSONResponse(status_code=error.status_code, content=error.detail)


@app.exception_handler(psycopg.Error)
@app.exception_handler(PoolTimeout)
async def database_error(request, error):
    run_id = getattr(request.state, "run_id", None)
    logger.error("Database operation failed; run_id=%s", run_id)
    return JSONResponse(
        status_code=503,
        content={
            "code": "persistence_error",
            "message": "Database unavailable. Run persistence could not be confirmed.",
            "run_id": str(run_id) if run_id else None,
        },
    )


def get_pool(request: Request):
    if request.app.state.pool is None:
        raise HTTPException(
            503,
            {
                "code": "database_unavailable",
                "message": "Configure DATABASE_URL first.",
                "run_id": None,
            },
        )
    return request.app.state.pool


async def read_chat(request: Request):
    request.state.started = perf_counter()
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 160000:
            raise HTTPException(
                422,
                {
                    "code": "invalid_input",
                    "message": "Request body is too large.",
                    "run_id": None,
                },
            )
    try:
        return ChatRequest.model_validate_json(body)
    except ValidationError:
        raise HTTPException(
            422,
            {
                "code": "invalid_input",
                "message": "Send 1–10 nonblank user/assistant messages, "
                "ending with a user message, with at most 12,000 characters "
                "of valid text in total.",
                "run_id": None,
            },
        ) from None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResult)
def chat(
    request: Request,
    body: Annotated[ChatRequest, Depends(read_chat)],
    pool=Depends(get_pool),
):
    settings, registry = runtime_config()
    run_id = uuid4()
    request.state.run_id = run_id
    try:
        result = run_chat(pool, run_id, body, settings, registry, request.state.started)
    except ValueError as error:
        raise HTTPException(
            503,
            {
                "code": "configuration_or_budget",
                "message": str(error),
                "run_id": None,
            },
        ) from None
    if result.status == "error":
        category = result.error_category
        status = {
            "timeout": 504,
            "invalid_request": 422,
            "malformed_response": 502,
            "empty_response": 502,
            "blocked": 502,
        }.get(category, 503)
        raise HTTPException(
            status,
            {
                "code": category,
                "message": "Generation failed; retry is a new request.",
                "run_id": str(run_id),
            },
        )
    return result


def runtime_config():
    try:
        return load_settings(), load_registry()
    except (ValueError, OSError):
        raise HTTPException(
            503,
            {
                "code": "invalid_configuration",
                "message": "Check the server model configuration and request limits.",
                "run_id": None,
            },
        ) from None


@app.get("/api/config")
def public_config():
    settings, registry = runtime_config()
    return {
        "mode": settings.mode,
        "model_key": None,
        "selection": "routed",
        "providers": [
            {
                "key": m.key,
                "provider": m.provider,
                "model_id": m.model_id,
                "status": model_status(m),
            }
            for m in registry.models
        ],
    }


@app.get("/api/runs")
def recent_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    pool=Depends(get_pool),
):
    return db.recent_runs(pool, limit, offset)


@app.get("/api/runs/{run_id}")
def read_run(run_id: UUID, pool=Depends(get_pool)):
    run = db.read_run(pool, run_id)
    if run is None:
        raise HTTPException(
            404,
            {
                "code": "not_found",
                "message": "Run not found.",
                "run_id": str(run_id),
            },
        )
    return run


@app.get("/api/benchmarks")
def recent_benchmarks(
    limit: Annotated[int, Query(ge=1, le=100)] = 20, pool=Depends(get_pool)
):
    return jobs.recent_jobs(pool, limit)


def benchmark_config():
    settings, registry = runtime_config()
    try:
        budget = Settings(
            request_budget_usd=os.environ.get("BENCHMARK_BUDGET_USD")
        ).request_budget_usd
        if budget is None or settings.request_budget_usd is None:
            raise ValueError()
        if settings.mode == "live" and not any(
            model_status(model) == "available" for model in registry.models
        ):
            raise ValueError()
    except ValueError:
        raise HTTPException(
            503,
            {
                "code": "benchmark_configuration",
                "message": "Configure positive BENCHMARK_BUDGET_USD and "
                "REQUEST_BUDGET_USD limits and live model credentials on the server.",
            },
        ) from None
    return settings, registry, budget


@app.get("/api/benchmarks/config")
def public_benchmark_config():
    settings, _, budget = benchmark_config()
    return {
        "mode": settings.mode,
        "budget_usd": str(budget),
        "request_budget_usd": str(settings.request_budget_usd),
    }


def run_background_benchmark(pool, job_id, lock):
    try:
        jobs.run_job(pool, job_id)
    except Exception:
        logger.error("Benchmark interrupted; job_id=%s", job_id)
        try:
            with pool.connection() as connection:
                connection.execute(
                    "UPDATE benchmark_jobs SET status='uncertain' WHERE id=%s",
                    (job_id,),
                )
        except (psycopg.Error, PoolTimeout):
            logger.error("Could not save interrupted benchmark; job_id=%s", job_id)
    finally:
        lock.release()


@app.post("/api/benchmarks", status_code=202)
def start_benchmark(
    request: Request,
    background_tasks: BackgroundTasks,
    x_arbiter_benchmark: Annotated[str, Header()],
    pool=Depends(get_pool),
):
    # A custom header requires a preflight for cross-origin browser requests.
    if x_arbiter_benchmark != "start":
        raise HTTPException(422, {"message": "Invalid benchmark start request."})
    settings, registry, budget = benchmark_config()
    lock = request.app.state.benchmark_lock
    if not lock.acquire(blocking=False):
        raise HTTPException(409, {"message": "A benchmark is already running."})
    try:
        cases = jobs.read_cases(
            Path(__file__).resolve().parents[2] / "benchmarks/dev.jsonl"
        )
        job_id = jobs.create_job(
            pool,
            cases,
            settings,
            registry,
            history.load_history(pool, registry),
            budget,
        )
        background_tasks.add_task(run_background_benchmark, pool, job_id, lock)
    except Exception:
        lock.release()
        raise
    return {"job_id": str(job_id)}


@app.get("/api/benchmarks/{job_id}")
def read_benchmark(job_id: UUID, pool=Depends(get_pool)):
    try:
        return jobs.report_job(pool, job_id)
    except ValueError:
        raise HTTPException(
            404,
            {
                "code": "not_found",
                "message": "Benchmark job not found.",
                "run_id": None,
            },
        ) from None


async def read_summary(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 10000:
            summaries.fail(422, "Summary selection is too large.")
    try:
        return summaries.SummaryRequest.model_validate_json(body)
    except ValidationError:
        summaries.fail(422, "Select between 1 and 100 valid run IDs.")


@app.post("/api/run-summaries")
def create_summary(
    body: Annotated[summaries.SummaryRequest, Depends(read_summary)],
    pool=Depends(get_pool),
):
    settings, registry = runtime_config()
    return Response(
        summaries.summarize(pool, body, settings, registry),
        media_type="text/markdown",
        headers={
            "Content-Disposition": 'attachment; filename="arbiter-run-summary.md"'
        },
    )
