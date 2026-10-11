from decimal import Decimal
from time import perf_counter

from app import analysis, db, evaluation, providers
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


def _route(
    classifier, registry, messages, available, budget, remaining, judge_cost, judge_time
):
    decision = choose_route(
        classifier,
        registry,
        messages,
        available,
        budget - judge_cost,
        remaining - judge_time,
    )
    decision["evaluation_reserved"] = (
        decision["selected_key"] is not None and judge_time > 0
    )
    return decision


def run_chat(pool, run_id, body, settings, registry, started, *, fixed=False):
    classifier = None
    decisions, attempts, grades, answers, calls, warnings = [], [], [], [], [], []
    spent = reserved = Decimal(0)
    sequence = 0
    error_category = None
    escalation_reason = None
    models = {model.key: model for model in registry.models}
    available = {m.key for m in registry.models if model_status(m) == "available"}
    model = judge = None
    judge_cost = Decimal(0)
    judge_time = 0
    judge_error = "judge_unavailable"
    if settings.mode == "live":
        if fixed:
            model, _ = prepare_live(settings, registry, body.messages)
        elif settings.request_budget_usd is None:
            raise ValueError(
                "Set an explicit positive REQUEST_BUDGET_USD for live calls."
            )
        elif not available:
            raise ValueError("No generation provider has configured credentials.")
        if not fixed and registry.judge_key in available:
            judge = models[registry.judge_key]
            try:
                judge_cost = evaluation.reservation(judge, body.messages)
                judge_time = settings.evaluation_timeout_seconds
            except ValueError:
                judge_error = "judge_context_or_configuration"
                judge = None
    db.create_run(pool, run_id, body, settings.mode, config_version(settings, registry))

    def record(stage, attempt, call, cap, grade=None):
        nonlocal sequence, spent, reserved
        sequence += 1
        call.price_snapshot = {
            **(call.price_snapshot or {}),
            "reserved_cost_usd": str(cap),
        }
        db.record_call(pool, run_id, sequence, stage, attempt, call, grade)
        calls.append(call)
        reserved += cap
        spent += call.cost_usd if call.cost_usd is not None else cap

    if settings.mode == "mock":
        try:
            generation = providers.generate_mock(body.messages)
        except Exception:
            generation = GenerationResult(
                text="",
                error_category="generation_failed",
                cost_usd=Decimal(0),
                cost_source="estimated",
            )
        record("generate", 1, generation, Decimal(0))
        attempts.append(generation)
        error_category = generation.error_category
        if not error_category:
            answers.append((generation, evaluation.Evaluation(), 1))
        warnings.append(
            "Mock output. No live model, classifier, or evaluator was called."
        )
    else:
        if not fixed:
            remaining = 90 - (perf_counter() - started)
            classifier = analysis.Analysis(error_category="budget")
            preflight = _route(
                classifier,
                registry,
                body.messages,
                available,
                settings.request_budget_usd - analysis.RESERVATION,
                remaining - settings.classification_timeout_seconds,
                judge_cost,
                judge_time,
            )
            if preflight["selected_key"] and remaining > 0:
                classifier = analysis.classify(
                    body.messages,
                    min(settings.classification_timeout_seconds, remaining),
                )
            db.record_analysis(pool, run_id, classifier)
            if classifier.called:
                sequence = 1
                calls.append(classifier)
                reserved += analysis.RESERVATION
                spent += (
                    classifier.cost_usd
                    if classifier.cost_usd is not None
                    else analysis.RESERVATION
                )
            if classifier.source == "fallback":
                warnings.append(
                    f"Classifier fallback: {classifier.error_category or 'uncertain'}."
                )
        retry_rank = None
        strict_rank = False
        retry_reason = None
        for attempt in range(1, 2 if fixed else 3):
            remaining = 90 - (perf_counter() - started)
            if not fixed:
                candidates = available - {item.model_key for item in attempts}
                if retry_rank is not None:
                    candidates = {
                        key
                        for key in candidates
                        if models[key].capability_rank is not None
                        and (
                            models[key].capability_rank > retry_rank
                            if strict_rank
                            else models[key].capability_rank >= retry_rank
                        )
                    }
                decision = _route(
                    classifier,
                    registry,
                    body.messages,
                    candidates,
                    settings.request_budget_usd - spent,
                    remaining,
                    judge_cost,
                    judge_time,
                )
                if attempt == 2 and decision["selected_key"]:
                    eligible = [c for c in decision["candidates"] if c["eligible"]]
                    chosen = min(
                        eligible,
                        key=lambda c: (
                            -c["quality"],
                            Decimal(c["estimated_cost_usd"]),
                            c["key"],
                        ),
                    )
                    decision["selected_key"] = chosen["key"]
                    decision["reason"] = (
                        "Escalation: highest quality prior among eligible ranks."
                    )
                decisions.append(decision)
                model = models.get(decision["selected_key"])
                eval_reserved = decision["evaluation_reserved"]
            else:
                eval_reserved = False
            if not model or remaining <= 0:
                if remaining <= 0:
                    error_category = "timeout"
                elif error_category is None:
                    error_category = "no_eligible_model"
                if attempt == 2:
                    warnings.append(
                        "Escalation skipped: no model fits the remaining limits."
                    )
                break
            if attempt == 2:
                escalation_reason = retry_reason
            cap = reserve_cost(model, body.messages)
            timeout = min(
                settings.generation_timeout_seconds,
                remaining - judge_time if eval_reserved else remaining,
            )
            generation = providers.generate(model, body.messages, timeout)
            attempts.append(generation)
            record("generate", attempt, generation, cap)
            error_category = generation.error_category
            if fixed:
                if not error_category:
                    answers.append((generation, evaluation.Evaluation(), attempt))
                warnings.append(
                    "Fixed provider smoke; classifier and evaluator skipped."
                )
                break
            if error_category and error_category != "empty_response":
                if (
                    error_category in {"timeout", "rate_limit", "unavailable"}
                    and attempt == 1
                ):
                    retry_rank = model.capability_rank
                    retry_reason = f"generation_{error_category}"
                    continue
                break
            remaining = 90 - (perf_counter() - started)
            judge_call = None
            judge_cap = Decimal(0)
            if generation.finish_reason == "length" or not generation.text.strip():
                grade, judge_call = evaluation.evaluate(
                    judge, body.messages, generation, 0
                )
            elif judge is None:
                grade = evaluation.Evaluation(
                    reason="The fixed judge is unavailable.", error_category=judge_error
                )
            else:
                try:
                    judge_cap = evaluation.reservation(
                        judge, body.messages, generation.text
                    )
                except ValueError:
                    grade = evaluation.Evaluation(
                        reason="Answer exceeds the judge context or output bound.",
                        error_category="context_limit",
                    )
                else:
                    if (
                        judge_cap > settings.request_budget_usd - spent
                        or remaining <= 0
                    ):
                        grade = evaluation.Evaluation(
                            reason="Evaluation skipped: budget or time exhausted.",
                            error_category="budget" if remaining > 0 else "timeout",
                        )
                    else:
                        grade, judge_call = evaluation.evaluate(
                            judge,
                            body.messages,
                            generation,
                            min(settings.evaluation_timeout_seconds, remaining),
                        )
            if judge_call is not None:
                record("evaluate", attempt, judge_call, judge_cap, grade)
            grades.append(
                {
                    **grade.model_dump(mode="json"),
                    "attempt": attempt,
                    "model_key": generation.model_key,
                }
            )
            if generation.text.strip() and generation.error_category is None:
                answers.append((generation, grade, attempt))
            if grade.status == "unknown":
                warnings.append(
                    f"Unverified: {grade.error_category or 'evaluation_unknown'}."
                )
                break
            if grade.status == "pass":
                break
            if generation.finish_reason == "length":
                warnings.append("Output reached its token limit and may be incomplete.")
            retry_rank = model.capability_rank
            strict_rank = True
            retry_reason = "quality_failed"

    selected = None
    status = "error"
    if answers:
        if answers[-1][1].status in {"pass", "unknown"}:
            selected = answers[-1]
        else:
            selected = max(
                answers,
                key=lambda item: (
                    min(
                        item[1].correctness or 0,
                        item[1].relevance or 0,
                        item[1].completeness or 0,
                    ),
                    sum(
                        score or 0
                        for score in (
                            item[1].correctness,
                            item[1].relevance,
                            item[1].completeness,
                        )
                    ),
                    item[2],
                ),
            )
        status = {"pass": "passed", "fail": "quality_failed", "unknown": "unverified"}[
            selected[1].status
        ]
        error_category = None
    costs = [call.cost_usd for call in calls]
    complete = all(cost is not None for cost in costs)
    known = sum((cost for cost in costs if cost is not None), Decimal(0))
    if not complete:
        warnings.append(
            "Final API cost is unknown; the reservation is only an estimate."
        )
    result = ChatResult(
        run_id=run_id,
        mode=settings.mode,
        answer=selected[0].text if selected else None,
        final_model=selected[0].model_key
        if selected
        else (attempts[-1].model_key if attempts else None),
        status=status,
        analysis=classifier.model_dump(mode="json") if classifier else None,
        route_decisions=decisions,
        attempts=attempts,
        evaluations=grades,
        total_cost_usd=known if complete else None,
        known_cost_usd=known,
        cost_complete=complete,
        reserved_cost_usd=reserved,
        error_category=error_category or ("empty_response" if not selected else None),
        escalation_reason=escalation_reason,
        warnings=warnings,
    )
    error = (
        {"code": result.error_category, "message": "Request failed."}
        if result.error_category
        else None
    )
    db.finish_run(pool, result, None, started, error)
    return result
