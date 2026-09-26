from types import SimpleNamespace

import pytest

import src.llm.client as client_module
from src.llm.client import (
    DEFAULT_GROQ_MODEL,
    RECOMMENDATION_RESPONSE_FORMAT,
    GroqLLMClient,
    LLMConfigurationError,
)


class FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content='{"summary":"","recommendations":[]}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeGroq:
    instances = []

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.chat = SimpleNamespace(completions=FakeCompletions())
        self.instances.append(self)


@pytest.fixture(autouse=True)
def fake_groq(monkeypatch):
    FakeGroq.instances.clear()
    monkeypatch.setattr(client_module, "Groq", FakeGroq)


@pytest.mark.parametrize(
    "model",
    ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
)
def test_supported_groq_models_use_strict_structured_output(model):
    client = GroqLLMClient(api_key="test-key", model=model, timeout_seconds=7)
    result = client.complete([{"role": "user", "content": "Return JSON"}])

    sdk = FakeGroq.instances[0]
    assert sdk.init_kwargs == {
        "api_key": "test-key",
        "timeout": 7,
        "max_retries": 0,
    }
    request = sdk.chat.completions.kwargs
    assert request["model"] == model
    assert request["temperature"] == 0.3
    assert request["max_completion_tokens"] == 1000
    assert request["response_format"] == RECOMMENDATION_RESPONSE_FORMAT
    assert request["response_format"]["json_schema"]["strict"] is True
    assert result.startswith("{")


def test_from_env_uses_default_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "12")

    client = GroqLLMClient.from_env()

    assert client.model == DEFAULT_GROQ_MODEL
    assert FakeGroq.instances[0].init_kwargs["timeout"] == 12


def test_unsupported_model_is_rejected_before_sdk_call():
    with pytest.raises(LLMConfigurationError, match="Unsupported GROQ_MODEL"):
        GroqLLMClient(api_key="test-key", model="qwen/qwen3.6-27b")
    assert FakeGroq.instances == []
