"""Dispatcher — pick the right Provider for the active brain.

Called per-request by routes/chat.py. Reads the brain id from state and
returns a Provider instance configured for that brain.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from orchestrator.catalog import BrainEntry
from orchestrator.events import ErrorEvent, Event, FinalDoneEvent
from orchestrator.providers.base import Provider
from orchestrator.providers.litellm_provider import LiteLLMProvider
from orchestrator.providers.ollama import OllamaProvider


class _MissingKeyProvider(Provider):
    """Stub that yields a single ErrorEvent. Used when a cloud brain is
    selected but no API key was provided."""

    def __init__(self, *, brain_id: str, required_env: str) -> None:
        self._missing_key_brain_id = brain_id
        self._required_env = required_env

    async def chat(self, messages, *, stream=False, tools=None) -> AsyncIterator[Event]:
        yield ErrorEvent(
            message=(
                f"brain '{self._missing_key_brain_id}' requires "
                f"{self._required_env} env var, but it is not set"
            )
        )
        yield FinalDoneEvent()


def dispatch_for_brain(
    brain: BrainEntry,
    *,
    ollama_url: str,
    request_timeout: float,
    api_key: str | None,
) -> Provider:
    """Construct a Provider for this brain."""
    if brain.kind == "ollama":
        return OllamaProvider(
            base_url=ollama_url, model=brain.model, timeout=request_timeout,
        )
    if brain.kind == "openai-compatible":
        return OllamaProvider(
            base_url=brain.url, model=brain.model, timeout=request_timeout,
        )
    if brain.kind == "cloud-litellm":
        if not api_key:
            return _MissingKeyProvider(
                brain_id=brain.id, required_env=brain.requires_key or "API_KEY",
            )
        return LiteLLMProvider(
            provider_name=brain.model.split("/")[0],
            model=brain.model,
            api_key=api_key,
            timeout=request_timeout,
        )
    raise ValueError(f"unknown brain kind: {brain.kind}")
