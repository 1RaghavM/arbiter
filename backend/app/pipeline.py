from decimal import Decimal
from time import perf_counter

from app import analysis, db, providers
from app.config import config_version, fixed_model, model_status, reserve_cost
from app.routing import choose_route
from app.schemas import ChatResult, GenerationResult


def prepare_live(settings, registry, messages):
    model = fixed_model(settings, registry)
    reservation = reserve_cost(model, messages)
    if settings.request_budget_usd is None:
        raise ValueError("Set an explicit positive REQUEST_BUDGET_USD for live calls.")
    if reservation > settings.request_budget_usd:
        raise ValueError("The estimated call reservation exceeds REQUEST_BUDGET_USD.")
    return model, reservation


def run_chat(pool, run_id, body, settings, registry, started, *, fixed=False):
    model = None
    reservation = Decimal(0)
    classifier = None
    decisions = []
    error_category = None
    generation = None
    available = {m.key for m in registry.models if model_status(m) == "available"}
    if settings.mode == "live":
        if fixed:
            model, reservation = prepare_live(settings, registry, body.messages)
        elif settings.request_budget_usd is None:
            raise ValueError(
                "Set an explicit positive REQUEST_BUDGET_USD for live calls."
            )
        elif not available:
            raise ValueError("No generation provider has configured credentials.")
    db.create_run(pool, run_id, body, settings.mode, config_version(settings, registry))
    if settings.mode == "live" and not fixed:
        remaining = 90 - (perf_counter() - started)
        classifier = analysis.Analysis(
            source="fallback",
            cost_usd=Decimal(0),
            cost_source="estimated",
            error_category="budget",
        )
        # Reserve a viable generation before spending anything on classification.
        preflight = choose_route(
            classifier,
            registry,
            body.messages,
            available,
            settings.request_budget_usd - analysis.RESERVATION,
            remaining,
        )
        if preflight["selected_key"] and remaining > 0:
            classifier = analysis.classify(
                body.messages, min(settings.classification_timeout_seconds, remaining)
            )
        db.record_analysis(pool, run_id, classifier)
        spent = (
            classifier.cost_usd
            if classifier.cost_usd is not None
            else analysis.RESERVATION
        )
        reservation = analysis.RESERVATION if classifier.called else Decimal(0)
        decision = choose_route(
            classifier,
            registry,
            body.messages,
            available,
            settings.request_budget_usd - spent,
            90 - (perf_counter() - started),
        )
        decisions = [decision]
        model = next(
            (m for m in registry.models if m.key == decision["selected_key"]), None
        )
        if model:
            reservation += reserve_cost(model, body.messages)
        else:
            error_category = (
                "timeout"
                if 90 - (perf_counter() - started) <= 0
                else "no_eligible_model"
            )
    call_started = perf_counter()
    remaining = 90 - (call_started - started)
    if model:
        if remaining <= 0:
            error_category = "timeout"
        else:
            generation = providers.generate(
                model,
                body.messages,
                min(settings.generation_timeout_seconds, remaining),
            )
            generation.price_snapshot = {
                **(generation.price_snapshot or {}),
                "reserved_cost_usd": str(reserve_cost(model, body.messages)),
            }
        warnings = ["Live generation; no quality evaluator was called."]
    elif settings.mode == "mock":
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
    else:
        warnings = ["No generation model fits the remaining budget, time, and context."]
    if generation:
        generation.latency_ms = round((perf_counter() - call_started) * 1000)
        error_category = generation.error_category
        if generation.finish_reason == "length":
            warnings.append("Output reached its token limit and may be incomplete.")
    if classifier and classifier.source == "fallback":
        warnings.append(
            f"Classifier fallback: {classifier.error_category or 'uncertain'}."
        )
    costs = [call.cost_usd for call in [classifier, generation] if call is not None]
    complete = all(cost is not None for cost in costs)
    known = sum((cost for cost in costs if cost is not None), Decimal(0))
    if not complete:
        warnings.append(
            "Final API cost is unknown; the reservation is only an estimate."
        )
    result = ChatResult(
        run_id=run_id,
        mode=settings.mode,
        answer=generation.text if generation and not error_category else None,
        final_model=model.key
        if model
        else (generation.model_key if generation else None),
        status="error" if error_category else "unverified",
        analysis=classifier.model_dump(mode="json") if classifier else None,
        route_decisions=decisions,
        attempts=[generation] if generation else [],
        total_cost_usd=known if complete else None,
        known_cost_usd=known,
        cost_complete=complete,
        reserved_cost_usd=reservation,
        error_category=error_category,
        warnings=warnings,
    )
    error = (
        {"code": error_category, "message": "Request failed."}
        if error_category
        else None
    )
    db.finish_run(pool, result, generation, started, error)
    return result
