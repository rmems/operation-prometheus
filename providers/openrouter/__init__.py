"""Thin OpenRouter HTTP adapter (OpenAI-compatible chat completions)."""

from .client import (
    CHAT_COMPLETIONS_URL,
    LOCKED_MODEL,
    OpenRouterClient,
    OpenRouterError,
    PlannedRequest,
    assert_locked_model,
    build_chat_request,
    redact_planned_request,
)

__all__ = [
    "CHAT_COMPLETIONS_URL",
    "LOCKED_MODEL",
    "OpenRouterClient",
    "OpenRouterError",
    "PlannedRequest",
    "assert_locked_model",
    "build_chat_request",
    "redact_planned_request",
]
