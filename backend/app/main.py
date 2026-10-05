import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from pydantic import ValidationError

from app import db, providers
from app.schemas import ChatRequest, ChatResult, GenerationResult

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    url = os.environ.get("DATABASE_URL")
    app.state.pool = db.create_pool(url) if url else None
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
    started = request.state.started
    run_id = uuid4()
    request.state.run_id = run_id
    db.create_run(pool, run_id, body)
    call_started = perf_counter()
    error = None
    try:
        generation = providers.generate_mock(body.messages)
    except Exception:
        error = {"code": "generation_failed", "message": "Mock generation failed."}
        generation = GenerationResult(text="", error_category="generation_failed")
    generation.latency_ms = round((perf_counter() - call_started) * 1000)
    result = ChatResult(
        run_id=run_id,
        answer=generation.text if not error else None,
        final_model=generation.model_key,
        status="error" if error else "unverified",
        attempts=[generation],
        total_latency_ms=round((perf_counter() - started) * 1000),
        warnings=["Mock output. No live model, classifier, or evaluator was called."],
    )
    db.finish_run(pool, result, generation, started, error)
    if error:
        raise HTTPException(503, {**error, "run_id": str(run_id)})
    return result


@app.get("/api/runs")
def recent_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 20, pool=Depends(get_pool)
):
    return db.recent_runs(pool, limit)


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
