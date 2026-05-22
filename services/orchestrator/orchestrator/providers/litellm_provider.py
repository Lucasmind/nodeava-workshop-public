"""LiteLLMProvider — cloud (or any LiteLLM-supported) chat backend.

LiteLLM normalizes ~30 providers' APIs to an OpenAI-compatible shape. We
delegate transport + auth + tool-format translation to it, and only
worry about adapting its response shape into our typed Event stream.

Plan #4: `tools=` injects OpenAI tool-function definitions; if the model
emits `tool_calls` in the response, yield a `ToolCallRequestEvent` before
FinalDoneEvent. The agentic loop catches these.

Error contract: LiteLLM exceptions (APIError, AuthenticationError,
APIConnectionError, etc.) do NOT raise out of the generator. They emit
ErrorEvent + FinalDoneEvent — same contract as LocalLlamaProvider.
"""
import logging
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import (
    ErrorEvent,
    Event,
    FinalDoneEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallRequestEvent,
)
from orchestrator.providers.base import Provider

log = logging.getLogger("orchestrator.providers.litellm")


class LiteLLMProvider(Provider):
    def __init__(
        self,
        *,
        provider_name: str,
        model: str,
        api_key: str,
        timeout: float = 300.0,
    ) -> None:
        self._provider_name = provider_name
        self._model = (
            model if "/" in model else f"{provider_name}/{model}"
        ) if model else provider_name
        self._api_key = api_key
        self._timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Event]:
        if stream:
            async for event in self._chat_streaming(messages):
                yield event
        else:
            async for event in self._chat_non_streaming(messages, tools):
                yield event

    async def _chat_non_streaming(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[Event]:
        import litellm

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "api_key": self._api_key,
            "timeout": self._timeout,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            resp = await litellm.acompletion(**kwargs)
        except litellm.APIError as e:
            log.warning("LiteLLM error: %s", e)
            yield ErrorEvent(message=str(e))
            yield FinalDoneEvent()
            return
        except Exception as e:  # last-resort safety net
            log.warning("Unexpected LiteLLM error: %s", e)
            yield ErrorEvent(message=f"LiteLLM error: {e}")
            yield FinalDoneEvent()
            return

        choices = resp.choices or []
        if not choices:
            yield FinalDoneEvent()
            return

        message = choices[0].message
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        if raw_tool_calls:
            # Normalize SimpleNamespace / Pydantic-shape to plain dicts so the
            # downstream agentic loop (and any JSON serializer) handles them uniformly.
            tool_calls_dicts = [_tool_call_to_dict(tc) for tc in raw_tool_calls]
            yield ToolCallRequestEvent(tool_calls=tool_calls_dicts)
            yield FinalDoneEvent()
            return

        content = message.content or ""
        if content:
            yield TokenEvent(delta=content)
        yield FinalDoneEvent()

    async def _chat_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        import litellm

        try:
            stream_iter = await litellm.acompletion(
                model=self._model,
                messages=messages,
                stream=True,
                api_key=self._api_key,
                timeout=self._timeout,
            )
            async for chunk in stream_iter:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                for thinking_text in _extract_thinking_deltas(delta):
                    yield ThinkingTokenEvent(delta=thinking_text)

                content = getattr(delta, "content", None)
                if content:
                    yield TokenEvent(delta=content)
        except litellm.APIError as e:
            log.warning("LiteLLM error during streaming: %s", e)
            yield ErrorEvent(message=str(e))
            yield FinalDoneEvent()
            return
        except Exception as e:
            log.warning("Unexpected LiteLLM streaming error: %s", e)
            yield ErrorEvent(message=f"LiteLLM error: {e}")
            yield FinalDoneEvent()
            return

        yield FinalDoneEvent()


def _tool_call_to_dict(tc: Any) -> dict[str, Any]:
    """Convert a LiteLLM tool_call (Pydantic / SimpleNamespace / dict)
    into a plain dict in OpenAI tool-call shape."""
    if isinstance(tc, dict):
        return tc
    return {
        "id": getattr(tc, "id", ""),
        "type": getattr(tc, "type", "function"),
        "function": {
            "name": getattr(getattr(tc, "function", None), "name", ""),
            "arguments": getattr(getattr(tc, "function", None), "arguments", ""),
        },
    }


def _extract_thinking_deltas(delta: Any) -> list[str]:
    """Pull reasoning text out of a streaming delta regardless of surface.

    LiteLLM exposes Anthropic extended-thinking via either:
      - `delta.thinking_blocks` — list of {"type": "thinking", "thinking": str}
      - `delta.reasoning_content` — flat string (alternate surface)
    Return non-empty strings in source order.
    """
    out: list[str] = []
    blocks = getattr(delta, "thinking_blocks", None) or []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "thinking":
            text = b.get("thinking") or ""
            if text:
                out.append(text)
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        out.append(reasoning)
    return out
