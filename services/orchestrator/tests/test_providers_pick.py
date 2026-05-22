"""Tests for pick_provider — the per-request provider factory."""
from types import SimpleNamespace

import pytest

from orchestrator.events import ErrorEvent, FinalDoneEvent
from orchestrator.providers import pick_provider
from orchestrator.providers.litellm_provider import LiteLLMProvider
from orchestrator.providers.ollama import OllamaProvider


def _fake_app(*, settings_provider: str = "local", settings_provider_model: str = ""):
    """Construct a minimal app-like object with the fields pick_provider reads."""
    settings = SimpleNamespace(
        provider=settings_provider,
        provider_model=settings_provider_model,
        ollama_url="http://localhost:11434",
        request_timeout=300.0,
    )
    state = SimpleNamespace(
        settings=settings,
        local_provider=OllamaProvider(
            base_url=settings.ollama_url,
            model="qwen3:4b",
            timeout=settings.request_timeout,
        ),
    )
    return SimpleNamespace(state=state)


def _fake_request(*, app, body: dict | None = None, headers: dict | None = None):
    return SimpleNamespace(
        app=app,
        _body=body or {},
        headers=headers or {},
    )


def test_default_local_when_no_override():
    """No body/header override + settings.provider="local" → returns the shared OllamaProvider."""
    app = _fake_app()
    req = _fake_request(app=app)
    p = pick_provider(req, body={})
    assert p is app.state.local_provider


def test_body_override_to_anthropic_with_header_key():
    """body.provider="anthropic" + X-Provider-Key → LiteLLMProvider with that key."""
    app = _fake_app()
    req = _fake_request(
        app=app, headers={"X-Provider-Key": "sk-ant-real"}
    )
    p = pick_provider(req, body={"provider": "anthropic", "model": "claude-haiku-4-5-20251001"})
    assert isinstance(p, LiteLLMProvider)


async def test_missing_api_key_yields_error_event():
    """Picking a cloud provider without an X-Provider-Key produces a Provider whose
    chat() emits a single ErrorEvent + FinalDoneEvent — no upstream call attempted."""
    app = _fake_app()
    req = _fake_request(app=app, headers={})
    p = pick_provider(req, body={"provider": "openai", "model": "gpt-4o-mini"})

    events = [
        e async for e in p.chat([{"role": "user", "content": "hi"}], stream=False)
    ]
    assert len(events) == 2
    assert isinstance(events[0], ErrorEvent)
    assert "api key" in events[0].message.lower() or "x-provider-key" in events[0].message.lower()
    assert isinstance(events[1], FinalDoneEvent)


def test_settings_default_to_anthropic_with_env_key():
    """Settings.provider=anthropic + header key → LiteLLMProvider even without body override."""
    app = _fake_app(
        settings_provider="anthropic",
        settings_provider_model="claude-haiku-4-5-20251001",
    )
    req = _fake_request(app=app, headers={"X-Provider-Key": "sk-ant-env"})
    p = pick_provider(req, body={})
    assert isinstance(p, LiteLLMProvider)


async def test_missing_key_provider_accepts_tools_kwarg():
    """_MissingKeyProvider.chat() must accept tools= kwarg so the agentic loop
    doesn't TypeError when a cloud provider is chosen without an API key."""
    from orchestrator.providers import _MissingKeyProvider

    p = _MissingKeyProvider(provider_name="openai")
    events = [
        e async for e in p.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=[{"type": "function", "function": {"name": "x", "parameters": {}}}],
        )
    ]
    # Same behavior as without tools: ErrorEvent + FinalDoneEvent
    assert len(events) == 2
    from orchestrator.events import ErrorEvent, FinalDoneEvent
    assert isinstance(events[0], ErrorEvent)
    assert isinstance(events[1], FinalDoneEvent)
