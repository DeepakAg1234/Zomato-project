"""Groq chat client configured entirely through environment variables."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol, TypedDict

from dotenv import load_dotenv
from groq import Groq

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
SUPPORTED_GROQ_MODELS = frozenset(
    {
        DEFAULT_GROQ_MODEL,
        "qwen/qwen3.8-27b",
    }
)

RECOMMENDATION_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "restaurant_recommendations",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "recommendations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "rank": {"type": "integer", "minimum": 1},
                            "explanation": {"type": "string"},
                        },
                        "required": ["id", "rank", "explanation"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "recommendations"],
            "additionalProperties": False,
        },
    },
}


class ChatMessage(TypedDict):
    role: str
    content: str


class ChatClient(Protocol):
    def complete(self, messages: Sequence[ChatMessage]) -> str: ...


class LLMConfigurationError(RuntimeError):
    pass


class GroqLLMClient:
    """Official Groq SDK adapter with bounded latency and structured output."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_GROQ_MODEL,
        timeout_seconds: float = 20.0,
    ):
        if not api_key:
            raise LLMConfigurationError("GROQ_API_KEY must be configured")
        if model not in SUPPORTED_GROQ_MODELS:
            choices = ", ".join(sorted(SUPPORTED_GROQ_MODELS))
            raise LLMConfigurationError(
                f"Unsupported GROQ_MODEL {model!r}; choose one of: {choices}"
            )
        if timeout_seconds <= 0:
            raise LLMConfigurationError("GROQ_TIMEOUT_SECONDS must be greater than zero")
        self.model = model
        self._client = Groq(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    @classmethod
    def from_env(cls) -> GroqLLMClient:
        load_dotenv()
        try:
            timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
        except ValueError as exc:
            raise LLMConfigurationError("GROQ_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            api_key=os.getenv("GROQ_API_KEY", ""),
            model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
            timeout_seconds=timeout,
        )

    def complete(self, messages: Sequence[ChatMessage]) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=list(messages),  # type: ignore[arg-type]
            temperature=0.3,
            max_completion_tokens=1000,
            response_format=RECOMMENDATION_RESPONSE_FORMAT,  # type: ignore[arg-type]
        )
        content = response.choices[0].message.content
        return content or ""


# Compatibility for callers that imported the pre-Groq generic name.
LLMClient = GroqLLMClient
