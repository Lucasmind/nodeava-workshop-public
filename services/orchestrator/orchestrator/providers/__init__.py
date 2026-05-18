"""Provider abstraction — extensible chat backends.

Plan #1 introduced LocalLlamaProvider and a static build_provider(settings).
Plan #2 adds LiteLLMProvider and replaces the static factory with
pick_provider(request, body) — a per-request factory that honors
body fields (`provider`, `model`) and headers (`X-Provider-Key`).
"""
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import ErrorEvent, Event, FinalDoneEvent
from orchestrator.providers.base import Provider
from orchestrator.providers.dispatcher import dispatch_for_brain
from orchestrator.providers.litellm_provider import LiteLLMProvider
from orchestrator.providers.ollama import OllamaProvider

__all__ = ["Provider", "OllamaProvider", "LiteLLMProvider", "pick_provider", "dispatch_for_brain"]


def pick_provider(request: Any, body: dict[str, Any]) -> Provider:
    """Return the Provider to use for this request.

    Selection precedence:
      1. body["provider"] (request-level override)
      2. settings.provider (deploy-level default)
      3. Fall back to "local"

    For local: reuse the shared instance at app.state.local_provider.
    For cloud (anything else): construct a fresh LiteLLMProvider per
    request with credentials from `X-Provider-Key` header. If the
    header is missing, return a stub provider that yields a single
    ErrorEvent — the caller never sees an unhandled exception.
    """
    settings = request.app.state.settings
    chosen = (body.get("provider") or settings.provider or "local").lower()

    if chosen == "local":
        return request.app.state.local_provider

    api_key = request.headers.get("X-Provider-Key") or request.headers.get("x-provider-key") or ""
    if not api_key:
        return _MissingKeyProvider(provider_name=chosen)

    model = body.get("model") or settings.provider_model or ""
    return LiteLLMProvider(
        provider_name=chosen,
        model=model,
        api_key=api_key,
        timeout=settings.request_timeout,
    )


class _MissingKeyProvider(Provider):
    """Returned when the caller chose a cloud provider but supplied no API key.
    Yields a single ErrorEvent + FinalDoneEvent — the route layer treats this
    identically to a real provider failure."""

    def __init__(self, *, provider_name: str) -> None:
        self._provider_name = provider_name

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Event]:
        yield ErrorEvent(
            message=(
                f"Missing API key for provider '{self._provider_name}'. "
                f"Send the key via the X-Provider-Key request header."
            )
        )
        yield FinalDoneEvent()
