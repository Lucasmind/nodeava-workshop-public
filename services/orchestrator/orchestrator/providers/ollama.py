"""OllamaProvider — chat client for a host-installed Ollama server.

Talks Ollama's OpenAI-compatible endpoint at <base_url>/v1/chat/completions.
Critical difference vs the old LocalLlamaProvider: Ollama REQUIRES a `model`
field in the request body. The provider stores the model name at construction
and includes it in every request.

Mirrors LocalLlamaProvider's error contract: HTTP failures and connection
errors do NOT raise out of the async generator; instead they yield an
ErrorEvent followed by FinalDoneEvent. The route layer relies on this.
"""
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from orchestrator.events import (
    ErrorEvent,
    Event,
    FinalDoneEvent,
    TokenEvent,
    ToolCallRequestEvent,
)
from orchestrator.providers.base import Provider

log = logging.getLogger("orchestrator.providers.ollama")


class OllamaProvider(Provider):
    """OpenAI-compatible chat client for Ollama.

    The chat endpoint path is a class attribute so subclasses (e.g.
    LMStudioProvider, which targets LM Studio's native /api/v0/chat/completions)
    can reuse this provider's streaming + tool_call parsing unchanged — the wire
    format is identical OpenAI-shaped SSE.
    """

    _CHAT_PATH = "/v1/chat/completions"

    def __init__(self, *, base_url: str, model: str, timeout: float = 300.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Event]:
        if stream:
            async for event in self._chat_streaming(messages, tools):
                yield event
        else:
            async for event in self._chat_non_streaming(messages, tools):
                yield event

    async def _chat_non_streaming(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[Event]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}{self._CHAT_PATH}",
                    json=payload,
                )
                if resp.status_code >= 400:
                    body = resp.text[:200]
                    log.warning("ollama HTTP %d: %s", resp.status_code, body)
                    yield ErrorEvent(message=f"ollama returned HTTP {resp.status_code}")
                    yield FinalDoneEvent()
                    return
                data = resp.json()
        except httpx.HTTPError as e:
            log.warning("ollama connection error: %s", e)
            yield ErrorEvent(message=f"ollama connection error: {e}")
            yield FinalDoneEvent()
            return

        message = (data.get("choices") or [{}])[0].get("message") or {}
        raw_tool_calls = message.get("tool_calls") or []
        if raw_tool_calls:
            yield ToolCallRequestEvent(tool_calls=raw_tool_calls)
            yield FinalDoneEvent()
            return

        content = message.get("content") or ""
        if content:
            yield TokenEvent(delta=content)
        yield FinalDoneEvent()

    async def _chat_streaming(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[Event]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}{self._CHAT_PATH}",
                    json=payload,
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode(errors="replace")[:200]
                        log.warning("ollama HTTP %d: %s", resp.status_code, body)
                        yield ErrorEvent(
                            message=f"ollama returned HTTP {resp.status_code}"
                        )
                        yield FinalDoneEvent()
                        return

                    accumulated_tool_calls: list[dict[str, Any]] = []
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield TokenEvent(delta=content)
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            while len(accumulated_tool_calls) <= idx:
                                accumulated_tool_calls.append(
                                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                                )
                            entry = accumulated_tool_calls[idx]
                            if "id" in tc:
                                entry["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if "name" in fn:
                                entry["function"]["name"] = fn["name"]
                            if "arguments" in fn:
                                entry["function"]["arguments"] += fn["arguments"]
                    if accumulated_tool_calls:
                        yield ToolCallRequestEvent(tool_calls=accumulated_tool_calls)
        except httpx.HTTPError as e:
            log.warning("ollama connection error: %s", e)
            yield ErrorEvent(message=f"ollama connection error: {e}")

        yield FinalDoneEvent()
