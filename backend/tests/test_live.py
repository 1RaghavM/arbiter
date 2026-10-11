import json
import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import analysis, db, providers
from app.config import KEY_ENV, Settings, load_registry
from app.main import app
from app.pipeline import prepare_live
from app.schemas import ChatRequest, GenerationResult
from app.smoke import smoke


@pytest.fixture
def live_client(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for real PostgreSQL tests")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CHAT_MODE", "live")
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    from app import pipeline

    original_route = pipeline.choose_route

    def route(classification, registry, *args):
        registry = registry.model_copy(update={"strong_baseline_key": "openai"})
        return original_route(classification, registry, *args)

    monkeypatch.setattr(pipeline, "choose_route", route)
    monkeypatch.setenv("REQUEST_BUDGET_USD", "0.05")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    db.migrate(url)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "error,cost,status",
    [
        (None, Decimal("0.001"), 200),
        ("timeout", None, 504),
        ("empty_response", Decimal("0.001"), 502),
    ],
)
def test_live_result_and_failure_accounting(
    live_client, monkeypatch, error, cost, status
):
    def generate(model, messages, timeout):
        assert model.key == "openai" and 0 < timeout <= 30
        assert messages[0].content == "test"
        return GenerationResult(
            model_key=model.key,
            provider=model.provider,
            model_id=model.model_id,
            text="response" if not error else "",
            error_category=error,
            input_tokens=10 if cost else None,
            output_tokens=5 if cost else None,
            cost_usd=cost,
            cost_source="observed_usage" if cost else "unknown",
            raw_usage={"input_tokens": 10} if cost else None,
            price_snapshot={"input_usd_per_million": "0.40"},
        )

    monkeypatch.setattr(providers, "generate", generate)
    response = live_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == status
    result = response.json()
    stored = live_client.get(f"/api/runs/{result['run_id']}").json()
    call = stored["calls"][0]
    assert stored["mode"] == "live" and stored["config_version"] != "mock-v1"
    assert call["model_id"] == "gpt-4.1-mini-2025-04-14"
    assert call["provider"] == "openai" and call["input_tokens"] == (
        10 if cost else None
    )
    assert call["price_snapshot"]["input_usd_per_million"] == "0.40"
    assert Decimal(call["price_snapshot"]["reserved_cost_usd"]) > 0
    assert stored["cost_complete"] == (cost is not None)
    assert stored["total_cost_usd"] == (float(cost) if cost is not None else None)
    assert stored["known_cost_usd"] == float(cost or 0)
    if not error:
        assert result["mode"] == "live" and result["status"] == "unverified"


@pytest.mark.parametrize(
    "variable,value",
    [
        ("OPENAI_API_KEY", ""),
        ("REQUEST_BUDGET_USD", "0.0000001"),
        ("REQUEST_BUDGET_USD", ""),
    ],
)
def test_preflight_blocks_provider(live_client, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    calls = []
    monkeypatch.setattr(providers, "generate", lambda *args: calls.append(args))
    response = live_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == 503 and calls == []


def test_live_db_failure_prevents_paid_call(live_client, monkeypatch):
    import psycopg

    def unavailable(*args):
        raise psycopg.OperationalError("private connection")

    calls = []
    monkeypatch.setattr(db, "create_run", unavailable)
    monkeypatch.setattr(providers, "generate", lambda *args: calls.append(args))
    response = live_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == 503 and calls == []
    assert "private" not in response.text


def test_config_is_safe_and_unknown_model_is_not_mock(monkeypatch):
    monkeypatch.setenv("CHAT_MODE", "live")
    monkeypatch.setenv("FIXED_MODEL_KEY", "missing")
    for key in KEY_ENV.values():
        monkeypatch.delenv(key, raising=False)
    with TestClient(app) as client:
        data = client.get("/api/config").json()
    assert data["mode"] == "live" and data["model_key"] is None
    assert data["selection"] == "routed"
    assert all(p["status"] == "missing_credentials" for p in data["providers"])
    assert all("api_key" not in p for p in data["providers"])


def test_smoke_preflights_entire_budget_and_missing_credentials(monkeypatch):
    registry = load_registry()
    for key in KEY_ENV.values():
        monkeypatch.delenv(key, raising=False)
    outcomes = smoke(None, registry, Decimal("0.05"), ["openai", "anthropic", "google"])
    assert all(row["status"] == "blocked" for row in outcomes)
    for key in KEY_ENV.values():
        monkeypatch.setenv(key, "offline-test")
    with pytest.raises(ValueError, match="reservations"):
        smoke(None, registry, Decimal("0.00001"), ["openai", "anthropic", "google"])
    with pytest.raises(ValueError, match="Unknown"):
        smoke(None, registry, Decimal("1"), ["typo"])
    messages = ChatRequest(messages=[{"role": "user", "content": "test"}]).messages
    with pytest.raises(ValueError, match="explicit positive"):
        prepare_live(Settings(mode="live"), registry, messages)


@pytest.mark.parametrize("invalid_text", ["bad\x00text", "bad\ud800text"])
def test_malformed_paid_text_retains_usage_in_postgres(
    live_client, monkeypatch, invalid_text
):
    import httpx2

    original = providers.openai.AsyncOpenAI
    payload = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": invalid_text}],
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    monkeypatch.setattr(
        providers.openai,
        "AsyncOpenAI",
        lambda **kwargs: original(
            **kwargs,
            http_client=httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    lambda request: httpx2.Response(
                        200,
                        content=json.dumps(payload),
                        headers={"content-type": "application/json"},
                    )
                )
            ),
        ),
    )
    response = live_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert response.status_code == 502
    stored = live_client.get(f"/api/runs/{response.json()['run_id']}").json()
    assert stored["cost_complete"] and stored["total_cost_usd"] > 0
    assert stored["calls"][0]["input_tokens"] == 10
    assert stored["calls"][0]["output"]["text"] == ""
    assert stored["calls"][0]["error"]["code"] == "malformed_response"


def test_expired_deadline_skips_generation(live_client, monkeypatch):
    from time import perf_counter
    from uuid import uuid4

    from app.pipeline import run_chat

    calls = []
    monkeypatch.setattr(providers, "generate", lambda *args: calls.append(args))
    result = run_chat(
        app.state.pool,
        uuid4(),
        ChatRequest(messages=[{"role": "user", "content": "test"}]),
        Settings(mode="live", request_budget_usd="0.05"),
        load_registry(),
        perf_counter() - 91,
        fixed=True,
    )
    assert not calls and result.status == "error"
    assert result.total_cost_usd == 0


def test_smoke_charges_unknown_reservation_and_stops_on_budget(monkeypatch):
    from app import smoke as smoke_module
    from app.config import reserve_cost
    from app.schemas import ChatResult

    registry = load_registry()
    for key in KEY_ENV.values():
        monkeypatch.setenv(key, "offline-test")
    messages = ChatRequest(
        messages=[{"role": "user", "content": "Reply exactly: smoke OK"}]
    ).messages
    reservations = [reserve_cost(model, messages) for model in registry.models]
    budget = Decimal("0.05")
    calls = []

    def run(pool, run_id, body, settings, registry, started, *, fixed=False):
        calls.append(settings.fixed_model_key)
        cost = (
            None if len(calls) == 1 else budget - reservations[2] - reservations[0] / 2
        )
        return ChatResult(
            run_id=run_id,
            status="unverified",
            total_cost_usd=cost,
            cost_complete=cost is not None,
            attempts=[GenerationResult(text="ok")],
        )

    monkeypatch.setattr(smoke_module, "run_chat", run)
    outcomes = smoke_module.smoke(
        None, registry, budget, [m.key for m in registry.models]
    )
    assert calls == ["openai", "anthropic"]
    assert outcomes[-1]["reason"] == "budget"


def test_smoke_stops_on_persistence_failure(monkeypatch):
    import psycopg

    from app import smoke as smoke_module

    for key in KEY_ENV.values():
        monkeypatch.setenv(key, "offline-test")
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise psycopg.OperationalError("private connection details")

    monkeypatch.setattr(smoke_module, "run_chat", fail)
    result = smoke_module.smoke(
        None, load_registry(), Decimal("1"), ["openai", "google"]
    )
    assert len(calls) == 1 and result[0]["reason"] == "persistence_error"
    assert "private" not in str(result)


@pytest.mark.parametrize("budget", ["nope", "NaN", "Infinity", "-1", "0"])
def test_smoke_rejects_invalid_cli_budget(monkeypatch, budget, capsys):
    from app.smoke import main

    monkeypatch.setattr("sys.argv", ["smoke", "--budget-usd", budget])
    assert main() == 2
    assert "configuration invalid" in capsys.readouterr().out


def test_routing_persists_classifier_and_combined_cost(live_client, monkeypatch):
    classification = analysis.Analysis(
        task="coding",
        difficulty="easy",
        reasoning="low",
        confidence=0.95,
        source="jev",
        called=True,
        cost_usd=Decimal("0.00001"),
        cost_source="observed_usage",
        raw_usage={"input_tokens": 238, "output_tokens": 0},
    )
    monkeypatch.setattr(analysis, "classify", lambda *args: classification)
    monkeypatch.setattr(
        providers,
        "generate",
        lambda model, *args: GenerationResult(
            model_key=model.key,
            provider=model.provider,
            model_id=model.model_id,
            text="ok",
            cost_usd=Decimal("0.0001"),
            cost_source="observed_usage",
        ),
    )
    response = live_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "test"}]}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["analysis"]["source"] == "jev"
    assert result["route_decisions"][0]["selected_key"] == "openai"
    assert Decimal(result["total_cost_usd"]) == Decimal("0.00011")
    stored = live_client.get(f"/api/runs/{result['run_id']}").json()
    assert [c["stage"] for c in stored["calls"]] == ["classify", "generate"]
    assert stored["analysis"] == result["analysis"]
    assert stored["route_decisions"] == result["route_decisions"]


def test_unknown_classifier_cost_remains_incomplete(live_client, monkeypatch):
    monkeypatch.setattr(
        analysis,
        "classify",
        lambda *args: analysis.Analysis(
            source="fallback",
            called=True,
            error_category="timeout",
            cost_usd=None,
        ),
    )
    monkeypatch.setattr(
        providers,
        "generate",
        lambda model, *args: GenerationResult(
            model_key=model.key,
            text="ok",
            cost_usd=Decimal("0.0001"),
        ),
    )
    result = live_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "test"}]}
    ).json()
    assert result["total_cost_usd"] is None and not result["cost_complete"]
    assert Decimal(result["known_cost_usd"]) == Decimal("0.0001")
    assert "fallback" in " ".join(result["warnings"])


def test_classifier_overrun_stops_generation_and_retains_cost(live_client, monkeypatch):
    monkeypatch.setattr(
        analysis,
        "classify",
        lambda *args: analysis.Analysis(
            source="jev",
            confidence=0.9,
            called=True,
            cost_usd=Decimal("0.06"),
            cost_source="observed_usage",
        ),
    )

    def unexpected(*args):
        raise AssertionError("Must not generate after budget exhausted")

    monkeypatch.setattr(providers, "generate", unexpected)
    response = live_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "test"}]}
    )
    assert response.status_code == 503
    stored = live_client.get(f"/api/runs/{response.json()['run_id']}").json()
    assert len(stored["calls"]) == 1 and stored["total_cost_usd"] == 0.06
    assert stored["error"]["code"] == "no_eligible_model"


def test_classifier_deadline_retains_usage_without_generation(live_client, monkeypatch):
    from time import perf_counter

    from app import pipeline

    now = perf_counter()

    def classify(*args):
        monkeypatch.setattr(pipeline, "perf_counter", lambda: now + 100)
        return analysis.Analysis(
            source="jev", confidence=0.9, called=True, cost_usd=Decimal(".00001")
        )

    monkeypatch.setattr(analysis, "classify", classify)

    def unexpected(*args):
        raise AssertionError("Must not generate after deadline")

    monkeypatch.setattr(providers, "generate", unexpected)
    response = live_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "test"}]}
    )
    assert response.status_code == 504
    stored = live_client.get(f"/api/runs/{response.json()['run_id']}").json()
    assert len(stored["calls"]) == 1 and stored["total_cost_usd"] == 0.00001


def test_analysis_write_failure_prevents_generation(live_client, monkeypatch):
    import psycopg

    monkeypatch.setattr(
        analysis,
        "classify",
        lambda *args: analysis.Analysis(
            source="jev", confidence=0.9, called=True, cost_usd=Decimal(".00001")
        ),
    )

    def fail(*args):
        raise psycopg.OperationalError("private details")

    def unexpected(*args):
        raise AssertionError("Must not generate after persistence failure")

    monkeypatch.setattr(db, "record_analysis", fail)
    monkeypatch.setattr(providers, "generate", unexpected)
    response = live_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "test"}]}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "persistence_error"
    assert "private" not in response.text


def test_five_paid_stages_and_attempt_labels_persist(live_client, monkeypatch):
    from app import evaluation

    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test")
    monkeypatch.setenv("REQUEST_BUDGET_USD", "1")
    monkeypatch.setattr(
        analysis,
        "classify",
        lambda *args: analysis.Analysis(
            source="jev",
            task="general",
            difficulty="easy",
            reasoning="low",
            confidence=0.9,
            called=True,
            cost_usd=Decimal(".00001"),
        ),
    )
    monkeypatch.setattr(
        providers,
        "generate",
        lambda model, *args: GenerationResult(
            model_key=model.key,
            provider=model.provider,
            model_id=model.model_id,
            text=f"answer from {model.key}",
            cost_usd=Decimal(".001"),
        ),
    )

    def evaluate(model, messages, generated, timeout):
        passed = generated.model_key == "anthropic"
        return evaluation.Evaluation(
            status="pass" if passed else "fail",
            correctness=4 if passed else 1,
            relevance=4,
            completeness=4,
            reason="offline fixture",
        ), GenerationResult(
            model_key=model.key,
            provider=model.provider,
            model_id=model.model_id,
            text="offline scores",
            cost_usd=Decimal(".002"),
        )

    monkeypatch.setattr(evaluation, "evaluate", evaluate)
    response = live_client.post(
        "/api/chat", json={"messages": [{"role": "user", "content": "test"}]}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "passed" and result["final_model"] == "anthropic"
    assert result["escalation_reason"] == "quality_failed"
    assert Decimal(result["total_cost_usd"]) == Decimal(".00601")
    stored = live_client.get(f"/api/runs/{result['run_id']}").json()
    assert [call["stage"] for call in stored["calls"]] == [
        "classify",
        "generate",
        "evaluate",
        "generate",
        "evaluate",
    ]
    assert [grade["attempt"] for grade in stored["evaluations"]] == [1, 2]
    assert [grade["status"] for grade in stored["evaluations"]] == ["fail", "pass"]
    assert stored["calls"][2]["attempt"] == 1 and stored["calls"][4]["attempt"] == 2
    assert stored["rubric_version"] == "rubric-v1"
