import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import ModelRegistry


@pytest.fixture
def template():
    path = Path(__file__).resolve().parents[2] / "config/models.json"
    return json.loads(path.read_text())


def test_template_is_disabled_and_has_no_invented_ids(template):
    registry = ModelRegistry.model_validate(template)
    assert {model.provider for model in registry.models} == {
        "openai",
        "anthropic",
        "google",
    }
    assert all(
        not model.enabled and model.model_id is None for model in registry.models
    )


def test_placeholder_cannot_be_enabled(template):
    template["models"][0]["enabled"] = True
    with pytest.raises(ValidationError, match="Enabled models need"):
        ModelRegistry.model_validate(template)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cost_weight", 0.9),
        ("latency_weight", -1),
        ("strong_baseline_key", "missing"),
        ("judge_key", "openai"),
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
