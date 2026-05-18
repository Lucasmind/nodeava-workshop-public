# nodeava-orch LiteLLM Provider Implementation Plan (Plan #2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cloud-provider support to `nodeava-orch` via LiteLLM, with per-request provider switching. Attendees flip between local Qwen3-4B and cloud models (Anthropic Claude, OpenAI, Groq) using their own API keys — no service restart, no frontend change.

**Architecture:** A new `LiteLLMProvider` joins `LocalLlamaProvider` behind the existing `Provider` ABC. Plan #1's static `build_provider(settings)` is replaced by `pick_provider(request, app)` — a per-request factory that reads body fields (`provider`, `model`) and headers (`X-Provider-Key`) to construct the right provider with the right credentials. A new `ThinkingTokenEvent` is added to the event union so Anthropic's extended-thinking content can be streamed to the upcoming brain-pane visualizer without contaminating the visible-content stream.

**Tech Stack:**
- New dep: `litellm>=1.50,<2.0` (unified async SDK for ~30 LLM providers)
- Everything else from Plan #1 (FastAPI, httpx, Pydantic, respx, pytest)

**Working directory:** `/media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec`. All paths are repo-relative.

**Branch:** `worktree-workshop-mvp-spec` (same as Plan #1; PR #17 grows).

---

## Reasoning visibility table (from spec §3.2 — drives ThinkingTokenEvent emission)

| Provider | Reasoning visible? | This plan |
|---|---|---|
| Local Qwen3 (`<think>` tags) | Yes | Plan #5 will parse think-tags. Plan #2 leaves LocalLlamaProvider unchanged. |
| Anthropic extended thinking | Yes | LiteLLMProvider emits `ThinkingTokenEvent` per thinking-block delta |
| OpenAI o-series | No (hidden) | LiteLLMProvider emits no thinking events (none available) |
| Other (Groq, Together, Mistral) | Mostly no | Same — no thinking events unless the chunk schema exposes them |

---

## File map (recap)

```
services/orchestrator/
├── requirements.txt                                # modify: add litellm
├── orchestrator/
│   ├── config.py                                   # modify: provider + provider_model defaults
│   ├── events.py                                   # modify: + ThinkingTokenEvent
│   ├── providers/
│   │   ├── __init__.py                             # modify: + pick_provider(request, app)
│   │   └── litellm_provider.py                     # NEW
│   ├── main.py                                     # modify: drop build_provider
│   └── routes/
│       └── chat.py                                 # modify: use pick_provider; route ThinkingTokenEvent
└── tests/
    ├── test_events.py                              # modify: + ThinkingTokenEvent test
    ├── test_sse.py                                 # modify: + ThinkingTokenEvent SSE routing
    ├── test_providers_litellm.py                   # NEW
    ├── test_providers_pick.py                      # NEW
    └── test_routes.py                              # modify: provider-override test, thinking SSE test
```

---

## Task 1: Add `litellm` dependency

**Files:**
- Modify: `services/orchestrator/requirements.txt`

Goal: pull in LiteLLM and confirm nothing breaks. No new tests yet.

- [ ] **Step 1: Edit `services/orchestrator/requirements.txt`**

Replace its full contents with:

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
httpx==0.28.*
pydantic==2.*
pydantic-settings==2.*
litellm>=1.50,<2.0
```

- [ ] **Step 2: Install and verify the existing suite still passes**

```bash
cd services/orchestrator && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pytest -q
```

Expected: 25 passed.

If `litellm` install fails on this machine, BLOCK and report — the user can decide if we pin a specific version or use a different transport for cloud providers.

- [ ] **Step 3: Commit**

```bash
cd ../..
git add services/orchestrator/requirements.txt
git commit -m "feat(orch): add litellm dependency"
```

---

## Task 2: Add `ThinkingTokenEvent` to the event union

**Files:**
- Modify: `services/orchestrator/orchestrator/events.py`
- Modify: `services/orchestrator/tests/test_events.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_events.py`**

```python
from orchestrator.events import ThinkingTokenEvent


def test_thinking_token_event_serialization():
    e = ThinkingTokenEvent(delta="hmm let me think")
    assert e.model_dump() == {"type": "thinking_token", "delta": "hmm let me think"}


def test_thinking_token_event_in_union():
    """ThinkingTokenEvent is part of the Event union."""
    events: list[Event] = [
        TokenEvent(delta="visible"),
        ThinkingTokenEvent(delta="hidden"),
        FinalDoneEvent(),
    ]
    types = [e.type for e in events]
    assert types == ["token", "thinking_token", "final_done"]
```

- [ ] **Step 2: Run failing test**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_events.py -v
```

Expected: ImportError (ThinkingTokenEvent doesn't exist).

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/events.py` with:**

```python
"""Typed event models emitted by Providers and consumed by the SSE encoder.

Plans extend this union as new event types arrive:
  Plan #1: TokenEvent, FinalDoneEvent, ErrorEvent
  Plan #2: ThinkingTokenEvent (this file)
  Plan #4 will add: ToolCallStartEvent, ToolCallEndEvent, StageTimingEvent
"""
from typing import Literal, Union

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


class FinalDoneEvent(BaseModel):
    type: Literal["final_done"] = "final_done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


Event = Union[TokenEvent, ThinkingTokenEvent, FinalDoneEvent, ErrorEvent]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_events.py -v
```

Expected: all 6 tests pass (4 prior + 2 new).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add ThinkingTokenEvent to event union"
```

---

## Task 3: SSE encoder routes ThinkingTokenEvent to named channel

**Files:**
- Modify: `services/orchestrator/tests/test_sse.py`

The existing `encode_sse` already routes by isinstance: `TokenEvent` goes on the default stream, everything else gets a named `event:` line. `ThinkingTokenEvent` should land on the named channel automatically — but we add a test to lock the contract so a future refactor can't accidentally merge thinking content into the user-visible content stream.

- [ ] **Step 1: Append to `services/orchestrator/tests/test_sse.py`**

```python
def test_encode_sse_thinking_token_event():
    """Thinking tokens MUST go on the named SSE channel — never on the
    default `data:` stream, so they can't contaminate user-visible content."""
    import json
    from orchestrator.events import ThinkingTokenEvent
    out = encode_sse(ThinkingTokenEvent(delta="reasoning..."))
    lines = out.splitlines()
    assert lines[0] == "event: thinking_token"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload == {"type": "thinking_token", "delta": "reasoning..."}
    assert out.endswith("\n\n")
```

- [ ] **Step 2: Run tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_sse.py -v
```

Expected: all 6 tests pass (5 prior + 1 new). No implementation change needed — the existing `encode_sse` already does the right thing because the `isinstance(event, TokenEvent)` branch only matches `TokenEvent` and `ThinkingTokenEvent` falls through to the named-channel path.

- [ ] **Step 3: Commit**

```bash
cd ../..
git add services/orchestrator/tests/test_sse.py
git commit -m "test(orch): lock SSE routing for ThinkingTokenEvent"
```

---

## Task 4: Extend `Settings` with `provider` + `provider_model` defaults

**Files:**
- Modify: `services/orchestrator/orchestrator/config.py`
- Modify: `services/orchestrator/tests/test_config.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_config.py`**

```python
def test_provider_defaults_to_local(monkeypatch):
    """No PROVIDER env → default to local."""
    for k in ("PROVIDER", "PROVIDER_MODEL"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.provider == "local"
    assert s.provider_model == ""


def test_provider_env_override(monkeypatch):
    """PROVIDER + PROVIDER_MODEL env vars set the deploy default."""
    monkeypatch.setenv("PROVIDER", "anthropic")
    monkeypatch.setenv("PROVIDER_MODEL", "claude-haiku-4-5-20251001")
    s = Settings()
    assert s.provider == "anthropic"
    assert s.provider_model == "claude-haiku-4-5-20251001"
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: AttributeError or similar — `Settings` has no `provider` field yet.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/config.py` with:**

```python
"""Runtime settings loaded from env vars."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orchestrator runtime settings.

    Default `bind_host` is 127.0.0.1 (localhost-only) — see the workshop
    MVP spec for the security rationale. LAN exposure requires explicit
    BIND_HOST=0.0.0.0 plus auth (added in a later plan).

    Provider defaults (`provider`, `provider_model`) are the DEPLOY-TIME
    default. Per-request body fields (`provider`, `model`) and headers
    (`X-Provider-Key`) override these — see orchestrator.providers.pick_provider.
    """

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    llama_url: str = "http://localhost:8081"
    request_timeout: float = 300.0
    bind_host: str = "127.0.0.1"
    bind_port: int = 8082

    # Provider selection — Plan #2
    provider: str = "local"        # "local" | "anthropic" | "openai" | "groq" | ...
    provider_model: str = ""       # only used when provider != "local"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_config.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): Settings.provider + provider_model defaults"
```

---

## Task 5: `LiteLLMProvider` — non-streaming chat

**Files:**
- Create: `services/orchestrator/orchestrator/providers/litellm_provider.py`
- Create: `services/orchestrator/tests/test_providers_litellm.py`

- [ ] **Step 1: Create `services/orchestrator/tests/test_providers_litellm.py`**

```python
"""Tests for LiteLLMProvider."""
from types import SimpleNamespace

import pytest

from orchestrator.events import FinalDoneEvent, TokenEvent
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
```

- [ ] **Step 2: Run failing test**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_providers_litellm.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.providers.litellm_provider'`.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/providers/litellm_provider.py`**

```python
"""LiteLLMProvider — cloud (or any LiteLLM-supported) chat backend.

LiteLLM normalizes ~30 providers' APIs to an OpenAI-compatible shape. We
delegate transport + auth + tool-format translation to it, and only
worry about adapting its response shape into our typed Event stream.

In Plan #2 only non-tool chat is implemented. Tool support and reasoning
streaming arrive in Plans #3-#4.
"""
import logging
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import Event, FinalDoneEvent, TokenEvent
from orchestrator.providers.base import Provider

log = logging.getLogger("orchestrator.providers.litellm")


class LiteLLMProvider(Provider):
    """Cloud chat provider routed through litellm.acompletion.

    Parameters
    ----------
    provider_name
        Identifier like "anthropic", "openai", "groq" — only used to construct
        the LiteLLM model string when callers omit a fully-qualified model.
    model
        Either a fully-qualified LiteLLM model string ("anthropic/claude-haiku-4-5-20251001")
        OR a bare model ID; provider_name is prepended when there's no slash.
    api_key
        The user's key. Passed per-request to litellm — never stored beyond
        this instance.
    timeout
        Seconds before LiteLLM gives up on the upstream call.
    """

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
    ) -> AsyncIterator[Event]:
        if stream:
            raise NotImplementedError("streaming added in Task 6")

        async for event in self._chat_non_streaming(messages):
            yield event

    async def _chat_non_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        import litellm

        resp = await litellm.acompletion(
            model=self._model,
            messages=messages,
            stream=False,
            api_key=self._api_key,
            timeout=self._timeout,
        )
        choices = resp.choices or []
        if not choices:
            yield FinalDoneEvent()
            return
        content = choices[0].message.content or ""
        if content:
            yield TokenEvent(delta=content)
        yield FinalDoneEvent()
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_litellm.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LiteLLMProvider non-streaming chat"
```

---

## Task 6: `LiteLLMProvider` — streaming chat with TokenEvents

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/litellm_provider.py`
- Modify: `services/orchestrator/tests/test_providers_litellm.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_providers_litellm.py`**

```python
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
```

- [ ] **Step 2: Run failing test**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_providers_litellm.py::test_streaming_emits_token_per_chunk -v
```

Expected: `NotImplementedError: streaming added in Task 6`.

- [ ] **Step 3: Replace the entire contents of `services/orchestrator/orchestrator/providers/litellm_provider.py` with:**

```python
"""LiteLLMProvider — cloud (or any LiteLLM-supported) chat backend.

LiteLLM normalizes ~30 providers' APIs to an OpenAI-compatible shape. We
delegate transport + auth + tool-format translation to it, and only
worry about adapting its response shape into our typed Event stream.

In Plan #2 only chat is implemented (non-streaming + streaming). Tool
support arrives in Plan #4.
"""
import logging
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import Event, FinalDoneEvent, TokenEvent
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
    ) -> AsyncIterator[Event]:
        if stream:
            async for event in self._chat_streaming(messages):
                yield event
        else:
            async for event in self._chat_non_streaming(messages):
                yield event

    async def _chat_non_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        import litellm

        resp = await litellm.acompletion(
            model=self._model,
            messages=messages,
            stream=False,
            api_key=self._api_key,
            timeout=self._timeout,
        )
        choices = resp.choices or []
        if not choices:
            yield FinalDoneEvent()
            return
        content = choices[0].message.content or ""
        if content:
            yield TokenEvent(delta=content)
        yield FinalDoneEvent()

    async def _chat_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        import litellm

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
            content = getattr(delta, "content", None)
            if content:
                yield TokenEvent(delta=content)

        yield FinalDoneEvent()
```

- [ ] **Step 4: Run all LiteLLM tests**

```bash
pytest tests/test_providers_litellm.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LiteLLMProvider streaming chat"
```

---

## Task 7: `LiteLLMProvider` — emit ThinkingTokenEvent for reasoning deltas

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/litellm_provider.py`
- Modify: `services/orchestrator/tests/test_providers_litellm.py`

LiteLLM exposes Anthropic's extended-thinking deltas via `chunk.choices[0].delta.thinking_blocks` (a list of `{type: "thinking", thinking: "<text>"}` blocks) or via a `reasoning_content` field on the delta, depending on the upstream provider. We treat both pathways: if either is non-empty, emit `ThinkingTokenEvent(delta=text)` for each thinking delta.

- [ ] **Step 1: Append to `services/orchestrator/tests/test_providers_litellm.py`**

```python
from orchestrator.events import ThinkingTokenEvent


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
```

- [ ] **Step 2: Run failing test**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_providers_litellm.py::test_streaming_emits_thinking_then_content -v
```

Expected: FAIL — current `_chat_streaming` ignores thinking surfaces.

- [ ] **Step 3: Update `_chat_streaming` in `services/orchestrator/orchestrator/providers/litellm_provider.py`**

Replace the `_chat_streaming` method with:

```python
    async def _chat_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        import litellm

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

            # Thinking deltas — two known surfaces across LiteLLM versions
            for thinking_text in _extract_thinking_deltas(delta):
                yield ThinkingTokenEvent(delta=thinking_text)

            content = getattr(delta, "content", None)
            if content:
                yield TokenEvent(delta=content)

        yield FinalDoneEvent()


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

Also add the new import at the top of the file:

```python
from orchestrator.events import Event, FinalDoneEvent, TokenEvent, ThinkingTokenEvent
```

- [ ] **Step 4: Run all LiteLLM tests**

```bash
pytest tests/test_providers_litellm.py -v
```

Expected: all three pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LiteLLMProvider emits ThinkingTokenEvent for reasoning deltas"
```

---

## Task 8: `LiteLLMProvider` — error handling

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/litellm_provider.py`
- Modify: `services/orchestrator/tests/test_providers_litellm.py`

LiteLLM raises exceptions (`litellm.APIConnectionError`, `litellm.AuthenticationError`, etc.) that all inherit from `litellm.APIError`. Wrap both call paths so they emit `ErrorEvent + FinalDoneEvent` instead of bubbling out.

- [ ] **Step 1: Append to `services/orchestrator/tests/test_providers_litellm.py`**

```python
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
```

- [ ] **Step 2: Run failing test**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_providers_litellm.py::test_auth_error_emits_error_event -v
```

Expected: FAIL — `litellm.AuthenticationError` raises out of the generator.

- [ ] **Step 3: Wrap both branches with try/except in `services/orchestrator/orchestrator/providers/litellm_provider.py`**

Replace the entire file with:

```python
"""LiteLLMProvider — cloud (or any LiteLLM-supported) chat backend.

LiteLLM normalizes ~30 providers' APIs to an OpenAI-compatible shape. We
delegate transport + auth + tool-format translation to it, and only
worry about adapting its response shape into our typed Event stream.

In Plan #2 only chat is implemented (non-streaming + streaming). Tool
support arrives in Plan #4.

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
    ) -> AsyncIterator[Event]:
        if stream:
            async for event in self._chat_streaming(messages):
                yield event
        else:
            async for event in self._chat_non_streaming(messages):
                yield event

    async def _chat_non_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        import litellm

        try:
            resp = await litellm.acompletion(
                model=self._model,
                messages=messages,
                stream=False,
                api_key=self._api_key,
                timeout=self._timeout,
            )
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
        content = choices[0].message.content or ""
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

Expected: all four pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LiteLLMProvider emits ErrorEvent on LiteLLM failure"
```

---

## Task 9: `pick_provider(request, app)` — per-request provider factory

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/__init__.py`
- Create: `services/orchestrator/tests/test_providers_pick.py`

This replaces the static `build_provider(settings)` from Plan #1. It reads body fields (`provider`, `model`) and headers (`X-Provider-Key`) and returns the correct Provider instance with the correct credentials.

Selection rules:
1. If body has `provider == "local"` OR no body override AND settings.provider == "local" → return a `LocalLlamaProvider` (shared on `app.state.local_provider` to avoid reconstructing on every call).
2. Otherwise → construct a fresh `LiteLLMProvider` per request with credentials from body + header.
3. No API key when one is required → return a "stub" provider that yields a single ErrorEvent telling the user a key is missing.

- [ ] **Step 1: Create `services/orchestrator/tests/test_providers_pick.py`**

```python
"""Tests for pick_provider — the per-request provider factory."""
from types import SimpleNamespace

import pytest

from orchestrator.events import ErrorEvent, FinalDoneEvent
from orchestrator.providers import pick_provider
from orchestrator.providers.litellm_provider import LiteLLMProvider
from orchestrator.providers.local import LocalLlamaProvider


def _fake_app(*, settings_provider: str = "local", settings_provider_model: str = ""):
    """Construct a minimal app-like object with the fields pick_provider reads."""
    settings = SimpleNamespace(
        provider=settings_provider,
        provider_model=settings_provider_model,
        llama_url="http://localhost:8081",
        request_timeout=300.0,
    )
    state = SimpleNamespace(
        settings=settings,
        local_provider=LocalLlamaProvider(
            base_url=settings.llama_url, timeout=settings.request_timeout
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
    """No body/header override + settings.provider="local" → returns the shared LocalLlamaProvider."""
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
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_providers_pick.py -v
```

Expected: ImportError (`pick_provider` doesn't exist).

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/providers/__init__.py` with:**

```python
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
from orchestrator.providers.litellm_provider import LiteLLMProvider
from orchestrator.providers.local import LocalLlamaProvider

__all__ = ["Provider", "LocalLlamaProvider", "LiteLLMProvider", "pick_provider"]


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
    ) -> AsyncIterator[Event]:
        yield ErrorEvent(
            message=(
                f"Missing API key for provider '{self._provider_name}'. "
                f"Send the key via the X-Provider-Key request header."
            )
        )
        yield FinalDoneEvent()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_pick.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): pick_provider per-request factory"
```

---

## Task 10: Wire chat route to `pick_provider`; emit ThinkingTokenEvent on stream

**Files:**
- Modify: `services/orchestrator/orchestrator/main.py`
- Modify: `services/orchestrator/orchestrator/routes/chat.py`
- Modify: `services/orchestrator/tests/test_routes.py`

Plan #1's `main.py` set `app.state.provider = build_provider(settings)`. We replace that single provider with `app.state.local_provider` (the always-available local) so `pick_provider` can fall back to it. The chat route now calls `pick_provider(request, body)` for every request, and the streaming generator routes `ThinkingTokenEvent` to `encode_sse(event)` (named channel — same path as ErrorEvent).

- [ ] **Step 1: Append two new tests to `services/orchestrator/tests/test_routes.py`**

```python
async def test_chat_provider_override_routes_to_litellm(app_client, monkeypatch):
    """body.provider="anthropic" + X-Provider-Key header → request hits LiteLLM,
    not the local llama-server. Verify by intercepting litellm.acompletion."""
    from types import SimpleNamespace
    import litellm

    captured = {}

    async def fake_acompletion(*, model, messages, stream, api_key, **kwargs):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["stream"] = stream
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="From cloud", role="assistant"),
                finish_reason="stop",
            )]
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    resp = await app_client.post(
        "/v1/chat/completions",
        json={
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"X-Provider-Key": "sk-ant-routed"},
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "From cloud"
    assert captured["model"] == "anthropic/claude-haiku-4-5-20251001"
    assert captured["api_key"] == "sk-ant-routed"
    assert captured["stream"] is False


async def test_chat_streaming_emits_thinking_on_named_channel(app_client, monkeypatch):
    """Streaming with a cloud provider that exposes thinking should send
    ThinkingTokenEvent on its named SSE channel — NEVER mixed into the
    OpenAI-style `data:` content stream."""
    from types import SimpleNamespace
    import json
    import litellm

    async def fake_acompletion(*, model, messages, stream, api_key, **kwargs):
        async def gen():
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    role="assistant",
                    thinking_blocks=[{"type": "thinking", "thinking": "hmm"}],
                ),
                finish_reason=None,
            )])
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content="Hello.", role=None),
                finish_reason=None,
            )])
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, role=None),
                finish_reason="stop",
            )])
        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    async with app_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "messages": [{"role": "user", "content": "say hi"}],
            "stream": True,
        },
        headers={"X-Provider-Key": "sk-ant-stream"},
    ) as resp:
        assert resp.status_code == 200
        body = (await resp.aread()).decode()

    # Visible content (OpenAI chunks on default stream)
    visible_contents = []
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
            visible_contents.append(delta["content"])

    assert visible_contents == ["Hello."]

    # Thinking events on the named SSE channel
    assert "event: thinking_token" in body
    # Each thinking event has its own data line with the delta
    assert '"delta": "hmm"' in body or '"delta":"hmm"' in body

    # Thinking content MUST NOT appear in any default-stream content chunk
    for c in visible_contents:
        assert "hmm" not in c
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_routes.py::test_chat_provider_override_routes_to_litellm tests/test_routes.py::test_chat_streaming_emits_thinking_on_named_channel -v
```

Expected: FAIL — current chat route uses `app.state.provider` (which doesn't exist after refactor) AND the streaming branch ignores ThinkingTokenEvent.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/main.py` with:**

```python
"""FastAPI app entry point for nodeava-orch."""
import logging

from fastapi import FastAPI

from orchestrator.config import Settings
from orchestrator.providers.local import LocalLlamaProvider
from orchestrator.routes import chat, health, models

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory. Tests can inject custom settings.

    Sets `app.state.local_provider` — the always-available local backend.
    Cloud providers are constructed per-request by
    `orchestrator.providers.pick_provider`.
    """
    settings = settings or Settings()
    app = FastAPI(title="nodeava-orch", version="0.2.0")
    app.state.settings = settings
    app.state.local_provider = LocalLlamaProvider(
        base_url=settings.llama_url, timeout=settings.request_timeout
    )
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

- [ ] **Step 4: Replace `services/orchestrator/orchestrator/routes/chat.py` with:**

```python
"""Chat completions route — both non-streaming and streaming.

This is the workhorse endpoint. The route layer is thin: it parses the
OpenAI request body, picks a Provider via `pick_provider(request, body)`,
and translates the Provider's typed Event stream into either an
OpenAI-shaped JSON response (non-streaming) or a dual-channel SSE stream
(streaming).

Streaming routing rules:
  - TokenEvent  → emitted as an OpenAI streaming chunk on the default
    SSE stream (consumed by openai SDK / fetch clients).
  - ThinkingTokenEvent → emitted via `encode_sse` on the
    `event: thinking_token` named channel (consumed by the upcoming
    brain-pane visualizer).
  - ErrorEvent → emitted via `encode_sse` on `event: error`.
  - FinalDoneEvent → ends the streaming loop; closing chunks +
    `data: [DONE]` are emitted after.
"""
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from orchestrator.events import (
    ErrorEvent,
    FinalDoneEvent,
    ThinkingTokenEvent,
    TokenEvent,
)
from orchestrator.providers import pick_provider
from orchestrator.sse import encode_openai_chunk, encode_openai_done, encode_sse

router = APIRouter()


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    # pop provider-routing fields BEFORE forwarding to the provider so they
    # are never echoed into the upstream model API.
    body.pop("provider", None)
    # body["model"] is intentionally LEFT in place — it's an OpenAI-standard
    # field that providers may want to respect (e.g. LiteLLM uses it).
    messages = body.get("messages") or []
    stream = bool(body.get("stream", False))

    provider = pick_provider(request, body)

    if not stream:
        return await _non_streaming(provider, messages)
    return await _streaming(provider, messages)


async def _non_streaming(provider, messages) -> JSONResponse:
    parts: list[str] = []
    error: str | None = None
    async for event in provider.chat(messages, stream=False):
        if isinstance(event, TokenEvent):
            parts.append(event.delta)
        elif isinstance(event, ThinkingTokenEvent):
            # Thinking content is intentionally DROPPED from non-streaming
            # responses — there's no place to put it. Streaming clients
            # see it on the named SSE channel.
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


async def _streaming(provider, messages) -> StreamingResponse:
    async def gen():
        yield encode_openai_chunk(delta_content=None, role="assistant")

        async for event in provider.chat(messages, stream=True):
            if isinstance(event, TokenEvent):
                yield encode_openai_chunk(delta_content=event.delta)
            elif isinstance(event, ThinkingTokenEvent):
                # Named SSE channel — frontends listen via
                # EventSource.addEventListener("thinking_token", ...)
                yield encode_sse(event)
            elif isinstance(event, ErrorEvent):
                yield encode_sse(event)
            elif isinstance(event, FinalDoneEvent):
                break

        yield encode_openai_chunk(delta_content=None, finish_reason="stop")
        yield encode_openai_done()

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 5: Run all tests**

```bash
pytest -v
```

Expected: all tests pass — Plan #1's 25 + 2 events + 1 sse + 4 litellm + 4 pick + 2 routes = **38 tests**.

- [ ] **Step 6: Update the `app_client` fixture's reset value if needed.**

The Plan #1 `test_run_uses_settings_bind_host_and_port` test references `app.state.settings.bind_host`/`bind_port`. The refactored `main.py` still sets those — no change needed.

But the same test should also still work because we kept `app.state.settings` and the `run()` function. Confirm by re-running the test alone:

```bash
pytest tests/test_routes.py::test_run_uses_settings_bind_host_and_port -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): chat route uses pick_provider + emits ThinkingTokenEvent"
```

---

## Task 11: README updates

**Files:**
- Modify: `services/orchestrator/README.md`

- [ ] **Step 1: Read the current README and add a new section after the Configuration section.**

Add the following block as a new top-level section, inserted RIGHT BEFORE the existing "## Run locally (dev)" section (use the actual line you find — it's around line 34 in the current README):

```markdown
## Provider selection — local vs. cloud (Plan #2)

The orchestrator can route per request to either the local llama-server
(default) or any LiteLLM-supported cloud provider (Anthropic, OpenAI,
Groq, Together, Mistral, ...). The frontend sends the API key in a
header — it's never stored server-side.

### Request-level override

```bash
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-Provider-Key: sk-ant-…' \
  -d '{
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

Body fields consumed by the orchestrator (stripped before upstream call):
- `provider` — `"local"`, `"anthropic"`, `"openai"`, `"groq"`, ... (anything LiteLLM supports)
- `model` — model id for the chosen provider; kept in the upstream call

Headers consumed by the orchestrator:
- `X-Provider-Key` — your API key for the chosen cloud provider

### Deploy-level default

For deployments that always want a cloud provider, set env vars:

| Var | Example | Purpose |
|---|---|---|
| `PROVIDER` | `anthropic` | Default provider when request omits one |
| `PROVIDER_MODEL` | `claude-haiku-4-5-20251001` | Default model for that provider |

Per-request overrides still win. API keys still come from `X-Provider-Key` —
the orchestrator never reads keys from env vars (defense in depth).

### Reasoning content streaming

Providers that expose reasoning (Anthropic extended thinking) emit
`ThinkingTokenEvent` on a NAMED SSE channel — `event: thinking_token`.
The default `data:` stream stays clean for OpenAI-SDK clients. Hook the
brain-pane visualizer with:

```js
const es = new EventSource('/v1/chat/completions?...');
es.addEventListener('thinking_token', (ev) => {
  const { delta } = JSON.parse(ev.data);
  brainPane.append(delta);
});
```

OpenAI o-series models hide reasoning entirely — no thinking events
will be emitted for those.
```

Also update the env-var table to add the two new vars. Find the existing table:

```markdown
| Var | Default | Purpose |
|---|---|---|
| `LLAMA_URL` | `http://localhost:8081` | Backend llama-server URL |
| `REQUEST_TIMEOUT` | `300` | Seconds, applies to all backend calls |
| `BIND_HOST` | `127.0.0.1` | Listener host. Default = localhost only. |
| `BIND_PORT` | `8082` | Listener port. |
```

Replace with:

```markdown
| Var | Default | Purpose |
|---|---|---|
| `LLAMA_URL` | `http://localhost:8081` | Backend llama-server URL (used when provider=local) |
| `REQUEST_TIMEOUT` | `300` | Seconds, applies to all backend calls |
| `BIND_HOST` | `127.0.0.1` | Listener host. Default = localhost only. |
| `BIND_PORT` | `8082` | Listener port. |
| `PROVIDER` | `local` | Default provider when request omits one |
| `PROVIDER_MODEL` | `""` | Default model id (only used when PROVIDER != "local") |
```

Update the "Adding a new provider" section — replace its existing 4-step list with:

```markdown
## Adding a new provider

Most providers come for free via LiteLLM — just set `provider` in the
request body and supply `X-Provider-Key`. Custom providers (e.g. a
shimmed CLI, a fully-local subprocess, an in-process model) follow this
recipe:

1. Subclass `orchestrator.providers.base.Provider`.
2. Implement the `chat()` async generator — yield `TokenEvent`,
   `ThinkingTokenEvent` (if reasoning), `ErrorEvent`, `FinalDoneEvent`.
3. Update `orchestrator.providers.pick_provider` to recognise its
   `provider` name and construct your class.
4. Write tests that mock its backend.
```

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/README.md
git commit -m "docs(orch): document provider selection + ThinkingTokenEvent SSE channel"
```

---

## Final verification

- [ ] **Step 1: Full test suite**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest -v
```

Expected tally:
- 2 config + 6 events + 6 sse + 2 providers_base + 4 providers_local + 4 providers_litellm + 4 providers_pick + 9 routes = **37 tests**

(Plan #1 had 25 tests. Plan #2 added 12 — 2 events + 1 sse + 4 litellm + 4 pick + 2 routes = 13, minus 1 because the cumulative "smoke test" doesn't get added.)

Confirm 37 pass. If a count is slightly off, that's fine — the goal is "everything passes, no skips."

- [ ] **Step 2: Docker build smoke test**

```bash
cd ../..
docker compose build orchestrator
```

Expected: succeeds. Image grew slightly because `litellm` is ~80MB installed.

- [ ] **Step 3: Optional real-backend smoke test**

Use the same `docker-compose.test.yml` override from Plan #1 to bring up `llm` + `orchestrator`, then:

```bash
# Local provider (should still work):
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say hi"}],"max_tokens":20}'

# Cloud provider override (need a real key):
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "X-Provider-Key: $ANTHROPIC_API_KEY" \
  -d '{"provider":"anthropic","model":"claude-haiku-4-5-20251001","messages":[{"role":"user","content":"say hi"}]}'

# Cloud provider missing key (should error gracefully, no upstream call):
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"provider":"openai","model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
```

The third should return a 200 with `"finish_reason": "error"` and an `"error"` key explaining the missing header.

---

## What comes next (Plan #3)

Plan #3 introduces the **tool registry** and the first two tool families:
- `browser.search` / `browser.open` / `browser.find` — bundled SearXNG-based web tools
- `wiki.search` / `wiki.open` / `wiki.list` — filesystem-backed wiki tools

Plan #3 does NOT add the agentic loop yet — tools are registered but only directly callable via a `/v1/tools/<name>` endpoint for testing. Plan #4 wires them into the chat completion flow.
