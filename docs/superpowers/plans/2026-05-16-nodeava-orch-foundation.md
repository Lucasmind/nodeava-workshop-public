# nodeava-orch Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational FastAPI service `nodeava-orch` — an OpenAI-compatible chat-completions proxy in front of a local llama-server. It exposes `/v1/chat/completions` (streaming + non-streaming), `/v1/models`, and `/health`. It introduces the Provider abstraction (one provider implemented: `LocalLlamaProvider`) and the typed Event / SSE-encoder infrastructure that later plans will extend with cloud providers and the agentic tool loop. **No tools, no agentic loop, no LiteLLM yet** — those land in Plans #2-#4.

**Architecture:** A small Python 3.12 / FastAPI application. The HTTP route layer is thin: it parses the OpenAI request, picks a Provider, and forwards events from the Provider's async generator into an SSE-encoded HTTP response (or a buffered JSON response for non-streaming). Providers are async generators that yield typed `Event` objects (Pydantic models) — this is the seam that later plans extend with `ToolCallStartEvent`, `ThinkingTokenEvent`, etc.

**Tech Stack:**
- Python 3.12, FastAPI 0.115, Uvicorn 0.34
- httpx 0.28 (async HTTP client to the llama-server backend)
- Pydantic 2.x (event models + settings)
- pydantic-settings 2.x (env var loading)
- pytest 8.x + pytest-asyncio (async test runner, auto mode)
- respx 0.21 (httpx mocking for unit tests)
- Existing infrastructure: this service builds into a Docker image and gets wired into the project's `docker-compose.yml` alongside the existing `stt-service`, `tts`, and `llm` services.

**Working directory:** all paths are repo-relative to the NodeAva repo root.

---

## File map

```
services/orchestrator/
├── Dockerfile
├── README.md
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── orchestrator/
│   ├── __init__.py
│   ├── config.py
│   ├── events.py
│   ├── sse.py
│   ├── main.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── local.py
│   └── routes/
│       ├── __init__.py
│       ├── chat.py
│       ├── health.py
│       └── models.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_config.py
    ├── test_events.py
    ├── test_sse.py
    ├── test_providers_local.py
    └── test_routes.py
```

Plus a modification to the existing top-level `docker-compose.yml` to add the `orchestrator` service.

---

## Task 1: Scaffold the project (no tests; setup only)

**Files:**
- Create: `services/orchestrator/pyproject.toml`
- Create: `services/orchestrator/requirements.txt`
- Create: `services/orchestrator/requirements-dev.txt`
- Create: `services/orchestrator/orchestrator/__init__.py` (empty)
- Create: `services/orchestrator/orchestrator/providers/__init__.py` (empty)
- Create: `services/orchestrator/orchestrator/routes/__init__.py` (empty)
- Create: `services/orchestrator/tests/__init__.py` (empty)
- Create: `services/orchestrator/tests/conftest.py`

- [ ] **Step 1: Create `services/orchestrator/pyproject.toml`**

```toml
[project]
name = "nodeava-orchestrator"
version = "0.1.0"
description = "OpenAI-compatible chat-completions proxy with provider abstraction"
requires-python = ">=3.12"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["orchestrator*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `services/orchestrator/requirements.txt`**

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
httpx==0.28.*
pydantic==2.*
pydantic-settings==2.*
```

- [ ] **Step 3: Create `services/orchestrator/requirements-dev.txt`**

```
-r requirements.txt
pytest==8.*
pytest-asyncio==0.24.*
respx==0.23.*
```

- [ ] **Step 4: Create empty package files**

Create `services/orchestrator/orchestrator/__init__.py` containing only:

```python
"""nodeava-orch — OpenAI-compatible chat proxy with provider abstraction."""
```

Create `services/orchestrator/orchestrator/providers/__init__.py` containing only:

```python
"""Provider abstraction — extensible chat backends."""
```

Create `services/orchestrator/orchestrator/routes/__init__.py` containing only:

```python
"""HTTP route modules."""
```

Create `services/orchestrator/tests/__init__.py` as an empty file.

- [ ] **Step 5: Create `services/orchestrator/tests/conftest.py`**

```python
"""Shared pytest fixtures for orchestrator tests."""
import pytest


@pytest.fixture
def llama_url() -> str:
    """Fixed mock URL used by tests so respx can match it."""
    return "http://localhost:8081"
```

- [ ] **Step 6: Install dependencies and verify pytest runs**

Run from `services/orchestrator/`:

```bash
cd services/orchestrator
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pytest -q
```

Expected: `no tests ran in 0.NNs` (zero tests collected, but pytest exits cleanly with exit code 5).

If pytest exits with `5` (no tests), proceed — that's the expected initial state. If it exits with anything else, fix import errors before proceeding.

- [ ] **Step 7: Commit**

```bash
cd ../..  # back to repo root
git add services/orchestrator/
git commit -m "feat(orch): scaffold orchestrator project structure"
```

---

## Task 2: Config module — env-var-driven settings

**Files:**
- Create: `services/orchestrator/orchestrator/config.py`
- Create: `services/orchestrator/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `services/orchestrator/tests/test_config.py`:

```python
"""Tests for the Settings module."""
import pytest

from orchestrator.config import Settings


def test_defaults_when_no_env(monkeypatch):
    """With no env vars set, defaults are used."""
    for k in ("LLAMA_URL", "REQUEST_TIMEOUT", "BIND_HOST", "BIND_PORT"):
        monkeypatch.delenv(k, raising=False)

    s = Settings()

    assert s.llama_url == "http://localhost:8081"
    assert s.request_timeout == 300.0
    assert s.bind_host == "127.0.0.1"
    assert s.bind_port == 8088


def test_env_overrides(monkeypatch):
    """Env vars override defaults."""
    monkeypatch.setenv("LLAMA_URL", "http://gpu-box:8081")
    monkeypatch.setenv("REQUEST_TIMEOUT", "60")
    monkeypatch.setenv("BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("BIND_PORT", "9000")

    s = Settings()

    assert s.llama_url == "http://gpu-box:8081"
    assert s.request_timeout == 60.0
    assert s.bind_host == "0.0.0.0"
    assert s.bind_port == 9000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.config'` (collection error).

- [ ] **Step 3: Write minimal implementation**

Create `services/orchestrator/orchestrator/config.py`:

```python
"""Runtime settings loaded from env vars."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orchestrator runtime settings.

    Default `bind_host` is 127.0.0.1 (localhost-only) — see the workshop
    MVP spec for the security rationale. LAN exposure requires explicit
    BIND_HOST=0.0.0.0 plus auth (added in a later plan).
    """

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    llama_url: str = "http://localhost:8081"
    request_timeout: float = 300.0
    bind_host: str = "127.0.0.1"
    bind_port: int = 8088
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add Settings env-var config"
```

---

## Task 3: Event schema — Pydantic models

**Files:**
- Create: `services/orchestrator/orchestrator/events.py`
- Create: `services/orchestrator/tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Create `services/orchestrator/tests/test_events.py`:

```python
"""Tests for the typed Event models."""
from orchestrator.events import Event, TokenEvent, FinalDoneEvent, ErrorEvent


def test_token_event_serialization():
    e = TokenEvent(delta="Hello")
    d = e.model_dump()
    assert d == {"type": "token", "delta": "Hello"}


def test_final_done_event_serialization():
    e = FinalDoneEvent()
    d = e.model_dump()
    assert d == {"type": "final_done"}


def test_error_event_serialization():
    e = ErrorEvent(message="backend unreachable")
    d = e.model_dump()
    assert d == {"type": "error", "message": "backend unreachable"}


def test_event_is_abstract_base_via_discriminator():
    """All concrete events should be assignable to the Event union type."""
    events: list[Event] = [
        TokenEvent(delta="x"),
        FinalDoneEvent(),
        ErrorEvent(message="boom"),
    ]
    types = [e.type for e in events]
    assert types == ["token", "final_done", "error"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_events.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.events'`.

- [ ] **Step 3: Write minimal implementation**

Create `services/orchestrator/orchestrator/events.py`:

```python
"""Typed event models emitted by Providers and consumed by the SSE encoder.

This module defines the events used in Plan #1 (foundation). Plans #2-#4 will
extend with ThinkingTokenEvent, ToolCallStartEvent, ToolCallEndEvent,
StageTimingEvent, etc. The discriminator is `type` so JSON consumers can
route on a single field.
"""
from typing import Literal, Union

from pydantic import BaseModel


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class FinalDoneEvent(BaseModel):
    type: Literal["final_done"] = "final_done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


Event = Union[TokenEvent, FinalDoneEvent, ErrorEvent]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_events.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add typed Event models"
```

---

## Task 4: SSE encoder helper

**Files:**
- Create: `services/orchestrator/orchestrator/sse.py`
- Create: `services/orchestrator/tests/test_sse.py`

The SSE encoder converts an `Event` into the wire format consumed by the frontend's `EventSource`. We use **named SSE events** (`event: type-name`) so the frontend can route by listener instead of parsing every data payload.

- [ ] **Step 1: Write the failing test**

Create `services/orchestrator/tests/test_sse.py`:

```python
"""Tests for the SSE encoder."""
import json

from orchestrator.events import TokenEvent, FinalDoneEvent, ErrorEvent
from orchestrator.sse import encode_sse, encode_openai_chunk, encode_openai_done


def test_encode_sse_token_event():
    """Token events are emitted on the default SSE event stream
    so that OpenAI-compatible clients receive them as plain `data:` chunks."""
    out = encode_sse(TokenEvent(delta="Hi"))
    # The OpenAI client expects no `event:` prefix for content chunks.
    assert out.startswith("data: ")
    payload = json.loads(out.removeprefix("data: ").strip())
    assert payload == {"type": "token", "delta": "Hi"}
    assert out.endswith("\n\n")


def test_encode_sse_named_event():
    """Non-token events get a named SSE event line so the frontend can route them."""
    out = encode_sse(ErrorEvent(message="boom"))
    lines = out.splitlines()
    assert lines[0] == "event: error"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload == {"type": "error", "message": "boom"}
    assert out.endswith("\n\n")


def test_encode_sse_final_done():
    out = encode_sse(FinalDoneEvent())
    lines = out.splitlines()
    assert lines[0] == "event: final_done"


def test_encode_openai_chunk():
    """Emit a standard OpenAI streaming chunk (used to wrap TokenEvents
    for compatibility with the official openai SDK)."""
    out = encode_openai_chunk(delta_content="Hi", finish_reason=None)
    assert out.startswith("data: ")
    payload = json.loads(out.removeprefix("data: ").strip())
    assert payload["choices"][0]["delta"]["content"] == "Hi"
    assert payload["choices"][0]["finish_reason"] is None
    assert payload["object"] == "chat.completion.chunk"


def test_encode_openai_done():
    """The OpenAI streaming convention terminates the stream with `data: [DONE]`."""
    out = encode_openai_done()
    assert out == "data: [DONE]\n\n"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_sse.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.sse'`.

- [ ] **Step 3: Write minimal implementation**

Create `services/orchestrator/orchestrator/sse.py`:

```python
"""Server-Sent Events encoding helpers.

We emit two flavors of SSE message:

1. **OpenAI-compatible chunks** (`encode_openai_chunk`, `encode_openai_done`) —
   so any OpenAI-SDK or fetch-based client can consume `/v1/chat/completions`
   without modification.

2. **NodeAva named events** (`encode_sse`) — typed Events serialized on
   named SSE event lines (`event: tool_call_start`, etc.) consumed by the
   Tier A visualizer panels via `EventSource.addEventListener('name', ...)`.

The two flavors share a single SSE stream. The OpenAI client is unaffected
by the extra named events because the EventSource default listener only
receives messages without an `event:` line.

Token content is emitted as BOTH a NodeAva TokenEvent (on the default
stream — which renders as a plain `data:` chunk and looks like an OpenAI
chunk) AND, in Plan #1, additionally wrapped in `encode_openai_chunk`
to match the exact OpenAI shape. Callers choose which to use.
"""
import json
import time
import uuid

from orchestrator.events import Event, TokenEvent


def encode_sse(event: Event) -> str:
    """Encode an Event as an SSE message.

    TokenEvent goes on the default stream (no `event:` line) so OpenAI
    clients can parse it as a chunk. All other events get a named
    `event:` line so the frontend's EventSource can route them.
    """
    payload = json.dumps(event.model_dump())
    if isinstance(event, TokenEvent):
        return f"data: {payload}\n\n"
    return f"event: {event.type}\ndata: {payload}\n\n"


def encode_openai_chunk(
    delta_content: str | None,
    *,
    finish_reason: str | None = None,
    role: str | None = None,
    model: str = "nodeava-orch",
) -> str:
    """Emit a single OpenAI-style streaming chunk."""
    delta: dict[str, object] = {}
    if role is not None:
        delta["role"] = role
    if delta_content is not None:
        delta["content"] = delta_content

    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def encode_openai_done() -> str:
    """Emit the OpenAI streaming sentinel that closes a stream."""
    return "data: [DONE]\n\n"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_sse.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add SSE encoder for events and OpenAI chunks"
```

---

## Task 5: Provider abstract base class

**Files:**
- Create: `services/orchestrator/orchestrator/providers/base.py`
- Modify: `services/orchestrator/tests/conftest.py` (add `StubProvider` fixture)

- [ ] **Step 1: Write the failing test (subclass-as-test)**

Create `services/orchestrator/tests/test_providers_base.py`:

```python
"""Tests for the Provider abstract base class."""
import pytest

from orchestrator.events import TokenEvent, FinalDoneEvent
from orchestrator.providers.base import Provider


class StubProvider(Provider):
    """Yields a fixed event sequence — used to test the ABC contract."""

    async def chat(self, messages, *, stream=False):
        yield TokenEvent(delta="hello")
        yield TokenEvent(delta=" world")
        yield FinalDoneEvent()


async def test_provider_is_async_iterable():
    """A Provider's `chat` method returns an async iterator of Events."""
    provider = StubProvider()
    events = [e async for e in provider.chat([{"role": "user", "content": "hi"}])]
    assert [e.type for e in events] == ["token", "token", "final_done"]


async def test_provider_subclass_must_implement_chat():
    """Instantiating a Provider that didn't override chat raises TypeError."""

    class BadProvider(Provider):
        pass

    with pytest.raises(TypeError):
        BadProvider()  # type: ignore[abstract]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_providers_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.providers.base'`.

- [ ] **Step 3: Write minimal implementation**

Create `services/orchestrator/orchestrator/providers/base.py`:

```python
"""Provider abstract base class.

A Provider is a chat backend (local llama-server, Anthropic, OpenAI, ...).
Implementations are async generators that yield typed Events.

In Plan #1 only LocalLlamaProvider is implemented. Plans #2-#4 extend
the Event union with ThinkingTokenEvent / ToolCallStartEvent / etc., and
add LiteLLMProvider + a tool-using agentic wrapper.
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
        """
        ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_providers_base.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add Provider abstract base class"
```

---

## Task 6: LocalLlamaProvider — non-streaming chat

**Files:**
- Create: `services/orchestrator/orchestrator/providers/local.py`
- Create: `services/orchestrator/tests/test_providers_local.py`

- [ ] **Step 1: Write the failing test**

Create `services/orchestrator/tests/test_providers_local.py`:

```python
"""Tests for LocalLlamaProvider."""
import respx
from httpx import Response

from orchestrator.events import TokenEvent, FinalDoneEvent
from orchestrator.providers.local import LocalLlamaProvider


@respx.mock
async def test_non_streaming_emits_single_token_and_done(llama_url):
    """Non-streaming: provider POSTs once, receives full JSON, yields one
    TokenEvent with the full content, then FinalDoneEvent."""
    respx.post(f"{llama_url}/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello, world."},
                        "finish_reason": "stop",
                    }
                ]
            },
        )
    )

    provider = LocalLlamaProvider(base_url=llama_url, timeout=30.0)
    events = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "hi"}], stream=False
        )
    ]

    assert len(events) == 2
    assert isinstance(events[0], TokenEvent)
    assert events[0].delta == "Hello, world."
    assert isinstance(events[1], FinalDoneEvent)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_providers_local.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.providers.local'`.

- [ ] **Step 3: Write minimal implementation**

Create `services/orchestrator/orchestrator/providers/local.py`:

```python
"""LocalLlamaProvider — forwards chat requests to a local llama-server.

The llama-server speaks OpenAI-compatible HTTP. This provider POSTs the
messages and translates either the JSON response (non-streaming) or the
SSE stream (streaming, added in Task 7) into typed Events.
"""
from collections.abc import AsyncIterator
from typing import Any

import httpx

from orchestrator.events import Event, FinalDoneEvent, TokenEvent
from orchestrator.providers.base import Provider


class LocalLlamaProvider(Provider):
    def __init__(self, *, base_url: str, timeout: float = 300.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
    ) -> AsyncIterator[Event]:
        if stream:
            raise NotImplementedError("streaming added in Task 7")

        async for event in self._chat_non_streaming(messages):
            yield event

    async def _chat_non_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json={"messages": messages, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            yield FinalDoneEvent()
            return

        content = choices[0].get("message", {}).get("content") or ""
        yield TokenEvent(delta=content)
        yield FinalDoneEvent()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_providers_local.py -v
```

Expected: test passes.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LocalLlamaProvider non-streaming chat"
```

---

## Task 7: LocalLlamaProvider — streaming TokenEvents

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/local.py`
- Modify: `services/orchestrator/tests/test_providers_local.py`

- [ ] **Step 1: Write the failing test**

Append to `services/orchestrator/tests/test_providers_local.py`:

```python
@respx.mock
async def test_streaming_emits_one_token_per_chunk(llama_url):
    """Streaming: provider opens an SSE stream and yields one TokenEvent per
    content chunk, terminating with FinalDoneEvent when the stream closes."""
    sse_body = (
        b'data: {"choices":[{"delta":{"role":"assistant"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"Hi"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" there"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n'
        b'data: [DONE]\n\n'
    )
    respx.post(f"{llama_url}/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=sse_body,
            headers={"content-type": "text/event-stream"},
        )
    )

    provider = LocalLlamaProvider(base_url=llama_url, timeout=30.0)
    events = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "hello"}], stream=True
        )
    ]

    token_deltas = [e.delta for e in events if isinstance(e, TokenEvent)]
    assert token_deltas == ["Hi", " there"]
    assert isinstance(events[-1], FinalDoneEvent)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_providers_local.py::test_streaming_emits_one_token_per_chunk -v
```

Expected: `NotImplementedError: streaming added in Task 7`.

- [ ] **Step 3: Replace the streaming stub with a real implementation**

In `services/orchestrator/orchestrator/providers/local.py`, replace the
entire file with:

```python
"""LocalLlamaProvider — forwards chat requests to a local llama-server.

The llama-server speaks OpenAI-compatible HTTP. This provider POSTs the
messages and translates either the JSON response (non-streaming) or the
SSE stream (streaming) into typed Events.
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from orchestrator.events import Event, FinalDoneEvent, TokenEvent
from orchestrator.providers.base import Provider


class LocalLlamaProvider(Provider):
    def __init__(self, *, base_url: str, timeout: float = 300.0) -> None:
        self._base_url = base_url.rstrip("/")
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
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json={"messages": messages, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices") or []
        if not choices:
            yield FinalDoneEvent()
            return

        content = choices[0].get("message", {}).get("content") or ""
        yield TokenEvent(delta=content)
        yield FinalDoneEvent()

    async def _chat_streaming(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[Event]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/v1/chat/completions",
                json={"messages": messages, "stream": True},
            ) as resp:
                resp.raise_for_status()
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

        yield FinalDoneEvent()
```

- [ ] **Step 4: Run all provider tests to verify both pass**

```bash
pytest tests/test_providers_local.py -v
```

Expected: both `test_non_streaming_emits_single_token_and_done` and
`test_streaming_emits_one_token_per_chunk` pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LocalLlamaProvider streaming chat"
```

---

## Task 8: LocalLlamaProvider — backend error handling

**Files:**
- Modify: `services/orchestrator/orchestrator/providers/local.py`
- Modify: `services/orchestrator/tests/test_providers_local.py`

- [ ] **Step 1: Write the failing test**

Append to `services/orchestrator/tests/test_providers_local.py`:

```python
from orchestrator.events import ErrorEvent


@respx.mock
async def test_backend_http_error_emits_error_event(llama_url):
    """If the llama-server returns a non-2xx, emit a single ErrorEvent
    followed by FinalDoneEvent — never raise out of the generator."""
    respx.post(f"{llama_url}/v1/chat/completions").mock(
        return_value=Response(503, text="model still loading")
    )

    provider = LocalLlamaProvider(base_url=llama_url, timeout=30.0)
    events = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "hi"}], stream=False
        )
    ]

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    done_events = [e for e in events if isinstance(e, FinalDoneEvent)]
    assert len(error_events) == 1
    assert "503" in error_events[0].message
    assert len(done_events) == 1


@respx.mock
async def test_backend_unreachable_emits_error_event(llama_url):
    """Connection errors also produce an ErrorEvent, not an exception."""
    import httpx

    respx.post(f"{llama_url}/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    provider = LocalLlamaProvider(base_url=llama_url, timeout=30.0)
    events = [
        e
        async for e in provider.chat(
            [{"role": "user", "content": "hi"}], stream=False
        )
    ]

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(error_events) == 1
    assert "connection" in error_events[0].message.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_providers_local.py::test_backend_http_error_emits_error_event tests/test_providers_local.py::test_backend_unreachable_emits_error_event -v
```

Expected: both fail because the current implementation calls `resp.raise_for_status()` and lets the exception escape the generator.

- [ ] **Step 3: Wrap both paths in try/except**

In `services/orchestrator/orchestrator/providers/local.py`, replace the
file with:

```python
"""LocalLlamaProvider — forwards chat requests to a local llama-server.

The llama-server speaks OpenAI-compatible HTTP. This provider POSTs the
messages and translates either the JSON response (non-streaming) or the
SSE stream (streaming) into typed Events.

Error handling: HTTP errors and connection errors do NOT raise out of
the generator. Instead, the generator yields an ErrorEvent followed by
FinalDoneEvent. This contract simplifies the route layer — it always
gets a clean event stream regardless of backend health.
"""
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from orchestrator.events import Event, ErrorEvent, FinalDoneEvent, TokenEvent
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
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json={"messages": messages, "stream": False},
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

        content = choices[0].get("message", {}).get("content") or ""
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

Expected: all four tests pass (non-streaming, streaming, HTTP error, connection error).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LocalLlamaProvider emits ErrorEvent on backend failure"
```

---

## Task 9: FastAPI app skeleton with DI

**Files:**
- Create: `services/orchestrator/orchestrator/main.py`

This task wires the FastAPI app and dependency injection but adds no routes yet. We'll add `/health`, `/v1/models`, and `/v1/chat/completions` in Tasks 10-13.

- [ ] **Step 1: Replace `tests/conftest.py` with an extended version**

Replace the entire contents of `services/orchestrator/tests/conftest.py` with:

```python
"""Shared pytest fixtures for orchestrator tests."""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def llama_url() -> str:
    """Fixed mock URL used by tests so respx can match it."""
    return "http://localhost:8081"


@pytest.fixture
async def app_client():
    """An httpx AsyncClient mounted directly against the FastAPI app."""
    from orchestrator.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

Create `services/orchestrator/tests/test_routes.py`:

```python
"""Tests for HTTP routes."""


async def test_app_imports_and_serves_404_for_unknown_route(app_client):
    """Smoke test: the app boots and serves an unknown path with 404."""
    resp = await app_client.get("/does-not-exist")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_routes.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.main'`.

- [ ] **Step 3: Create the FastAPI app**

Create `services/orchestrator/orchestrator/main.py`:

```python
"""FastAPI app entry point for nodeava-orch."""
import logging

from fastapi import FastAPI

from orchestrator.config import Settings
from orchestrator.providers.base import Provider
from orchestrator.providers.local import LocalLlamaProvider

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def build_provider(settings: Settings) -> Provider:
    """Construct the active Provider.

    Plan #1 always returns a LocalLlamaProvider. Plan #2 will switch on
    settings.provider to also support LiteLLMProvider.
    """
    return LocalLlamaProvider(
        base_url=settings.llama_url, timeout=settings.request_timeout
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory. Tests can inject custom settings."""
    settings = settings or Settings()
    app = FastAPI(title="nodeava-orch", version="0.1.0")
    app.state.settings = settings
    app.state.provider = build_provider(settings)
    return app


# Module-level app for `uvicorn orchestrator.main:app`
app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_routes.py -v
```

Expected: smoke test passes.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): FastAPI app skeleton with provider DI"
```

---

## Task 10: Health route

**Files:**
- Create: `services/orchestrator/orchestrator/routes/health.py`
- Modify: `services/orchestrator/orchestrator/main.py` (register router)
- Modify: `services/orchestrator/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `services/orchestrator/tests/test_routes.py`:

```python
import respx
from httpx import Response


@respx.mock
async def test_health_ok_when_backend_healthy(app_client):
    respx.get("http://localhost:8081/health").mock(return_value=Response(200))
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "backend": "http://localhost:8081"}


@respx.mock
async def test_health_503_when_backend_unhealthy(app_client):
    respx.get("http://localhost:8081/health").mock(return_value=Response(500))
    resp = await app_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert "backend" in body
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_routes.py -v
```

Expected: both new tests return 404 (route not registered yet).

- [ ] **Step 3: Implement the health route**

Create `services/orchestrator/orchestrator/routes/health.py`:

```python
"""Health route — checks backend reachability."""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    backend = settings.llama_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{backend}/health")
        if resp.status_code == 200:
            return JSONResponse({"status": "ok", "backend": backend})
        return JSONResponse(
            {
                "status": "unhealthy",
                "backend": backend,
                "detail": f"backend returned HTTP {resp.status_code}",
            },
            status_code=503,
        )
    except httpx.HTTPError as e:
        return JSONResponse(
            {"status": "unhealthy", "backend": backend, "detail": str(e)},
            status_code=503,
        )
```

Modify `services/orchestrator/orchestrator/main.py` to register the router.
Replace its contents with:

```python
"""FastAPI app entry point for nodeava-orch."""
import logging

from fastapi import FastAPI

from orchestrator.config import Settings
from orchestrator.providers.base import Provider
from orchestrator.providers.local import LocalLlamaProvider
from orchestrator.routes import health

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def build_provider(settings: Settings) -> Provider:
    return LocalLlamaProvider(
        base_url=settings.llama_url, timeout=settings.request_timeout
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="nodeava-orch", version="0.1.0")
    app.state.settings = settings
    app.state.provider = build_provider(settings)
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_routes.py -v
```

Expected: smoke test + both health tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add /health route"
```

---

## Task 11: Models route

**Files:**
- Create: `services/orchestrator/orchestrator/routes/models.py`
- Modify: `services/orchestrator/orchestrator/main.py`
- Modify: `services/orchestrator/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `services/orchestrator/tests/test_routes.py`:

```python
@respx.mock
async def test_models_proxies_backend_list(app_client):
    """GET /v1/models proxies the backend's /v1/models response."""
    respx.get("http://localhost:8081/v1/models").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [{"id": "qwen3-4b", "object": "model"}],
            },
        )
    )
    resp = await app_client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json()["data"][0]["id"] == "qwen3-4b"


@respx.mock
async def test_models_returns_empty_list_if_backend_down(app_client):
    """If the backend is unreachable we return an empty list, not 500."""
    import httpx

    respx.get("http://localhost:8081/v1/models").mock(
        side_effect=httpx.ConnectError("down")
    )
    resp = await app_client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json() == {"object": "list", "data": []}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_routes.py -v
```

Expected: both new tests 404.

- [ ] **Step 3: Implement the models route**

Create `services/orchestrator/orchestrator/routes/models.py`:

```python
"""Models route — proxies the backend's /v1/models for OpenAI compatibility."""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    backend = request.app.state.settings.llama_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{backend}/v1/models")
        if resp.status_code == 200:
            return JSONResponse(resp.json())
    except httpx.HTTPError:
        pass
    return JSONResponse({"object": "list", "data": []})
```

Modify `services/orchestrator/orchestrator/main.py` to also include the models router. Update the imports and `include_router` calls:

```python
from orchestrator.routes import health, models

# ... in create_app, after include_router(health.router):
    app.include_router(models.router)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_routes.py -v
```

Expected: all route tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): add /v1/models route"
```

---

## Task 12: Chat completions — non-streaming

**Files:**
- Create: `services/orchestrator/orchestrator/routes/chat.py`
- Modify: `services/orchestrator/orchestrator/main.py`
- Modify: `services/orchestrator/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `services/orchestrator/tests/test_routes.py`:

```python
@respx.mock
async def test_chat_non_streaming_returns_openai_shape(app_client):
    """Non-streaming chat returns an OpenAI-shaped JSON response with the
    full text in choices[0].message.content."""
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Greetings."},
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
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "Greetings."
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["object"] == "chat.completion"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_routes.py::test_chat_non_streaming_returns_openai_shape -v
```

Expected: 404.

- [ ] **Step 3: Implement the non-streaming branch**

Create `services/orchestrator/orchestrator/routes/chat.py`:

```python
"""Chat completions route — both non-streaming and streaming.

This is the workhorse endpoint. In Plan #1 it forwards every request
through the configured Provider. Plans #3-#4 will add an agentic loop
that wraps the provider when tools are enabled.
"""
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from orchestrator.events import ErrorEvent, FinalDoneEvent, TokenEvent
from orchestrator.sse import encode_openai_chunk, encode_openai_done, encode_sse

router = APIRouter()


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages") or []
    stream = bool(body.get("stream", False))

    provider = request.app.state.provider

    if not stream:
        return await _non_streaming(provider, messages)
    return await _streaming(provider, messages)


async def _non_streaming(provider, messages) -> JSONResponse:
    parts: list[str] = []
    error: str | None = None
    async for event in provider.chat(messages, stream=False):
        if isinstance(event, TokenEvent):
            parts.append(event.delta)
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
    raise NotImplementedError("streaming added in Task 13")
```

Modify `services/orchestrator/orchestrator/main.py` to register the chat
router. Add to imports and `include_router` calls:

```python
from orchestrator.routes import chat, health, models

# in create_app:
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_routes.py -v
```

Expected: all route tests pass.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): /v1/chat/completions non-streaming"
```

---

## Task 13: Chat completions — streaming

**Files:**
- Modify: `services/orchestrator/orchestrator/routes/chat.py`
- Modify: `services/orchestrator/tests/test_routes.py`

- [ ] **Step 1: Write the failing test**

Append to `services/orchestrator/tests/test_routes.py`:

```python
import json


@respx.mock
async def test_chat_streaming_emits_openai_chunks_then_done(app_client):
    """Streaming chat: each TokenEvent → an OpenAI-shaped `data: {...}` chunk;
    FinalDoneEvent → `data: [DONE]`."""
    sse_body = (
        b'data: {"choices":[{"delta":{"role":"assistant"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"Hi"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"!"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n'
        b'data: [DONE]\n\n'
    )
    respx.post("http://localhost:8081/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=sse_body,
            headers={"content-type": "text/event-stream"},
        )
    )

    async with app_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = (await resp.aread()).decode()

    # Parse the SSE body: collect content from data: chunks before [DONE].
    contents = []
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        chunk = json.loads(payload)
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta:
            contents.append(delta["content"])

    assert contents == ["Hi", "!"]
    assert body.rstrip().endswith("data: [DONE]")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_routes.py::test_chat_streaming_emits_openai_chunks_then_done -v
```

Expected: `NotImplementedError: streaming added in Task 13`.

- [ ] **Step 3: Implement the streaming branch**

In `services/orchestrator/orchestrator/routes/chat.py`, replace the
`_streaming` function:

```python
async def _streaming(provider, messages) -> StreamingResponse:
    async def gen():
        # Initial role chunk (OpenAI convention — many clients expect this).
        yield encode_openai_chunk(delta_content=None, role="assistant")

        async for event in provider.chat(messages, stream=True):
            if isinstance(event, TokenEvent):
                yield encode_openai_chunk(delta_content=event.delta)
            elif isinstance(event, ErrorEvent):
                # Emit on the named SSE event channel so the frontend can
                # display the error without confusing the OpenAI SDK parser.
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

Expected: every test in the suite passes.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): /v1/chat/completions streaming"
```

---

## Task 14: Dockerfile + docker-compose integration

**Files:**
- Create: `services/orchestrator/Dockerfile`
- Modify: `docker-compose.yml` (repo root)

- [ ] **Step 1: Create the Dockerfile**

Create `services/orchestrator/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY orchestrator/ ./orchestrator/

RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8088/health || exit 1

CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8088", "--log-level", "info"]
```

- [ ] **Step 2: Read the existing top-level docker-compose.yml**

Open `docker-compose.yml` at the repo root and identify the `llm` service
block. The orchestrator depends on it; add the new service after it.

- [ ] **Step 3: Append the orchestrator service to docker-compose.yml**

Add the following service definition to `docker-compose.yml`. Place it
after the existing `llm` service block, at the same indentation level:

```yaml
  orchestrator:
    build:
      context: ./services/orchestrator
      dockerfile: Dockerfile
    image: nodeava-orch:latest
    container_name: nodeava-orch
    ports:
      - "127.0.0.1:8088:8088"
    environment:
      - LLAMA_URL=http://llm:8080
      - REQUEST_TIMEOUT=300
      - BIND_HOST=0.0.0.0
      - BIND_PORT=8088
    depends_on:
      llm:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

If the existing `llm` service does not have a healthcheck, do NOT add
`depends_on.llm.condition: service_healthy` — use the simpler form
`depends_on: [llm]` instead. (Read the existing compose to decide.)

The host port mapping `127.0.0.1:8088:8088` enforces the localhost-only
default from the spec. LAN exposure is handled in a later plan.

- [ ] **Step 4: Verify the build succeeds**

From the repo root:

```bash
docker compose build orchestrator
```

Expected: build succeeds. (We don't `docker compose up` here because
the upstream `llm` service may not be configured on every dev machine —
that's a separate smoke test in a later integration plan.)

- [ ] **Step 5: Commit**

```bash
git add services/orchestrator/Dockerfile docker-compose.yml
git commit -m "feat(orch): Dockerfile + docker-compose service entry"
```

---

## Task 15: Service-level README

**Files:**
- Create: `services/orchestrator/README.md`

This is a documentation task (no test). The README is critical for the
next plans — every plan that extends the orchestrator will reference it.

- [ ] **Step 1: Create the README**

Create `services/orchestrator/README.md`:

````markdown
# nodeava-orch

An OpenAI-compatible chat-completions proxy in front of NodeAva's local
llama-server. This service is the seam where:

- The frontend talks to one URL regardless of backend (local or cloud).
- The agentic tool loop (Plan #4) lives.
- Tier A SSE events (`tool_call_start`, etc.) are emitted to drive the
  visualizer panels.

**Plan #1 scope:** scaffold + LocalLlamaProvider + chat/health/models
routes. Tools, LiteLLM, and agentic loop come in later plans.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat (stream + non-stream) |
| `POST` | `/chat/completions` | Alias |
| `GET`  | `/v1/models` | Proxy of backend model list |
| `GET`  | `/health` | Reports backend reachability |

## Configuration

Env vars (loaded via `pydantic-settings`):

| Var | Default | Purpose |
|---|---|---|
| `LLAMA_URL` | `http://localhost:8081` | Backend llama-server URL |
| `REQUEST_TIMEOUT` | `300` | Seconds, applies to all backend calls |
| `BIND_HOST` | `127.0.0.1` | Listener host. Default = localhost only. |
| `BIND_PORT` | `8088` | Listener port. |

## Run locally (dev)

```bash
cd services/orchestrator
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

# Point at a running llama-server (the workshop default port is 8081).
export LLAMA_URL=http://localhost:8081
uvicorn orchestrator.main:app --reload --port 8088
```

## Run via Docker (with the rest of NodeAva)

```bash
# From the repo root:
docker compose up -d orchestrator
```

## Test

```bash
cd services/orchestrator
source .venv/bin/activate
pytest -v
```

## Architecture

```
HTTP (OpenAI) ──► routes/chat.py
                       │
                       ▼
                 Provider.chat() ──► local.py (Plan #1)
                       │              litellm.py (Plan #2)
                       │
                       ▼
                 Event async iter
                       │
                       ▼
              SSE encoder (sse.py)
                       │
                       ▼
                  Wire to client
```

A Provider is an abstract async generator that yields typed Events
(`orchestrator/events.py`). The chat route translates Events into
OpenAI-compatible SSE chunks (for the OpenAI client) and named SSE
events (for the frontend's Tier A panels) on a single stream.

## Adding a new provider

1. Subclass `orchestrator.providers.base.Provider`.
2. Implement the `chat()` async generator — yield `TokenEvent`,
   `ErrorEvent`, `FinalDoneEvent` (Plan #1 events). Later plans add
   more event types you'll yield from too.
3. Register it in `orchestrator/main.py::build_provider` keyed off a
   settings field.
4. Write tests that mock its backend with `respx`.

## Why a custom service when LLMRunners has one?

NodeAva needs a NodeAva-flavored orchestrator: provider switching,
wiki tools, named SSE events for visualizers, localhost-only default.
The LLMRunners orchestrator is the inspiration but is shaped for a
different deployment (chimera, MoE thinking models, OpenWebUI). See
`docs/superpowers/specs/2026-05-16-nodeava-workshop-mvp-design.md`.
````

- [ ] **Step 2: Commit**

```bash
git add services/orchestrator/README.md
git commit -m "docs(orch): service-level README"
```

---

## Final verification

Before marking this plan complete, run the full test suite and confirm
the build:

- [ ] **Step 1: Full test suite passes**

```bash
cd services/orchestrator
source .venv/bin/activate
pytest -v
```

Expected: all tests pass. Tally roughly:
- 2 tests in `test_config.py`
- 4 tests in `test_events.py`
- 5 tests in `test_sse.py`
- 2 tests in `test_providers_base.py`
- 4 tests in `test_providers_local.py`
- 1 smoke + 2 health + 2 models + 1 chat-non-stream + 1 chat-stream = 7 tests in `test_routes.py`

Total: ~24 tests.

- [ ] **Step 2: Docker build succeeds**

```bash
cd ../..
docker compose build orchestrator
```

Expected: image builds successfully.

- [ ] **Step 3: Manual smoke test (optional but recommended)**

If a llama-server is running at `localhost:8081`:

```bash
# In one terminal:
LLAMA_URL=http://localhost:8081 uvicorn orchestrator.main:app --port 8088

# In another:
curl http://localhost:8088/health
curl -X POST http://localhost:8088/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hi"}]}'

# Streaming:
curl -N -X POST http://localhost:8088/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Say hi"}],"stream":true}'
```

Expected: health returns OK; non-streaming returns OpenAI-shaped JSON;
streaming returns SSE chunks terminated by `data: [DONE]`.

---

## What comes next (Plan #2)

Plan #2 adds the second provider: **LiteLLMProvider**, enabling Anthropic,
OpenAI, Groq, Together, and others. It will:

1. Add `LiteLLMProvider` alongside `LocalLlamaProvider`.
2. Extend `Settings` with `provider` and `provider_model` fields.
3. Add per-request override: `X-Provider`, `X-Provider-Model`,
   `X-Provider-Key` headers consumed by the chat route.
4. Update `build_provider` to switch on `provider`.
5. Add tests that mock LiteLLM's async completion.

Plan #2 does **not** add tools or agentic features — those are Plans #3
and #4.
