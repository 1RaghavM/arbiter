import asyncio
import copy
import json
from decimal import Decimal
from time import perf_counter

import httpx2
import pytest
from pydantic import ValidationError

from app import analysis
from app.schemas import Message

MESSAGES = [
    Message(role="user", content="Remember that I use Python."),
    Message(role="assistant", content="Understood."),
    Message(role="user", content="Write a function that adds two numbers."),
]
RESPONSE = {
    "model": analysis.MODEL_ID,
    "answers": {
        "task": {"type": "choice", "choice": "coding", "confidence": 0.9},
        "difficulty": {"type": "choice", "choice": "easy", "confidence": 0.85},
        "reasoning": {"type": "choice", "choice": "low", "confidence": 0.8},
    },
    "usage": {"input_tokens": 300, "output_tokens": 60},
}


def install_transport(monkeypatch, payload=None, status=200, delay=0, error=None):
    requests, options = [], []

    async def respond(request):
        requests.append(request)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            request.extensions["cancelled"] = True
            raise
        if error:
            raise error("private provider diagnostic", request=request)
        return httpx2.Response(
            status,
            content=json.dumps(RESPONSE if payload is None else payload),
            headers={"content-type": "application/json"},
        )

    original = httpx2.AsyncClient

    def client(**kwargs):
        options.append(kwargs)
        return original(**kwargs, transport=httpx2.MockTransport(respond))

    monkeypatch.setattr(analysis.httpx2, "AsyncClient", client)
    monkeypatch.setenv("JEV_API_KEY", "offline-key")
    return requests, options


def test_official_request_context_independent_questions_and_accounting(monkeypatch):
    requests, options = install_transport(monkeypatch)
    result = analysis.classify(MESSAGES, 2)
    assert result.source == "jev" and result.error_category is None and result.called
    assert (result.task, result.difficulty, result.reasoning) == (
        "coding",
        "easy",
        "low",
    )
    assert result.confidence == 0.8
    assert result.cost_usd == Decimal("0.0000126")
    assert result.raw_usage == RESPONSE["usage"]
    assert result.cost_source == "observed_usage"
    assert result.price_snapshot["source_url"] == "https://docs.typesafe.ai/models"
    assert result.model_id == analysis.MODEL_ID
    assert analysis.RESERVATION == Decimal(65536) * Decimal("0.042") / 1_000_000
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
    assert request.headers["authorization"] == "Bearer offline-key"
    body = json.loads(request.content)
    assert body["state"]["messages"] == [m.model_dump() for m in MESSAGES]
    assert set(body["questions"]) == {"task", "difficulty", "reasoning"}
    assert all(q["type"] == "choice" for q in body["questions"].values())
    assert body["model"] == analysis.MODEL_ID
    assert options == [{"timeout": 2, "follow_redirects": False}]


@pytest.mark.parametrize("cause", ["missing_key", "timeout", "context"])
def test_preflight_failure_costs_zero_and_does_not_call(monkeypatch, cause):
    requests, _ = install_transport(monkeypatch)
    messages, timeout = MESSAGES, 2
    if cause == "missing_key":
        monkeypatch.delenv("JEV_API_KEY")
    elif cause == "timeout":
        timeout = 0
    else:
        messages = [Message(role="user", content="😀" * 12000)]
    result = analysis.classify(messages, timeout)
    assert result.source == "fallback" and not result.called and not requests
    assert result.cost_usd == 0 and result.cost_source == "estimated"
    assert (result.task, result.difficulty, result.reasoning) == (
        "general",
        "hard",
        "high",
    )


@pytest.mark.parametrize(
    "confidence,category",
    [
        (0.59, "low_confidence"),
        (None, "missing_confidence"),
        (-0.1, "malformed_response"),
        (1.1, "malformed_response"),
        (True, "malformed_response"),
        ("0.9", "malformed_response"),
        (float("nan"), "malformed_response"),
    ],
)
def test_confidence_fallback_keeps_known_cost(monkeypatch, confidence, category):
    response = copy.deepcopy(RESPONSE)
    response["answers"]["difficulty"]["confidence"] = confidence
    install_transport(monkeypatch, response)
    result = analysis.classify(MESSAGES, 2)
    assert result.source == "fallback" and result.error_category == category
    assert result.cost_usd == Decimal("0.0000126") and result.called
    if confidence is None:
        assert result.confidence is None


@pytest.mark.parametrize("change", ["enum", "type", "missing_answer", "model"])
def test_invalid_answer_keeps_usage_and_conservative_defaults(monkeypatch, change):
    response = copy.deepcopy(RESPONSE)
    if change == "enum":
        response["answers"]["task"]["choice"] = "write secrets\x00\ud800"
    elif change == "type":
        response["answers"]["task"]["type"] = "noul"
    elif change == "missing_answer":
        response["answers"].pop("reasoning")
    else:
        response["model"] = "unverified-model\x00"
    install_transport(monkeypatch, response)
    result = analysis.classify(MESSAGES, 2)
    assert result.source == "fallback" and result.raw_usage == RESPONSE["usage"]
    if change == "model":
        assert result.cost_usd is None and result.cost_source == "unknown"
    else:
        assert result.cost_usd is not None and result.cost_source == "observed_usage"
    assert result.error_category in {"malformed_response", "model_mismatch"}
    assert result.task == "general" and result.difficulty == "hard"
    assert "secrets" not in result.model_dump_json()
    result.model_dump_json().encode("utf-8")


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": -1, "output_tokens": 10},
        {"input_tokens": True, "output_tokens": 10},
        {"input_tokens": "secret\x00\ud800", "output_tokens": 10},
    ],
)
def test_invalid_usage_is_unknown_and_safe_for_storage(monkeypatch, usage):
    response = copy.deepcopy(RESPONSE)
    response["usage"] = usage
    install_transport(monkeypatch, response)
    result = analysis.classify(MESSAGES, 2)
    assert result.source == "fallback" and result.error_category == "malformed_usage"
    assert result.cost_usd is None and result.cost_source == "unknown"
    assert "secret" not in result.model_dump_json()
    result.model_dump_json().encode("utf-8")


def test_usage_metadata_does_not_persist_untrusted_extra_fields(monkeypatch):
    response = copy.deepcopy(RESPONSE)
    response["usage"]["secret\x00"] = {"bad": "\ud800"}
    install_transport(monkeypatch, response)
    result = analysis.classify(MESSAGES, 2)
    assert result.source == "jev" and result.raw_usage == RESPONSE["usage"]
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "status,category",
    [
        (401, "authentication"),
        (422, "invalid_request"),
        (429, "rate_limit"),
        (529, "unavailable"),
        (500, "unavailable"),
        (302, "unavailable"),
    ],
)
def test_http_errors_never_retry_or_expose_body(monkeypatch, status, category):
    requests, _ = install_transport(monkeypatch, {"error": "private-key-value"}, status)
    result = analysis.classify(MESSAGES, 2)
    assert len(requests) == 1 and result.called
    assert result.source == "fallback" and result.error_category == category
    assert result.cost_usd is None
    assert "private" not in result.model_dump_json()


@pytest.mark.parametrize(
    "error,category",
    [(httpx2.ReadTimeout, "timeout"), (httpx2.ConnectError, "unavailable")],
)
def test_transport_errors_are_safe_and_unknown_cost(monkeypatch, error, category):
    requests, _ = install_transport(monkeypatch, error=error)
    result = analysis.classify(MESSAGES, 2)
    assert len(requests) == 1 and result.error_category == category
    assert result.source == "fallback" and result.cost_usd is None


def test_whole_call_deadline_cancels_network_work(monkeypatch):
    requests, _ = install_transport(monkeypatch, delay=5)
    started = perf_counter()
    result = analysis.classify(MESSAGES, 0.1)
    assert perf_counter() - started < 1
    assert len(requests) == 1 and requests[0].extensions["cancelled"]
    assert result.called and result.error_category == "timeout"
    assert result.source == "fallback" and result.cost_usd is None


def test_analysis_schema_rejects_unknown_enum_and_out_of_range_confidence():
    with pytest.raises(ValidationError):
        analysis.Analysis(task="unknown")
    with pytest.raises(ValidationError):
        analysis.Analysis(confidence=1.5)
