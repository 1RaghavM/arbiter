import asyncio
import os
from decimal import Decimal
from time import perf_counter

import anthropic
import httpx
import httpx2
import openai
from google import genai
from google.genai import errors, types

from app.config import ModelConfig
from app.schemas import GenerationResult, Message


def generate_mock(messages: list[Message]) -> GenerationResult:
    previous = [message.content for message in messages[:-1] if message.role == "user"]
    text = f"Mock reply to: {messages[-1].content[:200]}"
    if previous:
        text += f"\nEarlier you said: {previous[-1][:200]}"
    return GenerationResult(text=text, cost_usd=Decimal("0"), cost_source="estimated")


def _account(result: GenerationResult, model: ModelConfig) -> None:
    usage = result.raw_usage
    if not isinstance(usage, dict):
        return
    try:
        cached = written = 0
        if model.provider == "openai":
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
        elif model.provider == "anthropic":
            input_tokens = usage["input_tokens"]
            output_tokens = usage["output_tokens"]
            cached = usage.get("cache_read_input_tokens") or 0
            written = usage.get("cache_creation_input_tokens") or 0
            input_tokens += cached + written
            creation = usage.get("cache_creation") or {}
            if creation.get("ephemeral_1h_input_tokens", 0):
                # One-hour cache writes are not requested or priced here.
                return
        else:
            input_tokens = usage["prompt_token_count"]
            output_tokens = usage["candidates_token_count"]
            thoughts = usage.get("thoughts_token_count") or 0
            if type(thoughts) is not int or thoughts < 0:
                return
            output_tokens += thoughts
            cached = usage.get("cached_content_token_count") or 0
            if usage.get("tool_use_prompt_token_count"):
                return
        counts = (input_tokens, output_tokens, cached, written)
        if any(type(count) is not int or count < 0 for count in counts):
            return
        if cached + written > input_tokens:
            return
        result.input_tokens, result.output_tokens = input_tokens, output_tokens
        cost = Decimal(input_tokens - cached - written) * model.input_usd_per_million
        cost += Decimal(output_tokens) * model.output_usd_per_million
        if cached:
            cost += cached * model.additional_pricing["cached_input_usd_per_million"]
        if written:
            cost += written * model.additional_pricing["cache_write_usd_per_million"]
        result.cost_usd = cost / 1_000_000
        result.cost_source = "observed_usage"
    except (KeyError, TypeError, ValueError):
        return


def generate(
    model: ModelConfig,
    messages: list[Message],
    timeout: float,
    output_schema: dict | None = None,
) -> GenerationResult:
    if output_schema is not None and model.provider != "anthropic":
        raise ValueError("Structured outputs require the configured Anthropic judge")
    started = perf_counter()
    result = GenerationResult(
        model_key=model.key,
        provider=model.provider,
        model_id=model.model_id,
        text="",
        finish_reason="error",
        price_snapshot=model.model_dump(
            mode="json",
            include={
                "model_id",
                "input_usd_per_million",
                "output_usd_per_million",
                "additional_pricing",
                "price_verified_at",
                "source_url",
            },
        ),
    )

    async def run():
        await asyncio.wait_for(
            _generate(model, messages, timeout, result, output_schema), timeout
        )

    try:
        asyncio.run(run())
    except TimeoutError:
        result.error_category = "timeout"
    try:
        if "\x00" in result.text:
            raise ValueError("Null character in output")
        result.text.encode("utf-8")
    except (ValueError, UnicodeError):
        result.text = ""
        result.error_category = "malformed_response"
    if not result.text.strip() and not result.error_category:
        result.error_category = "empty_response"
    result.latency_ms = round((perf_counter() - started) * 1000)
    return result


async def _generate(model, messages, timeout, result, output_schema):
    try:
        history = [message.model_dump() for message in messages]
        if model.provider == "openai":
            async with openai.AsyncOpenAI(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url="https://api.openai.com/v1",
                max_retries=0,
                timeout=timeout,
            ) as client:
                response = (
                    await client.responses.create(
                        model=model.model_id,
                        input=history,
                        max_output_tokens=model.max_output_tokens,
                        store=False,
                    )
                ).model_dump(mode="json")
            result.raw_usage = response.get("usage")
            _account(result, model)
            for item in response.get("output", []):
                if item.get("type") == "message":
                    for part in item["content"]:
                        if part.get("type") == "output_text":
                            result.text += part["text"]
                        elif part.get("type") == "refusal":
                            result.error_category = "blocked"
            status = response.get("status")
            if status == "completed":
                result.finish_reason = "stop"
            elif status == "incomplete":
                reason = (response.get("incomplete_details") or {}).get("reason")
                result.finish_reason = (
                    "length" if reason == "max_output_tokens" else "other"
                )
                if reason != "max_output_tokens":
                    result.error_category = "blocked"
            else:
                result.error_category = "malformed_response"
        elif model.provider == "anthropic":
            options = {}
            if output_schema is not None:
                options["output_config"] = {
                    "format": {"type": "json_schema", "schema": output_schema}
                }
            async with anthropic.AsyncAnthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                base_url="https://api.anthropic.com",
                max_retries=0,
                timeout=timeout,
            ) as client:
                response = (
                    await client.messages.create(
                        model=model.model_id,
                        messages=history,
                        max_tokens=model.max_output_tokens,
                        thinking={
                            "type": "disabled"
                            if model.model_id == "claude-haiku-5-5"
                            else "between_tools"
                        },
                        **options,
                    )
                ).model_dump(mode="json")
            result.raw_usage = response.get("usage")
            _account(result, model)
            result.text = "".join(
                block["text"]
                for block in response["content"]
                if block.get("type") == "text"
            )
            reason = response.get("stop_reason")
            if reason in {"end_turn", "stop_sequence"}:
                result.finish_reason = "stop"
            elif reason == "max_tokens":
                result.finish_reason = "length"
            else:
                result.error_category = (
                    "blocked" if reason == "refusal" else "malformed_response"
                )
        else:
            async with genai.Client(
                api_key=os.environ["GOOGLE_API_KEY"],
                vertexai=False,
                enterprise=False,
                http_options=types.HttpOptions(
                    base_url="https://generativelanguage.googleapis.com",
                    timeout=max(1, int(timeout * 1000)),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ).aio as client:
                response = (
                    await client.models.generate_content(
                        model=model.model_id,
                        contents=[
                            types.Content(
                                role="model" if message.role == "assistant" else "user",
                                parts=[types.Part(text=message.content)],
                            )
                            for message in messages
                        ],
                        config=types.GenerateContentConfig(
                            max_output_tokens=model.max_output_tokens,
                            candidate_count=1,
                            thinking_config=types.ThinkingConfig(
                                thinking_level="minimal"
                            ),
                        ),
                    )
                ).model_dump(mode="json")
            result.raw_usage = response.get("usage_metadata")
            _account(result, model)
            candidates = response.get("candidates") or []
            if not candidates:
                result.error_category = (
                    "blocked"
                    if response.get("prompt_feedback")
                    else "malformed_response"
                )
            else:
                candidate = candidates[0]
                result.text = "".join(
                    part.get("text") or ""
                    for part in (candidate.get("content") or {}).get("parts", [])
                    if not part.get("thought")
                )
                reason = candidate.get("finish_reason")
                if reason == "STOP":
                    result.finish_reason = "stop"
                elif reason == "MAX_TOKENS":
                    result.finish_reason = "length"
                else:
                    result.error_category = (
                        "blocked"
                        if reason
                        in {
                            "SAFETY",
                            "RECITATION",
                            "BLOCKLIST",
                            "PROHIBITED_CONTENT",
                            "SPII",
                        }
                        else "malformed_response"
                    )
    except (
        TimeoutError,
        openai.APITimeoutError,
        anthropic.APITimeoutError,
        httpx.TimeoutException,
        httpx2.TimeoutException,
    ):
        result.error_category = "timeout"
    except (openai.APIStatusError, anthropic.APIStatusError, errors.APIError) as exc:
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        result.error_category = {
            400: "invalid_request",
            401: "authentication",
            403: "authentication",
            404: "unavailable",
            408: "timeout",
            422: "invalid_request",
            429: "rate_limit",
        }.get(status, "unavailable")
    except (
        openai.APIConnectionError,
        anthropic.APIConnectionError,
        httpx.TransportError,
        httpx2.TransportError,
    ):
        result.error_category = "unavailable"
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        openai.APIResponseValidationError,
        anthropic.APIResponseValidationError,
    ):
        result.error_category = "malformed_response"
    except Exception:
        result.error_category = "internal_error"
