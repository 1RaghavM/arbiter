from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

PositiveInt = Annotated[int, Field(gt=0)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
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
                self.prior_latency_ms,
                self.capability_rank,
            ]
            if any(value is None for value in required) or not self.model_id.strip():
                raise ValueError(
                    "Enabled models need verified IDs, limits, prices, and priors"
                )
            if not self.prior_quality:
                raise ValueError("Enabled models need provisional quality estimates")
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
