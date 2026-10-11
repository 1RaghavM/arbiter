import hashlib
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

PositiveInt = Annotated[int, Field(gt=0)]
NonNegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    provider: Literal["openai", "anthropic", "google"]
    model_id: str | None = None
    enabled: bool = False
    context_limit: PositiveInt | None = None
    max_output_tokens: PositiveInt = 1024
    input_usd_per_million: NonNegative | None = None
    output_usd_per_million: NonNegative | None = None
    additional_pricing: dict[str, NonNegative] = Field(default_factory=dict)
    price_verified_at: date | None = None
    source_url: HttpUrl | None = None
    prior_quality: dict[str, Probability] = Field(default_factory=dict)
    prior_latency_ms: PositiveInt | None = None
    capability_rank: PositiveInt | None = None

    @model_validator(mode="after")
    def check_enabled_model(self):
        if self.enabled:
            required = [
                self.model_id,
                self.context_limit,
                self.input_usd_per_million,
                self.output_usd_per_million,
                self.price_verified_at,
                self.source_url,
            ]
            if any(value is None for value in required) or not self.model_id.strip():
                raise ValueError("Enabled models need verified IDs, limits, and prices")
            if self.max_output_tokens > self.context_limit:
                raise ValueError("Output limit must fit the context limit")
        return self


class ModelRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[ModelConfig]
    cheap_baseline_key: str | None = None
    strong_baseline_key: str | None = None
    judge_key: str | None = None
    quality_floor: Probability = 0.80
    cost_weight: Probability = 0.70
    latency_weight: Probability = 0.30

    @model_validator(mode="after")
    def check_registry(self):
        keys = [model.key for model in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("Model keys must be unique")
        if abs(self.cost_weight + self.latency_weight - 1) > 1e-9:
            raise ValueError("Cost and latency weights must sum to one")
        enabled_keys = {model.key for model in self.models if model.enabled}
        for key in [self.cheap_baseline_key, self.strong_baseline_key, self.judge_key]:
            if key is not None and key not in enabled_keys:
                raise ValueError(
                    "Baseline and judge keys must reference enabled models"
                )
        return self


KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config/models.json"
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_environment():
    load_dotenv(ENV_PATH, override=False, interpolate=False)


class Settings(BaseModel):
    mode: Literal["mock", "live"] = "mock"
    fixed_model_key: str = "openai"
    evaluation_timeout_seconds: Annotated[
        float, Field(gt=0, le=30, allow_inf_nan=False)
    ] = 15
    classification_timeout_seconds: Annotated[
        float, Field(gt=0, le=30, allow_inf_nan=False)
    ] = 10
    request_budget_usd: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)] | None = (
        None
    )
    generation_timeout_seconds: Annotated[
        float, Field(gt=0, le=60, allow_inf_nan=False)
    ] = 30


def load_settings():
    return Settings(
        mode=os.environ.get("CHAT_MODE", "mock"),
        evaluation_timeout_seconds=os.environ.get("EVALUATION_TIMEOUT_SECONDS", "15"),
        fixed_model_key=os.environ.get("FIXED_MODEL_KEY", "openai"),
        classification_timeout_seconds=os.environ.get(
            "CLASSIFICATION_TIMEOUT_SECONDS", "10"
        ),
        request_budget_usd=os.environ.get("REQUEST_BUDGET_USD") or None,
        generation_timeout_seconds=os.environ.get("GENERATION_TIMEOUT_SECONDS", "30"),
    )


def load_registry():
    return ModelRegistry.model_validate_json(REGISTRY_PATH.read_text())


def model_status(model):
    if not model.enabled:
        return "disabled"
    if not os.environ.get(KEY_ENV[model.provider], "").strip():
        return "missing_credentials"
    return "available"


def fixed_model(settings, registry):
    model = next(
        (m for m in registry.models if m.key == settings.fixed_model_key), None
    )
    if model is None or model_status(model) != "available":
        raise ValueError("The configured model is disabled or missing credentials.")
    return model


def reserve_cost(model, messages):
    # shortcut: byte/framing token bound; use tokenizers if too restrictive.
    input_bound = sum(len(m.content.encode("utf-8")) + 256 for m in messages)
    if input_bound + model.max_output_tokens > model.context_limit:
        raise ValueError("Conversation exceeds the configured model context limit.")
    input_price = max(
        model.input_usd_per_million,
        model.additional_pricing.get("cache_write_usd_per_million", Decimal(0)),
    )
    return (
        input_bound * input_price
        + model.max_output_tokens * model.output_usd_per_million
    ) / 1000000


def config_version(settings, registry):
    snapshot = settings.model_dump_json() + registry.model_dump_json()
    return hashlib.sha256(snapshot.encode()).hexdigest()[:16]
