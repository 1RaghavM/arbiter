import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import ModelRegistry


def test_env_file_loads_at_api_startup(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app import config, db
    from app.main import app

    monkeypatch.setattr(os, "environ", os.environ.copy())
    values = {
        "DATABASE_URL": "postgresql://fake-host/env-test",
        "CHAT_MODE": "live",
        "REQUEST_BUDGET_USD": "0.05",
        "JEV_API_KEY": "fake-jev",
        "OPENAI_API_KEY": "fake-${LITERAL}-key",
        "ANTHROPIC_API_KEY": "fake-anthropic",
        "GOOGLE_API_KEY": "fake-google",
    }
    for key in values:
        monkeypatch.delenv(key, raising=False)
    config.ENV_PATH.write_text(
        "\n".join(f'{key}="{value}"' for key, value in values.items())
    )
    monkeypatch.chdir(tmp_path.parent)
    database_urls = []
    monkeypatch.setattr(db, "create_pool", lambda url: database_urls.append(url))
    with TestClient(app) as client:
        response = client.get("/api/config")
    assert response.status_code == 200
    assert database_urls == [values["DATABASE_URL"]]
    assert response.json()["mode"] == "live"
    assert all(p["status"] == "available" for p in response.json()["providers"])
    assert str(config.load_settings().request_budget_usd) == "0.05"
    assert all(os.environ[key] == value for key, value in values.items())
    assert all(
        value not in response.text for key, value in values.items() if "KEY" in key
    )


def test_env_file_preserves_shell_overrides_and_is_optional(monkeypatch):
    from app import config

    monkeypatch.setenv("CHAT_MODE", "mock")
    config.load_environment()
    assert config.load_settings().mode == "mock"
    config.ENV_PATH.write_text("CHAT_MODE=live\n")
    config.load_environment()
    assert config.load_settings().mode == "mock"


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
