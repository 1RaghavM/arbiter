from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)

    @field_validator("content")
    @classmethod
    def nonblank_text(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Message must contain text without null characters")
        # PostgreSQL JSONB requires valid Unicode scalar values.
        value.encode("utf-8")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[Message] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def bounded_history(self):
        if self.messages[-1].role != "user":
            raise ValueError("History must end with a user message")
        if sum(len(message.content) for message in self.messages) > 12000:
            raise ValueError("History exceeds 12,000 characters")
        return self


class GenerationResult(BaseModel):
    model_key: str = "mock-v1"
    text: str
    finish_reason: str = "stop"
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    cost_usd: Decimal | None = Decimal("0")
    cost_source: Literal["observed_usage", "estimated", "unknown"] = "estimated"
    error_category: str | None = None


class ChatResult(BaseModel):
    run_id: UUID
    mode: Literal["mock"] = "mock"
    answer: str | None = None
    final_model: str | None = None
    status: Literal["passed", "quality_failed", "unverified", "error"]
    analysis: dict | None = None
    route_decisions: list[dict] = Field(default_factory=list)
    attempts: list[GenerationResult] = Field(default_factory=list)
    total_latency_ms: int = 0
    total_cost_usd: Decimal | None = Decimal("0")
    known_cost_usd: Decimal = Decimal("0")
    cost_complete: bool = True
    escalation_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
