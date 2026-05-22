"""Tests for OllamaProvider."""
import json
from typing import Any

import httpx
import pytest
import respx

from orchestrator.events import (
    ErrorEvent,
    FinalDoneEvent,
    TokenEvent,
    ToolCallRequestEvent,
)
from orchestrator.providers.ollama import OllamaProvider


@pytest.fixture
def ollama_url():
    return "http://test-ollama:11434"


async def _collect(gen) -> list:
    out = []
    async for ev in gen:
        out.append(ev)
    return out


@respx.mock
async def test_chat_non_streaming_returns_content(ollama_url):
    respx.post(f"{ollama_url}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Hello back."}}
                ]
            },
        )
    )
    p = OllamaProvider(base_url=ollama_url, model="qwen3:4b")
    events = await _collect(p.chat([{"role": "user", "content": "hi"}], stream=False))
    text_parts = [e.delta for e in events if isinstance(e, TokenEvent)]
    assert "".join(text_parts) == "Hello back."
    assert any(isinstance(e, FinalDoneEvent) for e in events)


@respx.mock
async def test_chat_includes_model_field_in_request(ollama_url):
    captured: dict[str, Any] = {}

    def _handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    respx.post(f"{ollama_url}/v1/chat/completions").mock(side_effect=_handler)
    p = OllamaProvider(base_url=ollama_url, model="qwen3:4b")
    await _collect(p.chat([{"role": "user", "content": "hi"}], stream=False))
    assert captured["body"]["model"] == "qwen3:4b"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
async def test_chat_tool_call_yields_tool_call_request_event(ollama_url):
    respx.post(f"{ollama_url}/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "wiki.list", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
        )
    )
    p = OllamaProvider(base_url=ollama_url, model="qwen3:4b")
    events = await _collect(p.chat([{"role": "user", "content": "hi"}], stream=False))
    tool_events = [e for e in events if isinstance(e, ToolCallRequestEvent)]
    assert len(tool_events) == 1
    assert tool_events[0].tool_calls[0]["function"]["name"] == "wiki.list"


@respx.mock
async def test_chat_http_error_yields_error_event_not_exception(ollama_url):
    respx.post(f"{ollama_url}/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="boom")
    )
    p = OllamaProvider(base_url=ollama_url, model="qwen3:4b")
    events = await _collect(p.chat([{"role": "user", "content": "hi"}], stream=False))
    assert any(isinstance(e, ErrorEvent) for e in events)
    assert any(isinstance(e, FinalDoneEvent) for e in events)
