from decimal import Decimal
from itertools import permutations
from types import SimpleNamespace

import pytest

from app.config import ModelConfig, ModelRegistry, load_registry, reserve_cost
from app.routing import choose_route
from app.schemas import Message

MESSAGES = [Message(role="user", content="test")]


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_configured_haiku_routes_only_easy_tasks(difficulty):
    registry = load_registry()
    result = choose_route(
        SimpleNamespace(
            task="general", difficulty=difficulty, source="jev", confidence=0.9
        ),
        registry,
        MESSAGES,
        {model.key for model in registry.models},
        Decimal("1"),
        30,
    )
    haiku = next(c for c in result["candidates"] if c["key"] == "haiku")
    if difficulty == "easy":
        assert haiku["eligible"] and result["selected_key"] == "haiku"
    else:
        assert not haiku["eligible"]
        assert result["selected_key"] != "haiku"


def model(key, price="1", latency=1000, quality=0.85, rank=1, **changes):
    values = dict(
        key=key,
        provider="openai",
        model_id="offline",
        enabled=True,
        context_limit=4096,
        max_output_tokens=1024,
        input_usd_per_million=price,
        output_usd_per_million=price,
        price_verified_at="2026-10-11",
        source_url="https://example.com/pricing",
        prior_quality={"easy": quality},
        prior_latency_ms=latency,
        capability_rank=rank,
    )
    values.update(changes)
    return ModelConfig(**values)


def route(
    models,
    *,
    analysis=None,
    available=None,
    budget=Decimal("1"),
    remaining=30,
    history=None,
    **registry,
):
    return choose_route(
        analysis
        or SimpleNamespace(
            task="general", difficulty="easy", source="jev", confidence=0.9
        ),
        ModelRegistry(models=models, **registry),
        MESSAGES,
        available if available is not None else {m.key for m in models},
        budget,
        remaining,
        history,
    )


def test_hand_calculated_scores_and_separate_spend_reservation():
    cheap = model("cheap", price="1", latency=2000)
    fast = model("fast", price="2", latency=1000)
    decision = route([fast, cheap])
    # 260 input + 256 expected output: costs 0.000516 and 0.001032.
    assert decision["selected_key"] == "cheap"
    assert decision["bucket"] == "general:easy" and decision["source"] == "priors"
    assert decision["policy_version"] == "history-v1"
    cheap_log, fast_log = decision["candidates"]
    assert cheap_log["estimated_cost_usd"] == "0.000516"
    assert cheap_log["reserved_cost_usd"] == "0.001284"
    assert cheap_log["score"] == pytest.approx(0.65)
    assert fast_log["score"] == pytest.approx(0.85)


def test_quality_floor_and_bucket_override_difficulty_prior():
    low = model("cheap", price="0", prior_quality={"easy": 0.99, "general:easy": 0.79})
    passing = model("expensive", price="5", quality=0.8)
    result = route([low, passing])
    assert result["selected_key"] == "expensive"
    assert result["candidates"][0]["score"] is None


def test_ties_and_registry_order_are_stable_with_zero_prices():
    models = [model(key, price="0") for key in ["c", "a", "b"]]
    expected = route(models)
    assert expected["selected_key"] == "a"
    for ordering in permutations(models):
        assert route(list(ordering)) == expected


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"enabled": False}, "disabled"),
        ({"context_limit": 1024}, "context_limit"),
        ({"prior_quality": {}}, "missing_priors"),
        ({"prior_latency_ms": None}, "missing_priors"),
        ({"capability_rank": None}, "missing_priors"),
    ],
)
def test_invalid_candidate_exclusions(change, reason):
    result = route([model("excluded", **change)])
    assert result["selected_key"] is None
    candidate = result["candidates"][0]
    assert candidate["eligible"] is False and candidate["exclusion_reason"] == reason


def test_budget_credentials_and_time_filters_include_exact_boundaries():
    candidate = model("one")
    reservation = reserve_cost(candidate, MESSAGES)
    for kwargs, reason in [
        ({"budget": reservation - Decimal("0.000001")}, "budget"),
        ({"available": set()}, "unavailable"),
        ({"remaining": 0.999}, "deadline"),
    ]:
        result = route([candidate], **kwargs)
        assert result["selected_key"] is None
        assert result["candidates"][0]["exclusion_reason"] == reason
    assert route([candidate], budget=reservation, remaining=1)["selected_key"] == "one"


@pytest.mark.parametrize(
    "source,confidence", [("fallback", 0.9), ("jev", None), ("jev", 0.59)]
)
def test_classification_fallback_prefers_strong_then_highest_rank(source, confidence):
    analysis = SimpleNamespace(
        task="general", difficulty="easy", source=source, confidence=confidence
    )
    models = [
        model("strong", rank=2, quality=0.5),
        model("a", rank=3),
        model("z", rank=3),
    ]
    assert (
        route(models, analysis=analysis, strong_baseline_key="strong")["selected_key"]
        == "strong"
    )
    result = route(
        models, analysis=analysis, strong_baseline_key="strong", available={"a", "z"}
    )
    assert result["selected_key"] == "a"
    assert "fallback" in result["reason"]


def test_below_target_orders_by_quality_then_cost_then_key():
    models = [
        model("low", price="0", quality=0.5),
        model("b", price="1", quality=0.7),
        model("a", price="1", quality=0.7),
        model("costly", price="2", quality=0.7),
    ]
    result = route(models)
    assert result["selected_key"] == "a" and "below_target" in result["reason"]
    assert all(candidate["score"] is None for candidate in result["candidates"])


def test_disabled_placeholder_has_unknown_estimates():
    result = route([ModelConfig(key="unset", provider="google")])
    assert result["selected_key"] is None
    candidate = result["candidates"][0]
    assert candidate["estimated_cost_usd"] is None
    assert candidate["reserved_cost_usd"] is None


def test_short_output_limit_and_cache_write_price_affect_different_estimates():
    candidate = model(
        "short",
        max_output_tokens=100,
        additional_pricing={"cache_write_usd_per_million": "2"},
    )
    result = route([candidate])["candidates"][0]
    assert Decimal(result["estimated_cost_usd"]) == Decimal("0.000360")
    assert Decimal(result["reserved_cost_usd"]) == Decimal("0.000620")


def history_entry(key="cheap", **changes):
    entry = dict(
        bucket="general:easy",
        model_key=key,
        provider="openai",
        model_id="offline",
        n=5,
        passes=0,
        failures=5,
        unknown_count=2,
        latency_ms=500,
        output_tokens=50,
    )
    entry.update(changes)
    return {
        "id": "frozen",
        "policy_version": "history-v1",
        "rubric_version": "rubric-v1",
        "judge": None,
        "entries": [entry],
    }


def test_history_changes_selection_with_smoothed_quality_and_median_estimates():
    models = [model("cheap"), model("strong", price="2", quality=0.9)]
    assert route(models)["selected_key"] == "cheap"
    result = route(models, history=history_entry())
    assert result["selected_key"] == "strong"
    assert result["source"] == "history" and result["history_snapshot_id"] == "frozen"
    candidate = result["candidates"][0]
    assert candidate["quality"] == pytest.approx(0.425)
    assert candidate["history_n"] == 5 and candidate["unknown_count"] == 2
    assert candidate["latency_ms"] == 500 and candidate["expected_output_tokens"] == 50
    assert Decimal(candidate["estimated_cost_usd"]) == Decimal(".000310")
    assert Decimal(candidate["reserved_cost_usd"]) == Decimal(".001284")


def test_four_labels_and_many_unknowns_keep_priors():
    result = route(
        [model("cheap")], history=history_entry(n=4, failures=4, unknown_count=100)
    )
    candidate = result["candidates"][0]
    assert candidate["quality"] == 0.85 and candidate["estimate_source"] == "priors"
    assert candidate["history_n"] == 4 and candidate["unknown_count"] == 100
    assert (
        candidate["latency_ms"] == 1000 and candidate["expected_output_tokens"] == 256
    )


@pytest.mark.parametrize(
    "change",
    [
        {"bucket": "general:hard"},
        {"model_id": "old"},
        {"provider": "google"},
        {"model_key": "other"},
    ],
)
def test_incompatible_history_entry_is_ignored(change):
    result = route([model("cheap")], history=history_entry(**change))
    assert result["candidates"][0]["history_n"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"policy_version": "priors-v1"},
        {"rubric_version": "old"},
        {"judge": {"provider": "anthropic", "model_id": "old"}},
    ],
)
def test_incompatible_snapshot_is_ignored(change):
    snapshot = history_entry()
    snapshot.update(change)
    result = route([model("cheap")], history=snapshot)
    assert result["history_snapshot_id"] is None
    assert result["candidates"][0]["history_n"] == 0


def test_medians_are_bounded_and_missing_output_uses_prior():
    result = route(
        [model("cheap")], history=history_entry(latency_ms=0, output_tokens=9000)
    )
    assert result["candidates"][0]["latency_ms"] == 1
    assert result["candidates"][0]["expected_output_tokens"] == 1024
    result = route(
        [model("cheap")], history=history_entry(latency_ms=None, output_tokens=None)
    )
    assert result["candidates"][0]["latency_ms"] == 1000
    assert result["candidates"][0]["expected_output_tokens"] == 256


def test_history_latency_controls_deadline_without_mutating_snapshot():
    import copy

    snapshot = history_entry(latency_ms=4000)
    original = copy.deepcopy(snapshot)
    result = route([model("cheap")], history=snapshot, remaining=3)
    assert result["selected_key"] is None
    assert result["candidates"][0]["exclusion_reason"] == "deadline"
    assert snapshot == original
