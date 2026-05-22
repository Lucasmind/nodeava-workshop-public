# nodeava-orch Agentic Loop Implementation Plan (Plan #4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the tool registry from Plan #3 into the chat-completions flow. Add an **agentic loop**: when the model emits `tool_calls`, the orchestrator executes them via the registered tools, appends the results to the conversation, and re-prompts — until the model returns content without further tool calls (or `MAX_TOOL_ROUNDS` is reached). The loop emits typed events (`ToolCallStartEvent`, `ToolCallEndEvent`, `StageTimingEvent`) on named SSE channels so the upcoming Tier A visualizer panels (Plan #8) can render real-time tool traces.

**Architecture:** One new module — `orchestrator/agentic.py` — wraps `Provider.chat()` calls in a multi-round loop. The Provider ABC gains a `tools` parameter; both `LocalLlamaProvider` and `LiteLLMProvider` learn to forward tools to upstream and surface `tool_calls` in the response as a new internal event type `ToolCallRequestEvent`. The chat route, when body toggles `web_search: true` or `wiki: true` are set, replaces its direct `provider.chat()` call with the agentic loop. The Plan #3 test endpoint `POST /v1/tools/{name}` is deleted (tools are now exercised through `/v1/chat/completions`).

**Tech Stack:**
- Everything from Plans #1-#3 (FastAPI, LiteLLM, trafilatura, SearXNG bundle, tool registry)
- No new dependencies
- One new top-level module + four new event types

**Working directory:** `/media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec`. All paths repo-relative.

**Branch:** `worktree-workshop-mvp-spec` tracking `workshop/main` (private repo).

---

## Event flow summary (the new shape)

```
                              ┌──────────────────────────────┐
POST /v1/chat/completions ───►│ chat_completions (routes)    │
{messages, web_search: true,  │  - pick_provider             │
 wiki: true, stream: true}    │  - resolve enabled tools     │
                              │  - branch on toggles         │
                              └────────────┬─────────────────┘
                                           │ if no toggles → direct provider.chat() (unchanged)
                                           │ if any toggle → ↓
                              ┌────────────▼─────────────────┐
                              │ agentic_loop()                │
                              │  per round:                   │
                              │   1. provider.chat(stream=F,  │
                              │      tools=resolved)          │
                              │   2. catches ToolCallRequest  │
                              │   3. executes tools           │
                              │   4. yields ToolCallStart/End │
                              │   5. appends results to msgs  │
                              │  on no-more-tool-calls:       │
                              │   yields buffered TokenEvents │
                              │   + FinalDoneEvent            │
                              └────────────┬─────────────────┘
                                           │ Event stream:
                                           │ TokenEvent, ThinkingTokenEvent,
                                           │ ToolCallStartEvent, ToolCallEndEvent,
                                           │ StageTimingEvent, ErrorEvent,
                                           │ FinalDoneEvent
                                           ▼
                              SSE encoder (named channels)
```

---

## Task 1: Add `ToolCallRequestEvent`, `ToolCallStartEvent`, `ToolCallEndEvent`, `StageTimingEvent`

**Files:**
- Modify: `services/orchestrator/orchestrator/events.py`
- Modify: `services/orchestrator/tests/test_events.py`

`ToolCallRequestEvent` is **internal** — emitted by providers when the model requests tool calls; consumed by the agentic loop; never reaches the SSE wire. The other three are emitted by the agentic loop and surface to clients on named SSE channels (`event: tool_call_start`, etc.).

- [ ] **Step 1: Append to `services/orchestrator/tests/test_events.py`**

```python
from orchestrator.events import (
    ToolCallEndEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
    StageTimingEvent,
)


def test_tool_call_request_event():
    """Internal event — provider emits this when the model wants tools."""
    e = ToolCallRequestEvent(
        tool_calls=[
            {"id": "call_1", "type": "function",
             "function": {"name": "browser.search", "arguments": '{"query":"x"}'}}
        ]
    )
    d = e.model_dump()
    assert d["type"] == "tool_call_request"
    assert d["tool_calls"][0]["id"] == "call_1"


def test_tool_call_start_event():
    e = ToolCallStartEvent(
        id="call_1",
        name="browser.search",
        arguments={"query": "kernel"},
    )
    d = e.model_dump()
    assert d == {
        "type": "tool_call_start",
        "id": "call_1",
        "name": "browser.search",
        "arguments": {"query": "kernel"},
    }


def test_tool_call_end_event_success():
    e = ToolCallEndEvent(
        id="call_1",
        result_preview="3 results",
        duration_ms=124.5,
        error=None,
    )
    d = e.model_dump()
    assert d == {
        "type": "tool_call_end",
        "id": "call_1",
        "result_preview": "3 results",
        "duration_ms": 124.5,
        "error": None,
    }


def test_tool_call_end_event_with_error():
    e = ToolCallEndEvent(
        id="call_1",
        result_preview="",
        duration_ms=5.0,
        error="HTTP 403 fetching example.com",
    )
    assert e.error == "HTTP 403 fetching example.com"


def test_stage_timing_event():
    e = StageTimingEvent(
        stage="round_end",
        duration_ms=2400.0,
        round_num=1,
    )
    d = e.model_dump()
    assert d["type"] == "stage_timing"
    assert d["stage"] == "round_end"
    assert d["round_num"] == 1


def test_all_new_events_are_in_union():
    events: list[Event] = [
        ToolCallRequestEvent(tool_calls=[]),
        ToolCallStartEvent(id="x", name="t", arguments={}),
        ToolCallEndEvent(id="x", result_preview="", duration_ms=1.0),
        StageTimingEvent(stage="round_start", duration_ms=0.0, round_num=1),
    ]
    types = [e.type for e in events]
    assert types == [
        "tool_call_request", "tool_call_start", "tool_call_end", "stage_timing"
    ]
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_events.py -v
```

Expected: ImportError on the four new event names.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/events.py` entirely with:**

```python
"""Typed event models emitted by Providers / the agentic loop / consumed
by the SSE encoder.

  Plan #1: TokenEvent, FinalDoneEvent, ErrorEvent
  Plan #2: ThinkingTokenEvent
  Plan #4: ToolCallRequestEvent (internal — provider→agentic_loop),
           ToolCallStartEvent, ToolCallEndEvent, StageTimingEvent
           (emitted by agentic_loop → SSE)
"""
from typing import Any, Literal, Union

from pydantic import BaseModel


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class ThinkingTokenEvent(BaseModel):
    """Reasoning content emitted by providers that expose it (e.g. Anthropic
    extended thinking). The frontend's brain-pane subscribes to these on
    a named SSE channel — they are NOT mixed into the user-visible content
    stream.
    """
    type: Literal["thinking_token"] = "thinking_token"
    delta: str


class ToolCallRequestEvent(BaseModel):
    """Internal — emitted by a Provider when the upstream model requested
    one or more tool calls in its response. The agentic loop consumes this,
    executes the tools, and feeds results back in. Never serialized to SSE.

    `tool_calls` is the model's `choices[0].message.tool_calls` payload
    (OpenAI tool-call shape): list of {id, type, function: {name, arguments}}.
    """
    type: Literal["tool_call_request"] = "tool_call_request"
    tool_calls: list[dict[str, Any]]


class ToolCallStartEvent(BaseModel):
    """Emitted by the agentic loop just before executing a tool. Surfaces to
    SSE on `event: tool_call_start` for the Tier A visualizer."""
    type: Literal["tool_call_start"] = "tool_call_start"
    id: str
    name: str
    arguments: dict[str, Any]


class ToolCallEndEvent(BaseModel):
    """Emitted by the agentic loop after a tool finishes. `error` is set
    when the tool raised `ToolError`. Surfaces to SSE on `event: tool_call_end`."""
    type: Literal["tool_call_end"] = "tool_call_end"
    id: str
    result_preview: str  # truncated for UI display
    duration_ms: float
    error: str | None = None


class StageTimingEvent(BaseModel):
    """Per-round / per-stage timing for the agentic loop. Surfaces to SSE on
    `event: stage_timing` for the Tier A pipeline-visualizer latency badges."""
    type: Literal["stage_timing"] = "stage_timing"
    stage: Literal["round_start", "round_end", "first_token", "final"]
    duration_ms: float
    round_num: int | None = None


class FinalDoneEvent(BaseModel):
    type: Literal["final_done"] = "final_done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


Event = Union[
    TokenEvent,
    ThinkingTokenEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
    ToolCallEndEvent,
    StageTimingEvent,
    FinalDoneEvent,
    ErrorEvent,
]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_events.py -v
```

Expected: all 11 tests pass (6 prior + 5 new — your union test plus the 4 individual event tests). Actually 12: count above is `test_token_event_serialization`, `test_thinking_token_event_serialization`, `test_thinking_token_event_in_union`, `test_final_done_event_serialization`, `test_error_event_serialization`, `test_event_is_abstract_base_via_discriminator` + `test_tool_call_request_event`, `test_tool_call_start_event`, `test_tool_call_end_event_success`, `test_tool_call_end_event_with_error`, `test_stage_timing_event`, `test_all_new_events_are_in_union` = 12.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add tool-call + stage-timing event types"
```

---

## Task 2: Provider ABC accepts `tools` parameter

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/base.py`
- Modify: `services/orchestrator/tests/test_providers_base.py`

The change is backward-compatible: `tools: list[dict] | None = None`. Existing call sites (Plans #1-#3 code that doesn't pass tools) keep working.

- [ ] **Step 1: Replace the contents of `services/orchestrator/tests/test_providers_base.py` entirely:**

```python
"""Tests for the Provider abstract base class."""
import pytest

from orchestrator.events import TokenEvent, FinalDoneEvent
from orchestrator.providers.base import Provider


class StubProvider(Provider):
    """Yields a fixed event sequence — used to test the ABC contract."""

    async def chat(self, messages, *, stream=False, tools=None):
        # Echo whether tools were passed so we can assert.
        marker = f"tools={'yes' if tools else 'no'}"
        yield TokenEvent(delta=marker)
        yield FinalDoneEvent()


async def test_provider_is_async_iterable():
    """A Provider's `chat` method returns an async iterator of Events."""
    provider = StubProvider()
    events = [e async for e in provider.chat([{"role": "user", "content": "hi"}])]
    assert [e.type for e in events] == ["token", "final_done"]


async def test_provider_subclass_must_implement_chat():
    """Instantiating a Provider that didn't override chat raises TypeError."""

    class BadProvider(Provider):
        pass

    with pytest.raises(TypeError):
        BadProvider()  # type: ignore[abstract]


async def test_provider_chat_accepts_tools_kwarg():
    """The new `tools` parameter is optional and defaults to None.
    Subclasses receive it via the chat signature."""
    provider = StubProvider()
    events_no_tools = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hi"}]
        )
    ]
    events_with_tools = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "x", "parameters": {}}}],
        )
    ]
    assert events_no_tools[0].delta == "tools=no"
    assert events_with_tools[0].delta == "tools=yes"
```

- [ ] **Step 2: Run failing test**

```bash
pytest tests/test_providers_base.py -v
```

Expected: `test_provider_chat_accepts_tools_kwarg` fails with TypeError (signature doesn't accept `tools`).

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/providers/base.py` entirely:**

```python
"""Provider abstract base class.

A Provider is a chat backend (local llama-server, Anthropic, OpenAI, ...).
Implementations are async generators that yield typed Events.

  Plan #1: TokenEvent, FinalDoneEvent, ErrorEvent
  Plan #2: ThinkingTokenEvent (Anthropic extended thinking surface)
  Plan #4: tools=[...] parameter + ToolCallRequestEvent when model emits tool_calls
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import Event


class Provider(ABC):
    """Abstract chat provider — yields a stream of typed Events."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Event]:
        """Run a chat completion. Returns an async iterator of Events.

        Parameters
        ----------
        messages
            OpenAI-format message list.
        stream
            If True, emit TokenEvents as tokens arrive. If False, the provider
            may still emit a single TokenEvent containing the full response
            followed by FinalDoneEvent — callers should buffer either way.
        tools
            OpenAI tool-function definitions to inject into the request. When
            non-empty and the model emits a `tool_calls` array in its response,
            the provider yields a `ToolCallRequestEvent` before any
            FinalDoneEvent. The agentic loop catches this, executes the tools,
            and re-invokes chat() with the tool results appended to messages.
        """
        ...
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_base.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): Provider ABC accepts tools parameter"
```

---

## Task 3: `LocalLlamaProvider` — forward tools + emit `ToolCallRequestEvent`

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/local.py`
- Modify: `services/orchestrator/tests/test_providers_local.py`

Only the **non-streaming** path needs tool-call handling. The agentic loop calls `provider.chat(stream=False, tools=[...])` and reads `ToolCallRequestEvent` from the result. Streaming + tools simultaneously is out of scope for Plan #4 — keep `_chat_streaming` unchanged.

llama-server (with `--jinja`) accepts OpenAI tool definitions in the request body's `tools` field and returns `tool_calls` in the response's `choices[0].message.tool_calls` array when the model decides to call them.

- [ ] **Step 1: Append to `services/orchestrator/tests/test_providers_local.py`**

```python
from orchestrator.events import ToolCallRequestEvent


@respx.mock
async def test_non_streaming_with_tools_emits_tool_call_request(llama_url):
    """When the model responds with tool_calls, emit ToolCallRequestEvent
    (and skip the TokenEvent — the model didn't produce visible content)."""
    respx.post(f"{llama_url}/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_abc",
                                    "type": "function",
                                    "function": {
                                        "name": "browser.search",
                                        "arguments": '{"query":"kernel"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )
    )

    provider = LocalLlamaProvider(base_url=llama_url, timeout=30.0)
    events = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "search kernel"}],
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
    assert tc_events[0].tool_calls[0]["id"] == "call_abc"
    assert tc_events[0].tool_calls[0]["function"]["name"] == "browser.search"
    assert len(done_events) == 1
    assert token_events == []  # no visible content this round


@respx.mock
async def test_non_streaming_with_tools_payload_includes_tools(llama_url):
    """Confirm the `tools` parameter is forwarded to llama-server."""
    captured: dict = {}

    def _record(request):
        captured["payload"] = request.json() if hasattr(request, "json") else None
        return Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    respx.post(f"{llama_url}/v1/chat/completions").mock(side_effect=_record)

    provider = LocalLlamaProvider(base_url=llama_url, timeout=30.0)
    tools_defs = [
        {
            "type": "function",
            "function": {"name": "wiki.list", "parameters": {"type": "object"}},
        }
    ]
    _ = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "hi"}],
            stream=False,
            tools=tools_defs,
        )
    ]
    assert captured["payload"]["tools"] == tools_defs
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_providers_local.py -v
```

Expected: both new tests fail — `tools` is ignored / not propagated; tool_calls in response are silently dropped.

- [ ] **Step 3: Modify `services/orchestrator/orchestrator/providers/local.py`** —

Replace the chat dispatch and the _chat_non_streaming method. The full file should become:

```python
"""LocalLlamaProvider — forwards chat requests to a local llama-server.

The llama-server speaks OpenAI-compatible HTTP. This provider POSTs the
messages and translates either the JSON response (non-streaming) or the
SSE stream (streaming) into typed Events.

Error handling: HTTP errors and connection errors do NOT raise out of
the generator. Instead, the generator yields an ErrorEvent followed by
FinalDoneEvent. This contract simplifies the route layer — it always
gets a clean event stream regardless of backend health.

Plan #4: `tools=` injects OpenAI tool-function definitions; if the model
emits `tool_calls` in the response, yield a `ToolCallRequestEvent` before
FinalDoneEvent. The agentic loop catches these.
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

log = logging.getLogger("orchestrator.providers.local")


class LocalLlamaProvider(Provider):
    def __init__(self, *, base_url: str, timeout: float = 300.0) -> None:
        self._base_url = base_url.rstrip("/")
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
        payload: dict[str, Any] = {"messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                )
                if resp.status_code >= 400:
                    log.warning("backend HTTP %d: %s", resp.status_code, resp.text[:200])
                    yield ErrorEvent(
                        message=f"backend returned HTTP {resp.status_code}"
                    )
                    yield FinalDoneEvent()
                    return
                data = resp.json()
        except httpx.HTTPError as e:
            log.warning("backend connection error: %s", e)
            yield ErrorEvent(message=f"backend connection error: {e}")
            yield FinalDoneEvent()
            return

        choices = data.get("choices") or []
        if not choices:
            yield FinalDoneEvent()
            return

        message = choices[0].get("message") or {}

        # Tool calls take precedence over content — when the model decides to
        # call tools, it typically returns content: null + a tool_calls array.
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
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/v1/chat/completions",
                    json={"messages": messages, "stream": True},
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode(errors="replace")[:200]
                        log.warning("backend HTTP %d: %s", resp.status_code, body)
                        yield ErrorEvent(
                            message=f"backend returned HTTP {resp.status_code}"
                        )
                        yield FinalDoneEvent()
                        return
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line.removeprefix("data: ").strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield TokenEvent(delta=content)
        except httpx.HTTPError as e:
            log.warning("backend connection error: %s", e)
            yield ErrorEvent(message=f"backend connection error: {e}")
            yield FinalDoneEvent()
            return

        yield FinalDoneEvent()
```

- [ ] **Step 4: Run all provider tests**

```bash
pytest tests/test_providers_local.py -v
```

Expected: all tests pass (4 prior + 2 new = 6).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LocalLlamaProvider forwards tools + emits ToolCallRequestEvent"
```

---

## Task 4: `LiteLLMProvider` — forward tools + emit `ToolCallRequestEvent`

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/litellm_provider.py`
- Modify: `services/orchestrator/tests/test_providers_litellm.py`

Same shape as LocalLlamaProvider: only non-streaming path needs tool handling. LiteLLM passes `tools` straight to upstream and returns tool_calls in `resp.choices[0].message.tool_calls` (shaped as a list of objects with `.id`, `.type`, `.function.name`, `.function.arguments`).

- [ ] **Step 1: Append to `services/orchestrator/tests/test_providers_litellm.py`**

```python
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
```

- [ ] **Step 2: Run failing test**

```bash
pytest tests/test_providers_litellm.py::test_non_streaming_with_tools_emits_tool_call_request -v
```

Expected: FAIL — current provider doesn't forward tools and doesn't surface tool_calls.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/providers/litellm_provider.py` entirely:**

```python
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
```

- [ ] **Step 4: Run all LiteLLM tests**

```bash
pytest tests/test_providers_litellm.py -v
```

Expected: 5 PASS (4 prior + 1 new).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LiteLLMProvider forwards tools + emits ToolCallRequestEvent"
```

---

## Task 5: `browser.open` SSRF guard + fetch-size cap

**Files:**
- Modify: `services/orchestrator/orchestrator/tools/browser.py`
- Modify: `services/orchestrator/tests/test_tools_browser.py`

Plan #3's final review flagged: with the agentic loop about to drive `browser.open` autonomously, a malicious search snippet could feed the agent a URL like `http://169.254.169.254/latest/meta-data/` (cloud metadata service), `http://127.0.0.1:8082/v1/...` (the orchestrator's own admin surface), or any internal Docker DNS name. We add two guards:

1. **SSRF guard**: reject non-`http(s)` schemes, reject hostnames that resolve to private / loopback / link-local IPs.
2. **Fetch size cap**: refuse to fully load responses larger than 5MB. Use `client.stream()` to read incrementally and abort if `content-length` is too large or actual bytes exceed the cap.

- [ ] **Step 1: Append to `services/orchestrator/tests/test_tools_browser.py`**

```python
@respx.mock
async def test_open_rejects_non_http_scheme():
    """file://, ftp://, gopher:// all rejected."""
    from orchestrator.tools.base import ToolError
    import pytest

    tool = BrowserOpen(cache=PageCache())
    for url in ("file:///etc/passwd", "ftp://example.com/", "gopher://x"):
        with pytest.raises(ToolError) as exc:
            await tool.execute({"id": url})
        assert "scheme" in str(exc.value).lower() or "http" in str(exc.value).lower()


async def test_open_rejects_private_ip_hostnames(monkeypatch):
    """Hostnames resolving to private / loopback / link-local addresses are rejected
    BEFORE any HTTP call is attempted."""
    from orchestrator.tools.base import ToolError
    import pytest

    # Patch socket.gethostbyname so we don't need real DNS. The guard uses
    # it to resolve the hostname before deciding whether to fetch.
    import socket
    original = socket.gethostbyname

    def fake_resolve(host: str) -> str:
        return {
            "metadata.example": "169.254.169.254",     # link-local
            "internal.example": "10.0.0.5",             # private
            "loopback.example": "127.0.0.1",            # loopback
        }.get(host, original(host))

    monkeypatch.setattr(socket, "gethostbyname", fake_resolve)

    tool = BrowserOpen(cache=PageCache())
    for host in ("metadata.example", "internal.example", "loopback.example"):
        with pytest.raises(ToolError) as exc:
            await tool.execute({"id": f"http://{host}/anything"})
        msg = str(exc.value).lower()
        assert (
            "private" in msg or "internal" in msg or "loopback" in msg
            or "metadata" in msg or "refus" in msg
        )


async def test_open_rejects_raw_private_ip():
    """Literal IPs in private ranges also rejected — no DNS needed."""
    from orchestrator.tools.base import ToolError
    import pytest

    tool = BrowserOpen(cache=PageCache())
    for url in (
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
    ):
        with pytest.raises(ToolError):
            await tool.execute({"id": url})


@respx.mock
async def test_open_size_cap_rejects_oversized_content_length():
    """If the server advertises content-length > 5MB, refuse before reading the body."""
    from orchestrator.tools.base import ToolError
    import pytest

    too_big = 6 * 1024 * 1024
    respx.get("https://example.com/huge").mock(
        return_value=Response(
            200,
            content=b"<html></html>",
            headers={"content-type": "text/html", "content-length": str(too_big)},
        )
    )

    tool = BrowserOpen(cache=PageCache())
    with pytest.raises(ToolError) as exc:
        await tool.execute({"id": "https://example.com/huge"})
    assert "size" in str(exc.value).lower() or "too large" in str(exc.value).lower()
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: all four new tests fail (no guard yet).

- [ ] **Step 3: Edit `services/orchestrator/orchestrator/tools/browser.py`** —

Insert a new module-level constant + helper function near the top (after `_USER_AGENT`), then modify `BrowserOpen._fetch_and_extract` to call the guard and use a streamed download with a size cap. The full file should become:

```python
"""Browser tools — search/open/find against the live web via SearXNG + httpx.

Three tools share a PageCache so `browser.find` can target the last page
opened by `browser.open` without a re-fetch.

Plan #4 added two security guards to `BrowserOpen`:
  - SSRF: reject non-http(s) schemes, reject hostnames that resolve to
    private / loopback / link-local / reserved IPs (cloud-metadata,
    internal Docker services, the orchestrator itself).
  - Fetch size cap: refuse pages larger than MAX_FETCH_BYTES.
"""
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from orchestrator.tools.base import Tool, ToolError
from orchestrator.tools.cache import PageCache

log = logging.getLogger("orchestrator.tools.browser")


_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

MAX_FETCH_BYTES = 5 * 1024 * 1024  # 5 MB cap for browser.open


def _validate_public_url(url: str) -> None:
    """Raise ToolError if `url` is not safe to fetch from the public internet.

    Rejects:
      - non-http(s) schemes
      - hostnames missing or empty
      - hostnames that resolve to: loopback (127.0.0.0/8), private
        (10/8, 172.16/12, 192.168/16), link-local (169.254/16), reserved
        / unspecified / multicast

    The check runs BEFORE any HTTP request, so SSRF attempts never reach
    the network layer.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ToolError(f"refusing to open {url}: unsupported scheme {scheme!r}")
    host = parsed.hostname
    if not host:
        raise ToolError(f"refusing to open {url}: no hostname")

    # Resolve to IP (literal IPs short-circuit). gethostbyname is sync but the
    # resolution is local + cached; not worth dragging in asyncio DNS for a guard.
    try:
        ip_str = socket.gethostbyname(host)
    except OSError as e:
        raise ToolError(f"refusing to open {url}: hostname resolution failed: {e}") from e

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as e:
        raise ToolError(f"refusing to open {url}: invalid resolved address {ip_str}") from e

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        raise ToolError(
            f"refusing to open {url}: host {host} resolves to {ip_str} "
            "(loopback / private / link-local / reserved)"
        )


class BrowserSearch(Tool):
    """Search the web via the bundled SearXNG meta-search engine."""

    name = "browser.search"
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "topn": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, searxng_url: str, cache: PageCache, timeout: float = 30.0) -> None:
        self._searxng_url = searxng_url.rstrip("/")
        self._cache = cache
        self._timeout = timeout

    async def execute(self, args: dict[str, Any]) -> str:
        query = args.get("query") or ""
        if not query:
            raise ToolError("browser.search requires a non-empty 'query'")
        try:
            topn = int(args.get("topn", 5))
        except (TypeError, ValueError):
            topn = 5
        topn = max(1, min(topn, 20))

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._searxng_url}/search",
                    params={"q": query, "format": "json", "pageno": 1},
                )
        except httpx.HTTPError as e:
            raise ToolError(f"SearXNG unreachable: {e}") from e

        if resp.status_code >= 400:
            raise ToolError(f"SearXNG returned HTTP {resp.status_code}")

        data = resp.json()
        results = data.get("results") or []
        if not results:
            return f"No results for: {query}"

        chunks: list[str] = []
        for i, r in enumerate(results[:topn], start=1):
            title = r.get("title") or "(no title)"
            url = r.get("url") or ""
            snippet = r.get("content") or "(no snippet)"
            chunks.append(f"[{i}] {title}\n    URL: {url}\n    {snippet}")
        return "\n\n".join(chunks)


class BrowserOpen(Tool):
    """Fetch a URL, extract readable text, cache the result, return a slice."""

    name = "browser.open"
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "URL to open"},
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to return",
                "default": 120,
            },
            "cursor": {
                "type": "integer",
                "description": "Line offset to start from (0 = top of page)",
                "default": 0,
            },
        },
        "required": ["id"],
    }

    def __init__(self, *, cache: PageCache, timeout: float = 30.0) -> None:
        self._cache = cache
        self._timeout = timeout

    async def execute(self, args: dict[str, Any]) -> str:
        url = args.get("id") or args.get("url") or ""
        if not url:
            raise ToolError("browser.open requires 'id' (the URL)")

        try:
            num_lines = int(args.get("num_lines", 120))
        except (TypeError, ValueError):
            num_lines = 120
        num_lines = max(1, min(num_lines, 500))

        try:
            cursor = int(args.get("cursor", 0))
        except (TypeError, ValueError):
            cursor = 0
        cursor = max(0, cursor)

        cached = self._cache.get(url)
        if cached is None:
            # Validate BEFORE we even ask the cache — actually we validate
            # before fetching; the cache only ever holds previously-validated URLs.
            _validate_public_url(url)
            cached = await self._fetch_and_extract(url)
            self._cache.put(url, cached)

        lines: list[str] = cached["lines"]
        total = len(lines)
        end = min(cursor + num_lines, total)
        selected = lines[cursor:end]
        header = (
            f"Title: {cached['title']}\n"
            f"URL: {url}\n"
            f"Lines {cursor + 1}-{end} of {total}\n"
            f"---\n"
        )
        return header + "\n".join(selected)

    async def _fetch_and_extract(self, url: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self._timeout
            ) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    },
                ) as resp:
                    if resp.status_code >= 400:
                        log.warning("HTTP %d fetching %s", resp.status_code, url)
                        raise ToolError(
                            f"HTTP {resp.status_code} fetching {url}. "
                            "The site may block automated access."
                        )
                    # Pre-check via Content-Length when present
                    cl = resp.headers.get("content-length")
                    if cl is not None:
                        try:
                            if int(cl) > MAX_FETCH_BYTES:
                                raise ToolError(
                                    f"refusing to open {url}: declared size "
                                    f"{cl} bytes > MAX_FETCH_BYTES ({MAX_FETCH_BYTES})"
                                )
                        except ValueError:
                            pass

                    # Stream-read with a running byte cap
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_FETCH_BYTES:
                            raise ToolError(
                                f"refusing to open {url}: body exceeded "
                                f"MAX_FETCH_BYTES ({MAX_FETCH_BYTES} bytes)"
                            )
                        chunks.append(chunk)
                    html = b"".join(chunks).decode("utf-8", errors="replace")
        except httpx.HTTPError as e:
            raise ToolError(f"failed to fetch {url}: {e}") from e

        # Prefer trafilatura's reader-mode extraction; fall back to BS4 if it
        # returns nothing (rare, but trafilatura sometimes whiffs on tiny pages).
        text = trafilatura.extract(html) or ""
        if not text:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)

        title = ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception:
            title = ""

        lines = [line for line in text.split("\n") if line.strip()]
        return {"title": title, "url": url, "text": text, "lines": lines}


class BrowserFind(Tool):
    """Search a previously-opened page for a regex or substring pattern."""

    name = "browser.find"
    schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex or substring to find. Invalid regex falls back to substring.",
            },
            "url": {
                "type": "string",
                "description": (
                    "Optional — which cached page to search. "
                    "Default: the most recently opened page."
                ),
            },
            "max_matches": {
                "type": "integer",
                "description": "Cap matches returned",
                "default": 10,
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, *, cache: PageCache) -> None:
        self._cache = cache

    async def execute(self, args: dict[str, Any]) -> str:
        import re

        pattern = args.get("pattern")
        if not pattern:
            raise ToolError("browser.find requires a 'pattern'")

        url = args.get("url") or self._cache.most_recent_url()
        if url is None:
            raise ToolError(
                "browser.find: no page is currently cached. "
                "Call browser.open first or pass an explicit url."
            )

        page = self._cache.get(url)
        if page is None:
            raise ToolError(f"browser.find: no cached page for {url}")

        try:
            max_matches = int(args.get("max_matches", 10))
        except (TypeError, ValueError):
            max_matches = 10
        max_matches = max(1, min(max_matches, 50))

        try:
            compiled = re.compile(pattern, re.IGNORECASE)

            def predicate(line: str) -> bool:
                return bool(compiled.search(line))
        except re.error:
            needle = pattern.lower()

            def predicate(line: str) -> bool:
                return needle in line.lower()

        matches: list[str] = []
        for i, line in enumerate(page["lines"], start=1):
            if predicate(line):
                matches.append(f"Line {i}: {line}")
                if len(matches) >= max_matches:
                    break

        if not matches:
            return f"No matches for {pattern!r} in {url}"

        return f"Found {len(matches)} matches in {url}:\n" + "\n".join(matches)
```

- [ ] **Step 4: Run all browser tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: all tests pass (13 prior + 4 new = 17).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): browser.open SSRF guard + fetch size cap"
```

---

## Task 6: `agentic_loop` module — the meat of Plan #4

**Files:**
- Create: `services/orchestrator/orchestrator/agentic.py`
- Create: `services/orchestrator/tests/test_agentic.py`

This is the core of Plan #4. A single async-generator that wraps `Provider.chat()` in a multi-round tool-execution loop.

- [ ] **Step 1: Create `services/orchestrator/tests/test_agentic.py`**

```python
"""Tests for the agentic loop — the multi-round tool-execution wrapper."""
from typing import Any

import pytest

from orchestrator.agentic import agentic_loop
from orchestrator.events import (
    ErrorEvent,
    FinalDoneEvent,
    StageTimingEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
)
from orchestrator.providers.base import Provider
from orchestrator.tools import _clear_registry_for_tests, register
from orchestrator.tools.base import Tool, ToolError


@pytest.fixture(autouse=True)
def _reset_registry():
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


class _ScriptedProvider(Provider):
    """A provider that yields a pre-canned event sequence per chat() invocation.

    Each call dequeues the next sequence from `self._sequences`. Used to
    simulate multi-round agentic conversations without a real LLM."""

    def __init__(self, sequences: list[list]) -> None:
        self._sequences = list(sequences)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages, *, stream=False, tools=None):
        self.calls.append(
            {"messages": list(messages), "stream": stream, "tools": tools}
        )
        if not self._sequences:
            raise AssertionError(
                "_ScriptedProvider exhausted: agentic_loop called chat() more times than expected"
            )
        sequence = self._sequences.pop(0)
        for event in sequence:
            yield event


class _Echo(Tool):
    name = "test.echo"
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, args):
        return f"echo: {args.get('text', '')}"


class _Boom(Tool):
    name = "test.boom"
    schema = {"type": "object"}

    async def execute(self, args):
        raise ToolError("kaboom")


async def test_no_tool_calls_yields_buffered_tokens_then_done():
    """Single-round case: model returns content, no tool calls.
    The loop yields the buffered TokenEvents and a FinalDoneEvent."""
    register(_Echo())
    provider = _ScriptedProvider(
        sequences=[
            [TokenEvent(delta="Hello"), TokenEvent(delta=" world"), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "hi"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]
    token_deltas = [e.delta for e in events if isinstance(e, TokenEvent)]
    assert token_deltas == ["Hello", " world"]
    assert isinstance(events[-1], FinalDoneEvent)
    # provider was called exactly once
    assert len(provider.calls) == 1


async def test_one_tool_call_then_final_answer():
    """Round 1: model emits tool_call. Round 2: model returns content using the result."""
    register(_Echo())
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "test.echo", "arguments": '{"text":"foo"}'},
    }
    provider = _ScriptedProvider(
        sequences=[
            # Round 1 — model wants to call echo
            [ToolCallRequestEvent(tool_calls=[tool_call]), FinalDoneEvent()],
            # Round 2 — model returns its synthesis
            [TokenEvent(delta="The echo said: echo: foo"), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "echo foo"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]

    starts = [e for e in events if isinstance(e, ToolCallStartEvent)]
    ends = [e for e in events if isinstance(e, ToolCallEndEvent)]
    tokens = [e for e in events if isinstance(e, TokenEvent)]
    dones = [e for e in events if isinstance(e, FinalDoneEvent)]

    assert len(starts) == 1
    assert starts[0].id == "call_1"
    assert starts[0].name == "test.echo"
    assert starts[0].arguments == {"text": "foo"}

    assert len(ends) == 1
    assert ends[0].id == "call_1"
    assert ends[0].error is None
    assert ends[0].duration_ms >= 0

    assert [t.delta for t in tokens] == ["The echo said: echo: foo"]
    assert len(dones) == 1

    # provider called twice: round 1 + round 2
    assert len(provider.calls) == 2
    # round-2 messages include the tool result
    msgs_round2 = provider.calls[1]["messages"]
    tool_msg = next((m for m in msgs_round2 if m.get("role") == "tool"), None)
    assert tool_msg is not None
    assert tool_msg["tool_call_id"] == "call_1"
    assert tool_msg["content"] == "echo: foo"


async def test_tool_error_is_captured_in_tool_call_end():
    """When a tool raises ToolError, the agentic loop emits ToolCallEndEvent
    with `error` set, and the loop continues — the model gets the error
    as the tool result and can recover."""
    register(_Boom())
    tool_call = {
        "id": "call_2",
        "type": "function",
        "function": {"name": "test.boom", "arguments": "{}"},
    }
    provider = _ScriptedProvider(
        sequences=[
            [ToolCallRequestEvent(tool_calls=[tool_call]), FinalDoneEvent()],
            [TokenEvent(delta="Recovered."), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "fail safely"}],
            tools=[_Boom()],
            max_rounds=3,
        )
    ]
    end_events = [e for e in events if isinstance(e, ToolCallEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].error == "kaboom"
    assert "kaboom" in end_events[0].result_preview.lower()


async def test_unknown_tool_is_captured_in_tool_call_end():
    """If the model invents a tool name that isn't registered, the loop emits a
    ToolCallEndEvent with an error — does NOT raise out."""
    tool_call = {
        "id": "call_3",
        "type": "function",
        "function": {"name": "no.such.tool", "arguments": "{}"},
    }
    provider = _ScriptedProvider(
        sequences=[
            [ToolCallRequestEvent(tool_calls=[tool_call]), FinalDoneEvent()],
            [TokenEvent(delta="Sorry, I made up a tool."), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[],
            max_rounds=3,
        )
    ]
    end_events = [e for e in events if isinstance(e, ToolCallEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].error is not None
    assert "no.such.tool" in end_events[0].error


async def test_max_rounds_forces_final_answer():
    """If the model keeps asking for tools past max_rounds, the loop appends
    a 'stop calling tools' message and makes one more call with tools=None."""
    register(_Echo())
    repeated_tool_call = {
        "id": "call_x",
        "type": "function",
        "function": {"name": "test.echo", "arguments": "{}"},
    }
    # 2 rounds of tool calls + a final forced-answer round
    provider = _ScriptedProvider(
        sequences=[
            [ToolCallRequestEvent(tool_calls=[repeated_tool_call]), FinalDoneEvent()],
            [ToolCallRequestEvent(tool_calls=[repeated_tool_call]), FinalDoneEvent()],
            [TokenEvent(delta="Final answer."), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "loop forever"}],
            tools=[_Echo()],
            max_rounds=2,
        )
    ]
    # Three provider calls: rounds 1 + 2 + the forced-final
    assert len(provider.calls) == 3
    # Last call must NOT include tools (forced final)
    assert provider.calls[-1]["tools"] is None
    # Last call's messages include the "stop calling tools" instruction
    last_msgs = provider.calls[-1]["messages"]
    user_msgs = [m["content"] for m in last_msgs if m.get("role") == "user"]
    assert any("stop calling tools" in (m or "").lower() for m in user_msgs)
    # Final answer made it through
    assert any(
        isinstance(e, TokenEvent) and "Final answer" in e.delta for e in events
    )


async def test_thinking_tokens_pass_through_each_round():
    """ThinkingTokenEvents emitted during a round are forwarded immediately
    (not buffered) — the brain pane should reflect reasoning in real time."""
    register(_Echo())
    tool_call = {
        "id": "call_t",
        "type": "function",
        "function": {"name": "test.echo", "arguments": "{}"},
    }
    provider = _ScriptedProvider(
        sequences=[
            [
                ThinkingTokenEvent(delta="planning..."),
                ToolCallRequestEvent(tool_calls=[tool_call]),
                FinalDoneEvent(),
            ],
            [
                ThinkingTokenEvent(delta="synthesizing..."),
                TokenEvent(delta="done"),
                FinalDoneEvent(),
            ],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]
    thinking = [e.delta for e in events if isinstance(e, ThinkingTokenEvent)]
    assert thinking == ["planning...", "synthesizing..."]


async def test_error_event_short_circuits_loop():
    """If a provider yields an ErrorEvent, the loop forwards it and ends —
    no more provider calls, no more tool execution."""
    provider = _ScriptedProvider(
        sequences=[
            [ErrorEvent(message="backend down"), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[],
            max_rounds=3,
        )
    ]
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert errors[0].message == "backend down"
    assert isinstance(events[-1], FinalDoneEvent)
    assert len(provider.calls) == 1


async def test_stage_timing_events_emitted_per_round():
    """Each round emits round_start + round_end timing events for the visualizer."""
    register(_Echo())
    provider = _ScriptedProvider(
        sequences=[[TokenEvent(delta="hi"), FinalDoneEvent()]]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]
    timings = [e for e in events if isinstance(e, StageTimingEvent)]
    stages = sorted({t.stage for t in timings})
    assert "round_start" in stages
    assert "round_end" in stages
    # All timings have a round number on intermediate stages
    round_starts = [t for t in timings if t.stage == "round_start"]
    assert all(t.round_num == 1 for t in round_starts)
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_agentic.py -v
```

Expected: ImportError on `orchestrator.agentic`.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/agentic.py`**

```python
"""Agentic loop — the multi-round tool-execution wrapper.

The agentic loop is a single async generator that wraps `Provider.chat()`
in a multi-round conversation:

  Round 1: provider.chat(stream=False, tools=enabled)
    - If response includes tool_calls → execute them, append results, loop
    - Else → buffer TokenEvents, yield them, FinalDoneEvent, exit

  Round 2..N: same shape, with growing message history

  After MAX_TOOL_ROUNDS: append "stop calling tools" + one more call WITHOUT tools

Events emitted (to the SSE wire):
  - ThinkingTokenEvent     (pass-through, per round)
  - ToolCallStartEvent     (before each tool execution)
  - ToolCallEndEvent       (after each tool execution; `error` set if ToolError)
  - StageTimingEvent       (round_start, round_end per round)
  - TokenEvent             (buffered then replayed on the final-answer round)
  - FinalDoneEvent         (end of stream)
  - ErrorEvent             (provider error — short-circuits the loop)

Internal-only event (provider→agentic_loop):
  - ToolCallRequestEvent   (consumed; never forwarded)
"""
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import (
    ErrorEvent,
    Event,
    FinalDoneEvent,
    StageTimingEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
)
from orchestrator.providers.base import Provider
from orchestrator.tools import ToolError, get as get_tool
from orchestrator.tools.base import Tool

log = logging.getLogger("orchestrator.agentic")

DEFAULT_MAX_ROUNDS = 8
RESULT_PREVIEW_CHARS = 500
TOOL_RESULT_TRUNCATE = 4000  # what we feed back to the model


async def agentic_loop(
    *,
    provider: Provider,
    messages: list[dict[str, Any]],
    tools: list[Tool],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> AsyncIterator[Event]:
    """Run an agentic chat loop.

    Yields typed Events to the caller (route layer). Mutates `messages` —
    callers should pass a copy if they need to preserve the original.
    """
    tools_def: list[dict[str, Any]] | None = (
        [t.to_openai_function() for t in tools] if tools else None
    )

    for round_num in range(1, max_rounds + 1):
        round_start = time.monotonic()
        yield StageTimingEvent(
            stage="round_start", duration_ms=0.0, round_num=round_num
        )

        tool_calls: list[dict[str, Any]] | None = None
        buffered_tokens: list[TokenEvent] = []
        error: ErrorEvent | None = None

        async for event in provider.chat(messages, stream=False, tools=tools_def):
            if isinstance(event, ToolCallRequestEvent):
                tool_calls = event.tool_calls
            elif isinstance(event, TokenEvent):
                buffered_tokens.append(event)
            elif isinstance(event, ThinkingTokenEvent):
                yield event  # pass-through
            elif isinstance(event, ErrorEvent):
                error = event
            elif isinstance(event, FinalDoneEvent):
                pass  # round terminator from the provider; loop handles outer FinalDoneEvent
            else:
                # Unknown event type from provider — log and drop.
                log.debug("agentic_loop: ignoring unexpected event %r", event)

        round_dur_ms = (time.monotonic() - round_start) * 1000.0
        yield StageTimingEvent(
            stage="round_end", duration_ms=round_dur_ms, round_num=round_num
        )

        if error is not None:
            yield error
            yield FinalDoneEvent()
            return

        if tool_calls is None:
            # Final answer in hand — replay buffered tokens
            for tok in buffered_tokens:
                yield tok
            yield FinalDoneEvent()
            return

        # Execute each tool call
        # Append the assistant's tool_calls message FIRST so the model history
        # is well-formed for the next round.
        messages.append(
            {"role": "assistant", "content": None, "tool_calls": tool_calls}
        )

        for tc in tool_calls:
            tc_id = tc.get("id") or ""
            fn = tc.get("function") or {}
            tc_name = fn.get("name") or ""
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}

            yield ToolCallStartEvent(id=tc_id, name=tc_name, arguments=args)

            t0 = time.monotonic()
            try:
                tool = get_tool(tc_name)
                result = await tool.execute(args)
                err_msg: str | None = None
            except ToolError as e:
                result = f"Error: {e}"
                err_msg = str(e)
            except Exception as e:
                log.warning("unexpected exception from tool %s: %s", tc_name, e)
                result = f"Error: {e}"
                err_msg = str(e)
            dur_ms = (time.monotonic() - t0) * 1000.0

            yield ToolCallEndEvent(
                id=tc_id,
                result_preview=result[:RESULT_PREVIEW_CHARS],
                duration_ms=dur_ms,
                error=err_msg,
            )

            # Truncate the result fed back to the model — keeps context manageable.
            truncated = result
            if len(result) > TOOL_RESULT_TRUNCATE:
                truncated = (
                    result[:TOOL_RESULT_TRUNCATE]
                    + f"\n\n[...truncated, original {len(result)} chars]"
                )
            messages.append(
                {"role": "tool", "tool_call_id": tc_id, "content": truncated}
            )

        # Continue to next round

    # Exhausted max_rounds — force a final answer with no tools
    log.warning("agentic_loop: hit max_rounds=%d, forcing final answer", max_rounds)
    messages.append(
        {
            "role": "user",
            "content": (
                "You have finished searching. Stop calling tools. Write your "
                "final answer now using the information you've gathered. "
                "Do not invoke any more tools."
            ),
        }
    )
    final_buffer: list[TokenEvent] = []
    async for event in provider.chat(messages, stream=False, tools=None):
        if isinstance(event, TokenEvent):
            final_buffer.append(event)
        elif isinstance(event, ThinkingTokenEvent):
            yield event
        elif isinstance(event, ErrorEvent):
            yield event
            yield FinalDoneEvent()
            return
    for tok in final_buffer:
        yield tok
    yield FinalDoneEvent()
```

- [ ] **Step 4: Run all agentic tests**

```bash
pytest tests/test_agentic.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): agentic_loop — multi-round tool execution"
```

---

## Task 7: Wire agentic loop into the chat route + add toggles

**Files:**
- Modify: `services/orchestrator/orchestrator/routes/chat.py`
- Modify: `services/orchestrator/tests/test_routes.py`

Body toggles:
- `"web_search": true` → resolve all `browser.*` tools and run the agentic loop
- `"wiki": true` → resolve all `wiki.*` tools and run the agentic loop
- Either or both → agentic loop runs with the union
- Neither → keep Plan #1+#2 behavior: direct `provider.chat()`

The streaming path emits the new event types on named SSE channels (`event: tool_call_start`, etc.). The non-streaming path drops them (no place to put them in a one-shot JSON response).

- [ ] **Step 1: Append to `services/orchestrator/tests/test_routes.py`**

```python
async def test_chat_with_web_search_toggle_runs_agentic_loop(app_client, monkeypatch):
    """body.web_search=true → tools injected; tool calls executed; tool_call_start
    and tool_call_end events appear on the SSE stream."""
    from types import SimpleNamespace
    import json
    import httpx
    import respx

    # Mock SearXNG so browser.search has something to return
    with respx.mock(assert_all_called=False):
        respx.get("http://searxng:8080/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "Foo", "url": "https://example.com/foo", "content": "bar"}
                    ]
                },
            )
        )

        # The local llm needs to (a) ask for the search tool, (b) return content next.
        # Sequence two responses:
        from itertools import cycle
        call_count = {"n": 0}

        def llm_responder(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "browser.search",
                                                "arguments": '{"query":"foo"}',
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Done."},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )

        respx.post("http://localhost:8081/v1/chat/completions").mock(
            side_effect=llm_responder
        )

        async with app_client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "search foo"}],
                "stream": True,
                "web_search": True,
            },
        ) as resp:
            assert resp.status_code == 200
            body = (await resp.aread()).decode()

    # The stream should contain a named tool_call_start event for browser.search
    assert "event: tool_call_start" in body
    assert "browser.search" in body
    assert "event: tool_call_end" in body
    # The final visible content "Done." should appear on the default `data:` stream
    contents = []
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta and delta["content"]:
            contents.append(delta["content"])
    assert "Done." in "".join(contents)


async def test_chat_without_toggles_skips_agentic_loop(app_client, monkeypatch):
    """No web_search/wiki body field → direct provider.chat() path, no tool events."""
    import respx
    import httpx

    with respx.mock:
        respx.post("http://localhost:8081/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Plain."},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )
        )
        resp = await app_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "Plain."
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_routes.py -v
```

Expected: `test_chat_with_web_search_toggle_runs_agentic_loop` fails — toggle isn't wired yet.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/routes/chat.py` ENTIRELY:**

```python
"""Chat completions route — direct provider passthrough OR agentic loop.

The route layer is thin: parses the OpenAI request body, decides whether
agentic tools are needed (body toggles `web_search` / `wiki`), picks a
Provider via `pick_provider(request, body)`, then either:

  - Calls `provider.chat()` directly (Plan #1+#2 behavior)
  - Wraps it in `agentic_loop()` (Plan #4) — multi-round, tool-executing

Streaming routing rules (both paths):
  - TokenEvent           → OpenAI streaming chunk on default `data:` stream
  - ThinkingTokenEvent   → encode_sse, named `event: thinking_token`
  - ToolCallStartEvent   → encode_sse, named `event: tool_call_start`
  - ToolCallEndEvent     → encode_sse, named `event: tool_call_end`
  - StageTimingEvent     → encode_sse, named `event: stage_timing`
  - ErrorEvent           → encode_sse, named `event: error`
  - FinalDoneEvent       → break loop, emit final OpenAI chunk + [DONE]
"""
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from orchestrator.agentic import agentic_loop
from orchestrator.events import (
    ErrorEvent,
    FinalDoneEvent,
    StageTimingEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from orchestrator.providers import pick_provider
from orchestrator.sse import encode_openai_chunk, encode_openai_done, encode_sse
from orchestrator.tools import list_tools

router = APIRouter()


def _resolve_enabled_tools(*, web_search: bool, wiki: bool) -> list:
    """Return the subset of registered tools matching the request toggles."""
    if not (web_search or wiki):
        return []
    chosen = []
    for t in list_tools():
        if web_search and t.name.startswith("browser."):
            chosen.append(t)
        elif wiki and t.name.startswith("wiki."):
            chosen.append(t)
    return chosen


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    # Pop routing-only fields BEFORE the upstream call. pick_provider needs
    # `body["provider"]` available; orchestrator-only toggles are local.
    web_search = bool(body.pop("web_search", False))
    wiki = bool(body.pop("wiki", False))
    body.pop("provider", None)  # consumed by pick_provider above its body.pop
    messages = body.get("messages") or []
    stream = bool(body.get("stream", False))

    provider = pick_provider(request, body)
    enabled_tools = _resolve_enabled_tools(web_search=web_search, wiki=wiki)

    async def event_source():
        if enabled_tools:
            async for event in agentic_loop(
                provider=provider,
                messages=list(messages),  # copy: agentic_loop mutates
                tools=enabled_tools,
            ):
                yield event
        else:
            async for event in provider.chat(messages, stream=stream):
                yield event

    if not stream:
        return await _non_streaming(event_source())
    return await _streaming(event_source())


async def _non_streaming(events) -> JSONResponse:
    parts: list[str] = []
    error: str | None = None
    async for event in events:
        if isinstance(event, TokenEvent):
            parts.append(event.delta)
        elif isinstance(event, (ThinkingTokenEvent, ToolCallStartEvent, ToolCallEndEvent, StageTimingEvent)):
            # Drop in non-streaming mode — no place to put them in OpenAI JSON.
            continue
        elif isinstance(event, ErrorEvent):
            error = event.message
        elif isinstance(event, FinalDoneEvent):
            break

    content = "".join(parts)
    finish_reason = "error" if error else "stop"
    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "nodeava-orch",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }
    if error:
        response["error"] = error
    return JSONResponse(response)


async def _streaming(events) -> StreamingResponse:
    async def gen():
        yield encode_openai_chunk(delta_content=None, role="assistant")

        async for event in events:
            if isinstance(event, TokenEvent):
                yield encode_openai_chunk(delta_content=event.delta)
            elif isinstance(
                event,
                (
                    ThinkingTokenEvent,
                    ToolCallStartEvent,
                    ToolCallEndEvent,
                    StageTimingEvent,
                    ErrorEvent,
                ),
            ):
                yield encode_sse(event)
            elif isinstance(event, FinalDoneEvent):
                break

        yield encode_openai_chunk(delta_content=None, finish_reason="stop")
        yield encode_openai_done()

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: Run all tests**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): chat route wires agentic loop + web_search/wiki toggles"
```

---

## Task 8: Delete `POST /v1/tools/{name}` route and its tests

**Files:**
- Delete: `services/orchestrator/orchestrator/routes/tools.py`
- Delete: `services/orchestrator/tests/test_routes_tools.py`
- Modify: `services/orchestrator/orchestrator/main.py` (remove tools router include)

Plan #3's test endpoint was always temporary — tools are now exercised through the agentic loop in `/v1/chat/completions`. Delete it now to avoid a stale surface attracting future use.

- [ ] **Step 1: Delete the files**

```bash
rm services/orchestrator/orchestrator/routes/tools.py
rm services/orchestrator/tests/test_routes_tools.py
```

- [ ] **Step 2: Edit `services/orchestrator/orchestrator/main.py`**

Replace the file entirely with:

```python
"""FastAPI app entry point for nodeava-orch."""
import logging

from fastapi import FastAPI

from orchestrator.config import Settings
from orchestrator.providers.local import LocalLlamaProvider
from orchestrator.routes import chat, health, models
from orchestrator import tools as tool_registry
from orchestrator.tools.browser import BrowserFind, BrowserOpen, BrowserSearch
from orchestrator.tools.cache import PageCache
from orchestrator.tools.wiki import WikiList, WikiOpen, WikiSearch

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _register_builtin_tools(settings: Settings) -> None:
    """Register the Plan #3 built-in tools against the module-level registry.

    Browser tools share a single PageCache. Wiki tools point at
    settings.wiki_dir. The agentic loop (Plan #4) consumes from this registry.
    """
    page_cache = PageCache(max_size=20)
    tool_registry.register(
        BrowserSearch(searxng_url=settings.searxng_url, cache=page_cache)
    )
    tool_registry.register(BrowserOpen(cache=page_cache))
    tool_registry.register(BrowserFind(cache=page_cache))
    tool_registry.register(WikiList(wiki_dir=settings.wiki_dir))
    tool_registry.register(WikiSearch(wiki_dir=settings.wiki_dir))
    tool_registry.register(WikiOpen(wiki_dir=settings.wiki_dir))


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Sets `app.state.local_provider` — the always-available local backend.
    Cloud providers are constructed per-request by
    `orchestrator.providers.pick_provider`.

    Built-in tools are registered against the module-level registry. The
    agentic loop in `routes/chat.py` consumes them when body toggles
    `web_search` or `wiki` are set.
    """
    settings = settings or Settings()
    app = FastAPI(title="nodeava-orch", version="0.4.0")
    app.state.settings = settings
    app.state.local_provider = LocalLlamaProvider(
        base_url=settings.llama_url, timeout=settings.request_timeout
    )
    _register_builtin_tools(settings)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    return app


app = create_app()


def run() -> None:
    """Launch uvicorn honoring BIND_HOST / BIND_PORT settings."""
    import uvicorn

    settings: Settings = app.state.settings
    uvicorn.run(
        "orchestrator.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
```

- [ ] **Step 3: Run all tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest -v
```

Expected: all tests pass. The four tests in `test_routes_tools.py` are gone (deleted file).

- [ ] **Step 4: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): delete /v1/tools/{name} test endpoint (agentic loop replaces it)"
```

---

## Task 9: README — document agentic loop, toggles, SearXNG secret_key rotation

**Files:**
- Modify: `services/orchestrator/README.md`

- [ ] **Step 1: Update the README in three places.**

**(a) Replace the existing "## Tools (Plan #3)" section** with the following — the section still exists but the "Calling a tool directly" subsection is replaced because the `/v1/tools/{name}` endpoint is gone:

```markdown
## Tools (Plans #3 + #4)

The orchestrator hosts a pluggable tool registry. Plan #3 introduced two
families of built-in tools; Plan #4 wired them into the chat-completion
flow as an **agentic loop**: when the model emits `tool_calls`, the
orchestrator executes them, appends results to the conversation, and
re-prompts — until the model returns content without further tool calls
(or `MAX_TOOL_ROUNDS=8` is reached).

### Browser tools (backed by bundled SearXNG)

| Tool | Purpose |
|---|---|
| `browser.search` | Query the bundled SearXNG meta-search engine; returns top-N results as numbered text |
| `browser.open`   | Fetch a URL, extract readable text via trafilatura, return paginated lines; caches the page in an in-process LRU. SSRF guard rejects private/loopback/link-local hosts. 5MB fetch cap. |
| `browser.find`   | Regex / substring search across the most-recently-opened page (or an explicit URL) |

### Wiki tools (filesystem-backed, Karpathy-style)

| Tool | Purpose |
|---|---|
| `wiki.list`   | Return `wiki/index.md` verbatim — the agent's first stop for "what do I have?" |
| `wiki.search` | Grep across all `.md` files in `wiki/` for a query |
| `wiki.open`   | Read a single wiki page, paginated. Path-traversal safe. |

### Triggering the agentic loop

Add body toggles to a chat completions request:

```bash
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [{"role": "user", "content": "What is NodeAva?"}],
    "wiki": true,
    "stream": true
  }'
```

| Toggle | Effect |
|---|---|
| `"web_search": true` | Inject `browser.*` tools — model may search, fetch, find |
| `"wiki": true`       | Inject `wiki.*` tools — model can read the on-disk wiki |
| Both                 | Inject the union — model picks per turn |
| Neither              | No tools injected; agentic loop is bypassed (Plan #1+#2 behavior) |

### Streaming SSE event types

When `stream: true`, the SSE response interleaves several named-event types
on a single stream alongside the OpenAI-style `data:` content chunks:

| Event | When | What it carries |
|---|---|---|
| (default `data:`) | Per visible content token | OpenAI streaming chunk |
| `thinking_token` | Per reasoning delta (Anthropic etc.) | `{type, delta}` |
| `tool_call_start` | When the agent starts executing a tool | `{type, id, name, arguments}` |
| `tool_call_end`   | When a tool returns | `{type, id, result_preview, duration_ms, error?}` |
| `stage_timing`    | Per round start/end | `{type, stage, duration_ms, round_num}` |
| `error`           | On any error | `{type, message}` |
| `data: [DONE]`    | End of stream | (no payload) |

The Tier A visualizer panels (Plan #8) subscribe to these named events.

### Adding a custom tool

1. Subclass `orchestrator.tools.base.Tool` with `name`, `schema`, and `execute(args)`.
2. Register it at startup in `orchestrator.main._register_builtin_tools`.
3. Write tests under `tests/test_tools_<name>.py`.

Tools raise `ToolError` for user-fixable failures (bad input, page-not-found, etc.).
Anything else propagates and becomes a `ToolCallEndEvent` with an `error` field.
```

**(b) Add a new "## Deployment notes" subsection** before "## Run locally (dev)":

```markdown
## Deployment notes

### Rotate the SearXNG secret_key for any non-localhost deployment

`configs/searxng/settings.yml` ships with `secret_key: workshop-default-secret-please-rotate`.
SearXNG uses this for image-proxy URL signing + CSRF tokens. For a
localhost-only workshop deployment the impact is low (the SearXNG service
is exposed only internally on the Docker network and has `image_proxy: false`).
Before deploying anywhere else, generate a random key:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

…and replace the value in `configs/searxng/settings.yml`. A future plan
may switch this to an environment variable so docker-compose users can
inject it without editing the YAML.

### `browser.open` SSRF / size limits

Plan #4 added two guards inside `browser.open`:

- Hostnames that resolve to loopback / private / link-local / reserved IPs
  are rejected before any HTTP call (protects against cloud-metadata
  exfiltration, internal Docker service introspection, etc.).
- Responses are read incrementally with a 5 MB cap (`MAX_FETCH_BYTES`).
  Responses advertising a larger `Content-Length` are refused up front.

If you operate the orchestrator inside a network where you legitimately
need to fetch private-IP URLs, the guard lives in
`orchestrator/tools/browser.py::_validate_public_url` and can be loosened
per-deployment.
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/README.md
git commit -m "docs(orch): document agentic loop, toggles, SearXNG rotation, SSRF/size guards"
```

---

## Final verification

- [ ] **Step 1: Full test suite passes**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest -v
```

Expected: all tests pass. Cumulative tally additions from Plan #4:
- 5-6 new in `test_events.py` (4 new event types, +1 union test)
- 1 new in `test_providers_base.py` (tools-kwarg)
- 2 new in `test_providers_local.py` (tool_calls request + payload-includes-tools)
- 1 new in `test_providers_litellm.py` (tool_calls request)
- 4 new in `test_tools_browser.py` (SSRF scheme, SSRF hostname, SSRF raw-IP, size-cap)
- 8 new in `test_agentic.py` (the loop tests)
- 2 new in `test_routes.py` (agentic toggle, no-toggle bypass)
- DELETED: 4 tests from `test_routes_tools.py`

Plan #3 finished at 84. Net add ~23, minus 4 deleted = ~+19, so ~103 tests total.

- [ ] **Step 2: Docker build smoke test**

```bash
cd ../..
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml build orchestrator
```

Expected: builds clean.

- [ ] **Step 3: Optional manual smoke test** (after this plan completes — covered in the next testing checkpoint)

Real backend test: bring up `llm` + `orchestrator` + `searxng`. Send:

```bash
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What does the wiki say about itself?"}],"wiki":true,"stream":true,"max_tokens":300}'
```

Watch for: `event: tool_call_start` / `event: tool_call_end` in the SSE body, with `wiki.list` (or `wiki.search`) as the tool name, followed by visible content. This validates the agentic loop end-to-end with real Qwen3-4B.

---

## What comes next (Plan #5)

Plan #5 refactors the **frontend state machine** to handle the new states (`TOOL_CALLING`, `WIKI_QUERY`) and adds the **filler-speech UX** (avatar says "Let me look that up..." while tool rounds run). Plan #5 also wires the SSE event consumer in `LLMClient.js` to dispatch the named events to handlers — Plan #8 will hook the Tier A visualizer panels into those handlers. After Plan #5 the avatar UI will visibly react to tool calls (state shows TOOL_CALLING, filler audio plays) even before the panels are built.
