from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import summaries
from app.config import Settings, load_registry
from app.schemas import GenerationResult


class Pool:
    def __init__(self):
        self.writes = []

    @contextmanager
    def connection(self):
        yield self

    def execute(self, sql, params):
        self.writes.append((sql, params))


@pytest.mark.parametrize(
    "status, budget, upstream, expected",
    [
        ("passed", "1", False, None),
        ("running", "1", False, 422),
        ("passed", "0.001", False, 422),
        ("passed", "1", True, 502),
    ],
)
def test_summary(monkeypatch, status, budget, upstream, expected):
    pool = Pool()
    run_id = uuid4()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline")
    monkeypatch.setattr(
        summaries.db,
        "read_run",
        lambda *_: {
            "id": run_id,
            "status": status,
            "messages": [{"role": "user", "content": "Hello"}],
            "final_answer": "Hi",
        },
    )
    calls = []

    def generate(model, messages, timeout):
        assert pool.writes
        assert model.model_id == "claude-sonnet-5-5"
        assert str(run_id) in messages[0].content
        assert "student experiment" in messages[0].content
        calls.append(model)
        return GenerationResult(
            text="# Summary", error_category="timeout" if upstream else None
        )

    monkeypatch.setattr(summaries.providers, "generate", generate)
    args = (
        pool,
        summaries.SummaryRequest(run_ids=[run_id, run_id]),
        Settings(request_budget_usd=Decimal(budget)),
        load_registry(),
    )
    if expected:
        with pytest.raises(HTTPException) as error:
            summaries.summarize(*args)
        assert error.value.status_code == expected
    else:
        assert summaries.summarize(*args) == "# Summary"
        assert len(pool.writes) == 2
        assert len(pool.writes[0][1][1].obj) == 1
    assert len(calls) == (0 if status == "running" or budget == "0.001" else 1)
