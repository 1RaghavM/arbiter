from app.schemas import GenerationResult, Message


def generate_mock(messages: list[Message]) -> GenerationResult:
    previous = [message.content for message in messages[:-1] if message.role == "user"]
    text = f"Mock reply to: {messages[-1].content[:200]}"
    if previous:
        text += f"\nEarlier you said: {previous[-1][:200]}"
    return GenerationResult(text=text)
