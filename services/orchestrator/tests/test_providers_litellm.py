"""Tests for LiteLLMProvider."""
from types import SimpleNamespace

import pytest

from orchestrator.events import FinalDoneEvent, ThinkingTokenEvent, TokenEvent
from orchestrator.providers.litellm_provider import LiteLLMProvider


async def fake_acompletion_non_streaming(*, model, messages, stream, api_key, **kwargs):
    """Mimics litellm.acompletion(stream=False) — returns a coroutine that
    resolves to a non-streaming response object."""
    assert stream is False
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Hi there.", role="assistant"),
                finish_reason="stop",
            )
        ]
    )


async def test_non_streaming_emits_token_then_done(monkeypatch):
    """Non-streaming: LiteLLM returns one response, provider yields one
    TokenEvent with the full content + FinalDoneEvent."""
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion_non_streaming)

    provider = LiteLLMProvider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test",
        timeout=30.0,
    )
    events = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hello"}], stream=False
        )
    ]
    assert len(events) == 2
    assert isinstance(events[0], TokenEvent)
    assert events[0].delta == "Hi there."
    assert isinstance(events[1], FinalDoneEvent)


async def fake_acompletion_streaming(*, model, messages, stream, api_key, **kwargs):
    """Mimics litellm.acompletion(stream=True) — returns an async iterator
    of chunk-like objects shaped after LiteLLM's actual streaming output."""
    assert stream is True

    async def gen():
        # LiteLLM normalises chunks to look like OpenAI:
        # chunk.choices[0].delta.content (str) carries visible text
        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi", role="assistant"), finish_reason=None)]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" there", role=None), finish_reason=None)]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, role=None), finish_reason="stop")]),
        ]
        for c in chunks:
            yield c

    return gen()


async def test_streaming_emits_token_per_chunk(monkeypatch):
    """Streaming: yields one TokenEvent per non-empty content delta, then FinalDoneEvent."""
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion_streaming)

    provider = LiteLLMProvider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test",
        timeout=30.0,
    )
    events = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hello"}], stream=True
        )
    ]
    deltas = [e.delta for e in events if isinstance(e, TokenEvent)]
    assert deltas == ["Hi", " there"]
    assert isinstance(events[-1], FinalDoneEvent)


async def fake_acompletion_streaming_with_thinking(*, model, messages, stream, api_key, **kwargs):
    """Mimics LiteLLM streaming an Anthropic extended-thinking response.

    Anthropic emits thinking-block deltas BEFORE visible content. LiteLLM
    surfaces them on `delta.thinking_blocks` or `delta.reasoning_content`
    depending on version/provider. Test both surfaces.
    """
    assert stream is True

    async def gen():
        chunks = [
            # thinking via `thinking_blocks` (Anthropic preferred path)
            SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    role="assistant",
                    thinking_blocks=[{"type": "thinking", "thinking": "user wants a greeting"}],
                ),
                finish_reason=None,
            )]),
            # thinking via `reasoning_content` (alternate surface)
            SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    role=None,
                    reasoning_content=" then I'll respond",
                ),
                finish_reason=None,
            )]),
            # visible content
            SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content="Hi!", role=None),
                finish_reason=None,
            )]),
            # finish
            SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, role=None),
                finish_reason="stop",
            )]),
        ]
        for c in chunks:
            yield c

    return gen()


async def test_streaming_emits_thinking_then_content(monkeypatch):
    """When LiteLLM exposes reasoning (Anthropic extended thinking), emit
    ThinkingTokenEvent for thinking deltas and TokenEvent for visible content.

    Both `delta.thinking_blocks` and `delta.reasoning_content` surfaces
    must be handled so the provider works across LiteLLM versions."""
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion_streaming_with_thinking)

    provider = LiteLLMProvider(
        provider_name="anthropic",
        model="claude-opus-4-7",
        api_key="sk-ant-test",
    )
    events = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hi"}], stream=True
        )
    ]

    thinking_deltas = [e.delta for e in events if isinstance(e, ThinkingTokenEvent)]
    token_deltas = [e.delta for e in events if isinstance(e, TokenEvent)]
    assert thinking_deltas == ["user wants a greeting", " then I'll respond"]
    assert token_deltas == ["Hi!"]
    assert isinstance(events[-1], FinalDoneEvent)


from orchestrator.events import ErrorEvent


async def fake_acompletion_raising(*, model, messages, stream, api_key, **kwargs):
    """Simulates LiteLLM raising on auth failure."""
    import litellm
    raise litellm.AuthenticationError(
        message="invalid api key",
        llm_provider="anthropic",
        model=model,
    )


async def test_auth_error_emits_error_event(monkeypatch):
    """LiteLLM raises an APIError subclass → provider yields ErrorEvent + FinalDoneEvent."""
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion_raising)

    provider = LiteLLMProvider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="bogus",
    )
    events = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hi"}], stream=False
        )
    ]

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    done_events = [e for e in events if isinstance(e, FinalDoneEvent)]
    assert len(error_events) == 1
    assert "api key" in error_events[0].message.lower() or "auth" in error_events[0].message.lower()
    assert len(done_events) == 1


from orchestrator.events import ToolCallRequestEvent


async def fake_acompletion_with_tool_calls(*, model, messages, stream, api_key, **kwargs):
    """Simulates LiteLLM returning a tool-call response (Anthropic Claude shape)."""
    assert stream is False
    assert kwargs.get("tools") is not None  # forwarded
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="toolu_abc",
                            type="function",
                            function=SimpleNamespace(
                                name="browser.search",
                                arguments='{"query":"cats"}',
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )


async def test_non_streaming_with_tools_emits_tool_call_request(monkeypatch):
    """LiteLLM returns tool_calls → provider yields ToolCallRequestEvent."""
    import litellm

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion_with_tool_calls)

    provider = LiteLLMProvider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test",
    )
    events = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "search cats"}],
            stream=False,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "browser.search",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        )
    ]

    tc_events = [e for e in events if isinstance(e, ToolCallRequestEvent)]
    done_events = [e for e in events if isinstance(e, FinalDoneEvent)]
    token_events = [e for e in events if isinstance(e, TokenEvent)]
    assert len(tc_events) == 1
    assert tc_events[0].tool_calls[0]["id"] == "toolu_abc"
    assert tc_events[0].tool_calls[0]["function"]["name"] == "browser.search"
    assert tc_events[0].tool_calls[0]["function"]["arguments"] == '{"query":"cats"}'
    assert len(done_events) == 1
    assert token_events == []
