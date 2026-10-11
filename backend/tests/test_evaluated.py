from decimal import Decimal
from time import perf_counter
from uuid import uuid4

import pytest

from app import analysis, evaluation, pipeline
from app.config import ModelConfig, ModelRegistry, Settings
from app.schemas import ChatRequest, GenerationResult

BODY = ChatRequest(
    messages=[
        {"role": "user", "content": "Remember blue."},
        {"role": "assistant", "content": "Understood."},
        {"role": "user", "content": "Which color?"},
    ]
)


def make_model(key, price, rank):
    return ModelConfig(
        key=key,
        provider="anthropic" if key == "judge" else "openai",
        model_id="offline",
        enabled=True,
        context_limit=200000,
        input_usd_per_million=price,
        output_usd_per_million=price,
        price_verified_at="2026-10-11",
        source_url="https://example.com",
        prior_quality={} if key == "judge" else {"easy": 0.9, "hard": 0.9},
        prior_latency_ms=1000,
        capability_rank=rank,
    )


def grade(status, scores=None):
    scores = scores or ((4, 4, 4) if status == "pass" else (2, 2, 2))
    return evaluation.Evaluation(
        status=status,
        correctness=scores[0],
        relevance=scores[1],
        completeness=scores[2],
        error_category="judge_timeout" if status == "unknown" else None,
    )


@pytest.fixture
def setup(monkeypatch):
    events, gen_results, judge_results = [], [], []
    registry = ModelRegistry(
        models=[
            make_model("cheap", "1", 1),
            make_model("strong", "2", 2),
            make_model("judge", "2", 3),
        ],
        strong_baseline_key="strong",
        judge_key="judge",
    )
    settings = Settings(mode="live", fixed_model_key="cheap", request_budget_usd="1")
    monkeypatch.setattr(pipeline, "model_status", lambda m: "available")
    monkeypatch.setattr(
        pipeline.history, "load_history", lambda *a: {"id": "offline", "entries": []}
    )
    monkeypatch.setattr(pipeline.db, "create_run", lambda *a: events.append("create"))
    monkeypatch.setattr(
        pipeline.db, "record_analysis", lambda *a: events.append("record_classify")
    )
    monkeypatch.setattr(
        pipeline.db,
        "record_call",
        lambda p, r, seq, stage, attempt, call, ev=None: events.append(
            ("record", stage, seq, attempt, call.cost_usd)
        ),
    )
    monkeypatch.setattr(pipeline.db, "finish_run", lambda *a: events.append("finish"))

    def classify(messages, timeout):
        assert messages == BODY.messages and timeout > 0
        events.append("classify")
        return analysis.Analysis(
            task="general",
            difficulty="easy",
            reasoning="low",
            source="jev",
            confidence=0.9,
            called=True,
            cost_usd=Decimal(".001"),
            cost_source="observed_usage",
        )

    def generate(model, messages, timeout):
        assert messages == BODY.messages and timeout > 0
        events.append(("generate", model.key, timeout))
        changes = gen_results.pop(0) if gen_results else {}
        return GenerationResult(
            model_key=model.key,
            provider=model.provider,
            model_id=model.model_id,
            **(
                {
                    "text": model.key + " answer",
                    "cost_usd": Decimal(".002"),
                    "cost_source": "observed_usage",
                }
                | changes
            ),
        )

    deterministic = evaluation.evaluate

    def evaluate(model, messages, generation, timeout):
        assert messages == BODY.messages
        if generation.finish_reason == "length" or not generation.text.strip():
            return deterministic(model, messages, generation, timeout)
        assert timeout > 0 and model.key == "judge"
        events.append(("evaluate", generation.model_key, timeout))
        outcome = judge_results.pop(0) if judge_results else grade("pass")
        unknown = outcome.status == "unknown"
        return outcome, GenerationResult(
            model_key="judge",
            provider="anthropic",
            model_id="offline",
            text="{}",
            cost_usd=None if unknown else Decimal(".004"),
            error_category="timeout" if unknown else None,
        )

    monkeypatch.setattr(analysis, "classify", classify)
    monkeypatch.setattr(pipeline.providers, "generate", generate)
    monkeypatch.setattr(evaluation, "reservation", lambda *a: Decimal(".01"))
    monkeypatch.setattr(evaluation, "evaluate", evaluate)

    def run(**kwargs):
        return pipeline.run_chat(
            object(),
            uuid4(),
            BODY,
            settings,
            registry,
            kwargs.pop("started", perf_counter()),
            **kwargs,
        )

    return run, events, gen_results, judge_results, settings, registry


def test_pass_first_persists_each_call_before_next_stage_and_counts_all_costs(setup):
    run, events, _, _, _, _ = setup
    result = run()
    assert result.status == "passed" and result.final_model == "cheap"
    assert result.total_cost_usd == Decimal(".007") and result.cost_complete
    assert len(result.attempts) == len(result.evaluations) == 1
    assert events[0:3] == ["create", "classify", "record_classify"]
    assert events[3][0] == "generate" and events[4][:4] == ("record", "generate", 2, 1)
    assert events[5][0] == "evaluate" and events[6][:4] == ("record", "evaluate", 3, 1)
    assert events[-1] == "finish"


def test_fail_then_pass_has_five_calls_and_uses_original_context(setup):
    run, events, _, outcomes, _, _ = setup
    outcomes.extend([grade("fail"), grade("pass")])
    result = run()
    assert result.status == "passed" and result.final_model == "strong"
    assert result.total_cost_usd == Decimal(".013")
    assert result.escalation_reason == "quality_failed"
    assert len(result.attempts) == len(result.evaluations) == 2
    records = [e for e in events if isinstance(e, tuple) and e[0] == "record"]
    assert [(e[1], e[2], e[3]) for e in records] == [
        ("generate", 2, 1),
        ("evaluate", 3, 1),
        ("generate", 4, 2),
        ("evaluate", 5, 2),
    ]


@pytest.mark.parametrize(
    "first,second,winner",
    [
        ((2, 4, 4), (1, 4, 4), "cheap"),
        ((2, 2, 2), (2, 3, 4), "strong"),
        ((2, 2, 2), (2, 2, 2), "strong"),
    ],
)
def test_fail_twice_uses_minimum_then_mean_then_later(setup, first, second, winner):
    run, _, _, outcomes, _, _ = setup
    outcomes.extend([grade("fail", first), grade("fail", second)])
    result = run()
    assert result.status == "quality_failed" and result.final_model == winner


def test_unknown_evaluation_stops_without_escalation_and_keeps_unknown_cost(setup):
    run, events, _, outcomes, _, _ = setup
    outcomes.append(grade("unknown"))
    result = run()
    assert result.status == "unverified" and len(result.attempts) == 1
    assert result.total_cost_usd is None and result.known_cost_usd == Decimal(".003")
    assert not result.cost_complete and result.reserved_cost_usd >= Decimal(".01")
    assert len([e for e in events if isinstance(e, tuple) and e[0] == "generate"]) == 1


def test_failed_second_generation_retains_first_answer_and_grade(setup):
    run, _, generations, outcomes, _, _ = setup
    generations.extend(
        [{}, {"text": "", "error_category": "unavailable", "cost_usd": None}]
    )
    outcomes.append(grade("fail"))
    result = run()
    assert result.status == "quality_failed" and result.final_model == "cheap"
    assert result.answer == "cheap answer" and result.error_category is None
    assert len(result.attempts) == 2 and len(result.evaluations) == 1
    assert not result.cost_complete


@pytest.mark.parametrize(
    "error,retries",
    [
        ("timeout", 2),
        ("rate_limit", 2),
        ("unavailable", 2),
        ("authentication", 1),
        ("invalid_request", 1),
    ],
)
def test_generation_error_retry_policy(setup, error, retries):
    run, _, generations, _, _, _ = setup
    generations.append({"text": "", "error_category": error, "cost_usd": None})
    result = run()
    assert len(result.attempts) == retries
    assert result.status == ("passed" if retries == 2 else "error")
    assert not result.cost_complete


@pytest.mark.parametrize(
    "changes",
    [{"finish_reason": "length"}, {"text": "", "error_category": "empty_response"}],
)
def test_empty_or_truncated_skips_first_judge_then_escalates(setup, changes):
    run, events, generations, _, _, _ = setup
    generations.append(changes)
    result = run()
    assert result.status == "passed" and result.final_model == "strong"
    assert result.evaluations[0]["status"] == "fail"
    assert len([e for e in events if isinstance(e, tuple) and e[0] == "evaluate"]) == 1


def test_no_higher_rank_returns_quality_failed_without_repeating(setup):
    run, _, _, outcomes, _, registry = setup
    registry.models[1].capability_rank = 1
    outcomes.append(grade("fail"))
    result = run()
    assert result.status == "quality_failed" and len(result.attempts) == 1
    assert result.escalation_reason is None
    assert any("Escalation skipped" in warning for warning in result.warnings)


def test_missing_judge_returns_best_effort_unverified(setup, monkeypatch):
    run, _, _, _, _, _ = setup
    monkeypatch.setattr(
        pipeline,
        "model_status",
        lambda m: "disabled" if m.key == "judge" else "available",
    )
    result = run()
    assert (
        result.status == "unverified"
        and result.evaluations[0]["error_category"] == "judge_unavailable"
    )


def test_expired_request_and_exhausted_budget_do_not_call(setup):
    run, events, _, _, settings, _ = setup
    result = run(started=perf_counter() - 91)
    assert (
        result.status == "error"
        and result.error_category == "timeout"
        and not result.attempts
    )
    assert "classify" not in events
    settings.request_budget_usd = Decimal(".000001")
    result = run()
    assert result.status == "error" and result.error_category == "no_eligible_model"
    assert not result.attempts and result.total_cost_usd == 0


def test_evaluation_time_is_reserved_before_generation(setup, monkeypatch):
    run, events, _, _, settings, _ = setup
    # A fixed clock leaves 20 seconds: five for generation, fifteen for the judge.
    monkeypatch.setattr(pipeline, "perf_counter", lambda: 100)
    settings.classification_timeout_seconds = 1
    result = run(started=30)
    gen = next(
        event for event in events if isinstance(event, tuple) and event[0] == "generate"
    )
    assert gen[2] == 5 and result.route_decisions[0]["evaluation_reserved"]


def test_persistence_failure_stops_before_judge_or_escalation(setup, monkeypatch):
    run, events, _, _, _, _ = setup

    def fail(*args):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(pipeline.db, "record_call", fail)
    with pytest.raises(RuntimeError, match="database write"):
        run()
    assert not any(isinstance(e, tuple) and e[0] == "evaluate" for e in events)


def test_fixed_smoke_has_no_classifier_or_evaluator(setup, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-key")
    run, events, _, _, _, _ = setup
    result = run(fixed=True)
    assert (
        result.status == "unverified"
        and result.analysis is None
        and not result.evaluations
    )
    assert "classify" not in events and result.total_cost_usd == Decimal(".002")


def test_mock_has_no_paid_stages_and_keeps_mock_zero_cost(setup):
    run, events, _, _, settings, _ = setup
    settings.mode = "mock"
    result = run()
    assert result.status == "unverified" and result.mode == "mock"
    assert result.total_cost_usd == 0 and result.cost_complete
    assert result.analysis is None and not result.evaluations
    assert "classify" not in events
    assert not any(isinstance(e, tuple) and e[0] == "evaluate" for e in events)


def test_second_unknown_answer_is_unverified_without_third_generation(setup):
    run, _, _, outcomes, _, _ = setup
    outcomes.extend([grade("fail"), grade("unknown")])
    result = run()
    assert result.status == "unverified" and result.final_model == "strong"
    assert len(result.attempts) == 2 and len(result.evaluations) == 2
    assert not result.cost_complete


def test_unknown_generation_cost_consumes_reservation_before_retry(setup, monkeypatch):
    run, _, generations, _, settings, _ = setup
    monkeypatch.setattr(
        pipeline,
        "model_status",
        lambda m: "disabled" if m.key == "judge" else "available",
    )
    settings.request_budget_usd = Decimal(".005")
    generations.append({"text": "", "error_category": "timeout", "cost_usd": None})
    result = run()
    assert result.status == "error" and len(result.attempts) == 1
    assert result.total_cost_usd is None and not result.cost_complete
    assert any("Escalation skipped" in warning for warning in result.warnings)


@pytest.mark.parametrize("constraint", ["budget", "time"])
def test_configured_judge_reservation_blocks_paid_work_when_it_cannot_fit(
    setup, monkeypatch, constraint
):
    run, events, _, _, settings, _ = setup
    started = perf_counter()
    if constraint == "budget":
        settings.request_budget_usd = Decimal(".005")
    else:
        monkeypatch.setattr(pipeline, "perf_counter", lambda: 100)
        started = 25
    result = run(started=started)
    assert result.status == "error" and result.error_category == "no_eligible_model"
    assert not result.attempts and not result.evaluations
    assert "classify" not in events and result.total_cost_usd == 0
    assert not result.route_decisions[0]["evaluation_reserved"]


def test_observed_spend_exceeding_reservation_skips_judge_and_keeps_answer(setup):
    run, _, generations, _, _, _ = setup
    generations.append({"cost_usd": Decimal(".995")})
    result = run()
    assert result.status == "unverified" and len(result.attempts) == 1
    assert result.evaluations[0]["error_category"] == "budget"
    assert result.total_cost_usd == Decimal(".996")


@pytest.mark.parametrize("category", ["timeout", "empty_response"])
def test_unavailable_retry_retains_original_generation_error(
    setup, monkeypatch, category
):
    run, _, generations, _, _, _ = setup
    monkeypatch.setattr(
        pipeline,
        "model_status",
        lambda m: "disabled" if m.key == "strong" else "available",
    )
    generations.append({"text": "", "error_category": category, "cost_usd": None})
    result = run()
    assert result.status == "error" and result.error_category == category
    assert len(result.attempts) == 1 and result.answer is None


def test_one_history_snapshot_is_reused_for_preflight_and_escalation(
    setup, monkeypatch
):
    run, _, _, outcomes, _, _ = setup
    outcomes.extend([grade("fail"), grade("pass")])
    snapshot = {"id": "frozen", "entries": []}
    loads, routes = [], []
    monkeypatch.setattr(
        pipeline.history, "load_history", lambda *a: loads.append(True) or snapshot
    )
    original_route = pipeline.choose_route

    def route(*args):
        routes.append(args[-1])
        return original_route(*args)

    monkeypatch.setattr(pipeline, "choose_route", route)
    run()
    assert loads == [True] and len(routes) == 3
    assert all(item is snapshot for item in routes)
    loads.clear()
    run(history_snapshot=snapshot)
    assert loads == []


def test_history_read_failure_stops_before_paid_work(setup, monkeypatch):
    import psycopg

    run, events, *_ = setup

    def unavailable(*args):
        raise psycopg.OperationalError("offline database failure")

    monkeypatch.setattr(pipeline.history, "load_history", unavailable)
    with pytest.raises(psycopg.OperationalError):
        run()
    assert events == []
