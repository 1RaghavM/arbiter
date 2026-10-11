import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import ModelRegistry


@pytest.fixture
def template():
    path = Path(__file__).resolve().parents[2] / "config/models.json"
    return json.loads(path.read_text())


def test_registry_has_verified_candidates_disabled_without_keys(template, monkeypatch):
    registry = ModelRegistry.model_validate(template)
    assert {model.provider for model in registry.models} == {
        "openai",
        "anthropic",
        "google",
    }
    from app.config import KEY_ENV, model_status

    for name in KEY_ENV.values():
        monkeypatch.delenv(name, raising=False)
    assert all(model.model_id and model.price_verified_at for model in registry.models)
    assert all(
        model_status(model) == "missing_credentials" for model in registry.models
    )


def test_placeholder_cannot_be_enabled(template):
    template["models"][0]["model_id"] = None
    with pytest.raises(ValidationError, match="Enabled models need"):
        ModelRegistry.model_validate(template)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost_weight", 0.9),
        ("latency_weight", -1),
        ("strong_baseline_key", "missing"),
        ("judge_key", "missing"),
    ],
)
def test_invalid_policy_is_rejected(template, field, value):
    template[field] = value
    with pytest.raises(ValidationError):
        ModelRegistry.model_validate(template)


def test_duplicate_keys_are_rejected(template):
    template["models"].append(template["models"][0])
    with pytest.raises(ValidationError, match="unique"):
        ModelRegistry.model_validate(template)


def test_nonpositive_model_limits_are_rejected(template):
    template["models"][0]["max_output_tokens"] = 0
    with pytest.raises(ValidationError):
        ModelRegistry.model_validate(template)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0"])
def test_budget_must_be_positive_and_finite(value):
    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(request_budget_usd=value)


def test_reservation_covers_unicode_output_and_context(template):
    from decimal import Decimal

    from app.config import reserve_cost
    from app.schemas import Message

    model = ModelRegistry.model_validate(template).models[0]
    messages = [Message(role="user", content="🧪")]
    expected = (Decimal(260) * Decimal("0.4") + 1024 * Decimal("1.6")) / 1000000
    assert reserve_cost(model, messages) == expected
    model.context_limit = 1024
    with pytest.raises(ValueError, match="context"):
        reserve_cost(model, messages)
