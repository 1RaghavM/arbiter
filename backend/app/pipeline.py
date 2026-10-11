from decimal import Decimal
from time import perf_counter

from app import db, providers
from app.config import config_version, fixed_model, reserve_cost
from app.schemas import ChatResult, GenerationResult


def prepare_live(settings, registry, messages):
    model = fixed_model(settings, registry)
    reservation = reserve_cost(model, messages)
    if settings.request_budget_usd is None:
        raise ValueError("Set an explicit positive REQUEST_BUDGET_USD for live calls.")
    if reservation > settings.request_budget_usd:
        raise ValueError("The estimated call reservation exceeds REQUEST_BUDGET_USD.")
    return model, reservation


def run_chat(pool, run_id, body, settings, registry, started):
    model = None
    reservation = Decimal(0)
    if settings.mode == "live":
        model, reservation = prepare_live(settings, registry, body.messages)
    db.create_run(pool, run_id, body, settings.mode, config_version(settings, registry))
    call_started = perf_counter()
    remaining = 90 - (call_started - started)
    if model:
        if remaining <= 0:
            generation = GenerationResult(
                model_key=model.key,
                provider=model.provider,
                model_id=model.model_id,
                text="",
                finish_reason="error",
                error_category="timeout",
                cost_usd=Decimal(0),
                cost_source="estimated",
            )
        else:
            generation = providers.generate(
                model,
                body.messages,
                min(settings.generation_timeout_seconds, remaining),
            )
        generation.price_snapshot = {
            **(generation.price_snapshot or {}),
            "reserved_cost_usd": str(reservation),
        }
        warnings = ["Live generation; no classifier or quality evaluator was called."]
    else:
        try:
            generation = providers.generate_mock(body.messages)
        except Exception:
            generation = GenerationResult(
                text="",
                error_category="generation_failed",
                cost_usd=Decimal(0),
                cost_source="estimated",
            )
        warnings = ["Mock output. No live model, classifier, or evaluator was called."]
    generation.latency_ms = round((perf_counter() - call_started) * 1000)
    error = None
    if generation.error_category:
        error = {"code": generation.error_category, "message": "Generation failed."}
    if generation.finish_reason == "length":
        warnings.append("Output reached its token limit and may be incomplete.")
    if generation.cost_usd is None:
        warnings.append(
            "Final API cost is unknown; the reservation is only an estimate."
        )
    result = ChatResult(
        run_id=run_id,
        mode=settings.mode,
        answer=generation.text if not error else None,
        final_model=generation.model_key,
        status="error" if error else "unverified",
        attempts=[generation],
        total_cost_usd=generation.cost_usd,
        known_cost_usd=generation.cost_usd or Decimal(0),
        cost_complete=generation.cost_usd is not None,
        reserved_cost_usd=reservation,
        warnings=warnings,
    )
    db.finish_run(pool, result, generation, started, error)
    return result
