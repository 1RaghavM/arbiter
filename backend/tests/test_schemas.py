import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "system", "content": "Hi"}],
        [{"role": "user", "content": " \n"}],
        [{"role": "assistant", "content": "Hi"}],
        [{"role": "user", "content": "x"}] * 11,
        [{"role": "user", "content": "x" * 12001}],
        [
            {"role": "assistant", "content": "x" * 6000},
            {"role": "user", "content": "x" * 6001},
        ],
        [{"role": "user", "content": "\x00"}],
        [{"role": "user", "content": "\ud800"}],
    ],
)
def test_invalid_history(messages):
    with pytest.raises(ValidationError):
        ChatRequest(messages=messages)


def test_history_boundary_preserves_context():
    messages = [{"role": "user", "content": "x" * 1200}] * 10
    assert ChatRequest(messages=messages).model_dump()["messages"] == messages
