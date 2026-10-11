import asyncio
import copy
import json
from decimal import Decimal
from time import perf_counter

import httpx2
import pytest

from app import providers
from app.config import ModelConfig
from app.schemas import Message

RESPONSES = {
    "openai": {
        "id": "resp_offline",
        "object": "response",
        "created_at": 1,
        "model": "gpt-4.1-mini-2025-04-14",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "id": "msg_offline",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Blue", "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    },
    "anthropic": {
        "id": "msg_offline",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": "Blue"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 70,
            "output_tokens": 10,
            "cache_read_input_tokens": 20,
            "cache_creation_input_tokens": 10,
        },
    },
    "google": {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": "hidden reasoning", "thought": True},
                        {"text": "Blue"},
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 7,
            "thoughtsTokenCount": 3,
            "cachedContentTokenCount": 20,
            "totalTokenCount": 110,
        },
    },
}


def model(provider):
    return ModelConfig(
        key=provider,
        provider=provider,
        model_id={
            "openai": "gpt-4.1-mini-2025-04-14",
            "anthropic": "claude-sonnet-5-5",
            "google": "gemini-3.5-flash-lite",
        }[provider],
        input_usd_per_million="2",
        output_usd_per_million="10",
        additional_pricing={
            "cached_input_usd_per_million": "0.1",
            "cache_write_usd_per_million": "2.5",
        },
    )


def install_transport(
    monkeypatch, provider, payload=None, status=200, timeout=False, delay=0
):
    requests = []
    options = []

    async def respond(request):
        requests.append(request)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            request.extensions["cancelled"] = True
            raise
        if timeout:
            raise httpx2.ReadTimeout("secret provider diagnostic", request=request)
        body = payload if payload is not None else RESPONSES[provider]
        return httpx2.Response(
            status,
            content=json.dumps(body),
            headers={"content-type": "application/json"},
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(respond))
    if provider == "google":
        original = providers.genai.Client

        def factory(**kwargs):
            options.append(kwargs.copy())
            kwargs["http_options"] = kwargs["http_options"].model_copy(
                update={"httpx_async_client": client}
            )
            return original(**kwargs)

        monkeypatch.setattr(providers.genai, "Client", factory)
    else:
        module = providers.openai if provider == "openai" else providers.anthropic
        name = "AsyncOpenAI" if provider == "openai" else "AsyncAnthropic"
        original = getattr(module, name)

        def factory(**kwargs):
            options.append(kwargs.copy())
            return original(**kwargs, http_client=client)

        monkeypatch.setattr(module, name, factory)
    monkeypatch.setenv(
        {"google": "GOOGLE", "openai": "OPENAI", "anthropic": "ANTHROPIC"}[provider]
        + "_API_KEY",
        "offline-key",
    )
    return requests, options


def run(provider):
    return providers.generate(
        model(provider),
        [
            Message(role="user", content="My favorite color is blue."),
            Message(role="assistant", content="Understood."),
            Message(role="user", content="Which color?"),
        ],
        3.5,
    )


@pytest.mark.parametrize("provider", RESPONSES)
def test_sdk_requests_roles_usage_cost_and_limits(monkeypatch, provider):
    requests, options = install_transport(monkeypatch, provider)
    result = run(provider)
    assert result.error_category is None
    assert result.text == "Blue"
    assert result.input_tokens == 100 and result.output_tokens == 10
    assert result.cost_usd == Decimal(
        "0.000267" if provider == "anthropic" else "0.000262"
    )
    assert result.cost_source == "observed_usage"
    assert result.raw_usage and result.price_snapshot
    assert len(requests) == 1
    request = json.loads(requests[0].content)
    if provider != "google":
        assert request["model"] == model(provider).model_id
    if provider == "google":
        assert requests[0].url.host == "generativelanguage.googleapis.com"
        assert [m["role"] for m in request["contents"]] == ["user", "model", "user"]
        assert request["generationConfig"]["maxOutputTokens"] == 1024
        assert (
            request["generationConfig"]["thinkingConfig"]["thinking_level"] == "MINIMAL"
        )
        assert options[0]["http_options"].retry_options.attempts == 1
        assert options[0]["http_options"].timeout == 3500
    else:
        assert options[0]["max_retries"] == 0 and options[0]["timeout"] == 3.5
        field = "input" if provider == "openai" else "messages"
        assert [m["role"] for m in request[field]] == ["user", "assistant", "user"]
        assert (
            request["max_output_tokens" if provider == "openai" else "max_tokens"]
            == 1024
        )
        if provider == "openai":
            assert request["store"] is False
            assert requests[0].url.host == "api.openai.com"
        else:
            assert request["thinking"] == {"type": "between_tools"}
            assert requests[0].url.host == "api.anthropic.com"


@pytest.mark.parametrize("provider", RESPONSES)
@pytest.mark.parametrize(
    "status,category",
    [
        (401, "authentication"),
        (429, "rate_limit"),
        (500, "unavailable"),
        (400, "invalid_request"),
    ],
)
def test_sdk_errors_do_not_retry_or_claim_zero_cost(
    monkeypatch, provider, status, category
):
    requests, _ = install_transport(
        monkeypatch,
        provider,
        {
            "error": {
                "code": status,
                "message": "secret provider diagnostic",
                "type": "api_error",
            }
        },
        status,
    )
    result = run(provider)
    assert len(requests) == 1
    assert result.error_category == category
    assert result.cost_usd is None and result.cost_source == "unknown"
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize("provider", RESPONSES)
def test_sdk_timeout_is_bounded_and_unknown_cost(monkeypatch, provider):
    requests, _ = install_transport(monkeypatch, provider, timeout=True)
    result = run(provider)
    assert len(requests) == 1 and result.error_category == "timeout"
    assert result.cost_usd is None


@pytest.mark.parametrize("provider", RESPONSES)
@pytest.mark.parametrize("kind", ["truncated", "empty", "malformed", "no_usage"])
def test_partial_response_retains_observed_usage(monkeypatch, provider, kind):
    response = copy.deepcopy(RESPONSES[provider])
    if provider == "openai":
        if kind == "truncated":
            response.update(
                status="incomplete", incomplete_details={"reason": "max_output_tokens"}
            )
        elif kind == "no_usage":
            response.pop("usage")
        else:
            response["output"][0]["content"] = (
                [] if kind == "empty" else [{"type": "output_text"}]
            )
    elif provider == "anthropic":
        if kind == "truncated":
            response["stop_reason"] = "max_tokens"
        elif kind == "no_usage":
            response.pop("usage")
        else:
            response["content"] = [] if kind == "empty" else [{"type": "text"}]
    else:
        if kind == "truncated":
            response["candidates"][0]["finishReason"] = "MAX_TOKENS"
        elif kind == "no_usage":
            response.pop("usageMetadata")
        else:
            response["candidates"][0]["content"]["parts"] = []
            if kind == "malformed":
                response["candidates"][0]["finishReason"] = None
    install_transport(monkeypatch, provider, response)
    result = run(provider)
    if kind == "no_usage":
        assert result.error_category is None and result.cost_usd is None
    else:
        assert result.cost_usd is not None and result.raw_usage
        if kind == "truncated":
            assert result.text == "Blue" and result.finish_reason == "length"
            assert result.error_category is None
        else:
            assert result.error_category == (
                "empty_response" if kind == "empty" else "malformed_response"
            )


def test_bad_usage_and_unpriced_cache_remain_unknown(monkeypatch):
    response = copy.deepcopy(RESPONSES["openai"])
    response["usage"]["input_tokens_details"]["cached_tokens"] = 101
    install_transport(monkeypatch, "openai", response)
    result = run("openai")
    assert result.cost_usd is None and result.raw_usage


@pytest.mark.parametrize("provider", RESPONSES)
def test_blocked_response_preserves_usage(monkeypatch, provider):
    response = copy.deepcopy(RESPONSES[provider])
    if provider == "openai":
        response["output"][0]["content"] = [{"type": "refusal", "refusal": "No."}]
    elif provider == "anthropic":
        response["stop_reason"] = "refusal"
    else:
        response["candidates"][0]["finishReason"] = "SAFETY"
    install_transport(monkeypatch, provider, response)
    result = run(provider)
    assert result.error_category == "blocked" and result.cost_usd is not None


def test_unknown_cache_price_does_not_undercount(monkeypatch):
    install_transport(monkeypatch, "openai")
    config = model("openai").model_copy(update={"additional_pricing": {}})
    result = providers.generate(config, [Message(role="user", content="Hello")], 1)
    assert result.input_tokens == 100 and result.cost_usd is None


def test_expired_timeout_does_not_make_a_request(monkeypatch):
    requests, _ = install_transport(monkeypatch, "openai")
    result = providers.generate(
        model("openai"), [Message(role="user", content="Hi")], 0
    )
    assert not requests and result.error_category == "timeout"


@pytest.mark.parametrize("provider", RESPONSES)
@pytest.mark.parametrize("text", ["bad\x00output", "bad\ud800output"])
def test_invalid_output_text_is_cleared_without_losing_usage(
    monkeypatch, provider, text
):
    response = copy.deepcopy(RESPONSES[provider])
    if provider == "openai":
        response["output"][0]["content"][0]["text"] = text
    elif provider == "anthropic":
        response["content"][0]["text"] = text
    else:
        response["candidates"][0]["content"]["parts"] = [{"text": text}]
    install_transport(monkeypatch, provider, response)
    result = run(provider)
    assert result.error_category == "malformed_response" and result.text == ""
    assert result.raw_usage and result.cost_usd is not None
    result.model_dump_json().encode("utf-8")


@pytest.mark.parametrize("provider", RESPONSES)
def test_whole_stage_deadline_cancels_inflight_request(monkeypatch, provider):
    requests, _ = install_transport(monkeypatch, provider, delay=5)
    started = perf_counter()
    result = providers.generate(
        model(provider), [Message(role="user", content="Hi")], 0.1
    )
    assert perf_counter() - started < 1
    assert result.error_category == "timeout" and result.cost_usd is None
    assert result.price_snapshot and result.raw_usage is None
    assert len(requests) == 1 and requests[0].extensions["cancelled"]


def test_partially_parsed_invalid_text_is_still_cleared(monkeypatch):
    response = copy.deepcopy(RESPONSES["openai"])
    response["output"][0]["content"] = [
        {"type": "output_text", "text": "bad\x00output"},
        {"type": "output_text"},
    ]
    install_transport(monkeypatch, "openai", response)
    result = run("openai")
    assert result.error_category == "malformed_response" and result.text == ""
    assert result.raw_usage and result.cost_usd is not None


def test_anthropic_native_schema_is_sent_without_changing_generation(monkeypatch):
    requests, _ = install_transport(monkeypatch, "anthropic")
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer"}},
        "required": ["score"],
        "additionalProperties": False,
    }
    result = providers.generate(
        model("anthropic"),
        [Message(role="user", content="Grade")],
        2,
        output_schema=schema,
    )
    assert result.error_category is None
    assert json.loads(requests[0].content)["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }


@pytest.mark.parametrize("provider", ["openai", "google"])
def test_unsupported_schema_provider_is_rejected_before_network(monkeypatch, provider):
    requests, _ = install_transport(monkeypatch, provider)
    with pytest.raises(ValueError, match="Anthropic"):
        providers.generate(
            model(provider),
            [Message(role="user", content="Grade")],
            2,
            output_schema={"type": "object"},
        )
    assert not requests
