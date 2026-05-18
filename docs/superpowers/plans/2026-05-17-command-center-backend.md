# Command Center Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the backend NodeAva's dashboard talks to — catalog + state + swap endpoints + Ollama-native local LLM serving + interactive teaching scripts — implementing Plans #7's spec.

**Architecture:** One Ollama service running on the host (cross-platform — Linux/WSL2 via curl-pipe install, Mac via brew) replaces the in-Docker llama.cpp service. Orchestrator reaches Ollama via `host.docker.internal:11434`. Two source-of-truth files (`configs/catalog.yml` and `state/current.json`) drive three new endpoints (GET /v1/catalog, GET /v1/state, POST /v1/swap) plus a provider dispatcher that routes per-request to Ollama, LiteLLM (cloud), or an openai-compatible escape hatch.

**Tech Stack:** Python 3.12, FastAPI, pydantic-settings, httpx, PyYAML, pytest. Ollama (host, native). Bash for teaching scripts. Cross-platform audio: `arecord` (Linux/WSL2) + `sox` (macOS).

**Spec:** `docs/superpowers/specs/2026-05-16-command-center-backend-design.md`

---

## File structure

### New files

| Path | Purpose |
|------|---------|
| `configs/catalog.yml` | Single source of truth for swappable brains/voices/avatars/personalities |
| `state/current.json` | Single source of truth for what's active; persisted across orchestrator restarts |
| `state/.gitkeep` | Track the directory in git without tracking the runtime file |
| `services/orchestrator/orchestrator/catalog.py` | Load + validate the catalog YAML |
| `services/orchestrator/orchestrator/state.py` | Atomic R/W of state/current.json |
| `services/orchestrator/orchestrator/system/__init__.py` | Module marker |
| `services/orchestrator/orchestrator/system/residency.py` | Query Ollama /api/ps; derive gpu/split/cpu labels |
| `services/orchestrator/orchestrator/providers/ollama.py` | OllamaProvider — talks to Ollama's OpenAI-compatible endpoint |
| `services/orchestrator/orchestrator/providers/dispatcher.py` | Per-request brain selection (Ollama / cloud-litellm / openai-compatible) |
| `services/orchestrator/orchestrator/routes/catalog.py` | GET /v1/catalog |
| `services/orchestrator/orchestrator/routes/state.py` | GET /v1/state |
| `services/orchestrator/orchestrator/routes/swap.py` | POST /v1/swap |
| `services/orchestrator/tests/test_catalog.py` | Catalog parser tests |
| `services/orchestrator/tests/test_state.py` | State R/W tests |
| `services/orchestrator/tests/test_providers_ollama.py` | Ollama provider tests |
| `services/orchestrator/tests/test_providers_dispatcher.py` | Dispatcher routing tests |
| `services/orchestrator/tests/test_routes_catalog.py` | Catalog route tests |
| `services/orchestrator/tests/test_routes_state.py` | State route + residency tests |
| `services/orchestrator/tests/test_routes_swap.py` | Swap route tests |
| `services/orchestrator/tests/test_system_residency.py` | Residency module tests |
| `scripts/setup-linux.sh` | Ollama install (curl-pipe) + model pulls (Linux/WSL2) |
| `scripts/demos/_audio.sh` | Cross-platform mic record / playback helper sourced by other demo scripts |
| `scripts/demos/test-llm.sh` | Interactive LLM token-stream demo |
| `scripts/demos/test-tts.sh` | Interactive TTS synthesize+play demo |
| `scripts/demos/test-stt.sh` | Interactive mic→Whisper demo |
| `scripts/demos/test-pipeline.sh` | Full mic→STT→LLM→TTS→speaker pipeline |
| `scripts/demos/test-orchestrator.sh` | Interactive swap-and-show-state menu |
| `scripts/demos/list-models.sh` | Print catalog with availability |
| `assets/demos/sample-stt.wav` | Shipped fixture for `--fixture` mode of test-stt.sh |

### Modified files

| Path | Change |
|------|--------|
| `docker-compose.yml` | Remove `llm` service; add `extra_hosts: host-gateway` + `OLLAMA_URL` env + `./state:/app/state:rw` mount to `orchestrator` |
| `docker-compose.gpu-nvidia.yml` | Remove the `llm` override section |
| `docker-compose.gpu-amd.yml` | Remove the `llm` override section |
| `services/orchestrator/orchestrator/config.py` | Rename `llama_url` → `ollama_url`; default `http://host.docker.internal:11434` |
| `services/orchestrator/orchestrator/main.py` | Replace `LocalLlamaProvider` with `OllamaProvider`; register new routers; load catalog + state at startup |
| `services/orchestrator/orchestrator/providers/__init__.py` | Export `OllamaProvider` + `pick_provider_by_brain` (new dispatcher entry point) |
| `services/orchestrator/orchestrator/routes/chat.py` | Use dispatcher per-request; inject personality system prompt; read tool toggles from state instead of body |
| `services/orchestrator/requirements.txt` | Add `pyyaml>=6.0,<7.0` |
| `scripts/setup-mac.sh` | Replace llama.cpp install with `brew install ollama`; pull default models |
| `scripts/start-mac.sh` | Replace `llama-server` start with `ollama serve` check |
| `scripts/stop-mac.sh` | Drop `pkill llama-server` |
| `frontend/src/tts/TTSManager.js` | Read voice from `/v1/state` on init instead of `config.ttsDefaultVoice` |
| `frontend/src/avatar/AvatarManager.js` | Read avatar from `/v1/state` on init |
| `frontend/src/ui/components/ControlPanel.js` | Replace localStorage writes with POST /v1/swap for `tools` toggles |
| `frontend/src/pipeline/Orchestrator.js` | Drop `web_search` / `wiki` body fields — state lives server-side now |
| `frontend/vite.config.js` | Add `/api/orch` proxy entry for `/v1/catalog`, `/v1/state`, `/v1/swap` |
| `CLAUDE.md` | Update LLM section, port table, add Plan #7 summary |
| `README.md` | Update install instructions for Ollama prereq |
| `services/orchestrator/README.md` | Document new endpoints |

---

## Task 1: Docker / compose migration

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.gpu-nvidia.yml`
- Modify: `docker-compose.gpu-amd.yml`
- Create: `state/.gitkeep`

This task removes the in-Docker llama.cpp `llm` service and wires the orchestrator to reach the host's Ollama via `host.docker.internal:11434`. After this task, attempting to bring up the stack will need a host Ollama running — Task 2 installs it.

- [ ] **Step 1: Inspect the current orchestrator service block**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
grep -A 30 "^  orchestrator:" docker-compose.yml
```

Note the current `volumes`, `environment`, and `depends_on` blocks — you'll edit them next.

- [ ] **Step 2: Edit `docker-compose.yml` — remove the `llm` service entirely**

Find the block that starts with `  llm:` (about 30 lines). Delete the entire service definition. After deletion, the file should have only these services: `orchestrator`, `tts`, `stt`, `searxng`, `frontend`.

- [ ] **Step 3: Edit `docker-compose.yml` — update the orchestrator service**

Replace the orchestrator service's `environment`, `depends_on`, and `volumes` sections.

In the `environment:` block, REPLACE `- LLAMA_URL=http://llm:8080` with `- OLLAMA_URL=http://host.docker.internal:11434`. Leave the other env vars (`REQUEST_TIMEOUT`, `BIND_HOST`, `BIND_PORT`, `WIKI_DIR`, `RAW_DIR`, `WIKI_COMPILER_PATH`, `ANTHROPIC_API_KEY`) untouched.

In the `depends_on:` block, REMOVE the `llm:` entry. Keep `searxng:`.

In the `volumes:` block, ADD a new line for the state mount:

```yaml
      - ./state:/app/state:rw
```

Place it after the existing `./raw:/app/raw:rw` line.

ADD a new top-level key under the orchestrator service (sibling to `volumes`, `environment`, etc.):

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

On Mac/Windows Docker Desktop this is a no-op (the alias exists natively). On Linux it injects the host gateway IP under the `host.docker.internal` hostname so the orchestrator container can reach Ollama running on the host.

- [ ] **Step 4: Edit `docker-compose.gpu-nvidia.yml` — delete the `llm:` block**

The whole `llm:` block (with `image: ghcr.io/ggml-org/llama.cpp:server-cuda` etc.) goes. Leave the `tts:` and `stt:` GPU overrides intact.

- [ ] **Step 5: Edit `docker-compose.gpu-amd.yml` — delete the `llm:` block**

Same pattern — delete the entire `llm:` block. Leave other AMD-specific overrides intact.

- [ ] **Step 6: Create `state/` directory and `.gitkeep`**

```bash
mkdir -p state
touch state/.gitkeep
```

This makes the empty directory committable. The runtime `state/current.json` file will be gitignored — add it now:

```bash
echo "state/current.json" >> .gitignore
```

- [ ] **Step 7: Verify compose still parses**

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.gpu-amd.yml config --quiet
```

Expected: all three exit 0 with no output (config is valid). If any complain about anchors / references / missing services, fix the YAML.

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml docker-compose.gpu-nvidia.yml docker-compose.gpu-amd.yml state/.gitkeep .gitignore
git commit -m "feat(compose): remove llm service; wire orchestrator to host Ollama"
```

---

## Task 2: Ollama setup scripts (host install)

**Files:**
- Create: `scripts/setup-linux.sh`
- Modify: `scripts/setup-mac.sh`
- Modify: `scripts/start-mac.sh`
- Modify: `scripts/stop-mac.sh`

After Task 1 the orchestrator expects Ollama on the host. This task installs it.

- [ ] **Step 1: Create `scripts/setup-linux.sh`**

```bash
#!/bin/bash
# Install Ollama (host-native) and pull NodeAva's default models.
# Works on Linux distros + WSL2.
set -euo pipefail

echo "[setup-linux] Checking for Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "[setup-linux] Installing Ollama via official installer..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "[setup-linux] Ollama already installed: $(ollama --version 2>/dev/null || echo unknown)"
fi

# Ollama installs as a systemd service on most distros; on WSL2 / minimal
# installs it may need to be started manually. Probe and start if needed.
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[setup-linux] Ollama not responding. Attempting to start..."
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-enabled ollama >/dev/null 2>&1; then
    systemctl --user start ollama
  else
    # WSL2 or no systemd — start a detached process
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 2
  fi
fi

if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[setup-linux] ERROR: Ollama is not reachable at http://localhost:11434"
  echo "[setup-linux] Start it manually with 'ollama serve' and rerun this script."
  exit 1
fi

echo "[setup-linux] Pulling default models..."
ollama pull qwen3:4b
ollama pull smollm2:360m

echo "[setup-linux] Done. Ollama is ready."
```

```bash
chmod +x scripts/setup-linux.sh
```

- [ ] **Step 2: Modify `scripts/setup-mac.sh` — replace llama.cpp install with Ollama**

Read the current file first:

```bash
cat scripts/setup-mac.sh
```

Find the block that installs llama.cpp (look for `brew install llama.cpp` or similar). Delete that block and the subsequent llama.cpp model-file download steps. Add an Ollama section in its place:

```bash
# --- Ollama (replaces llama.cpp as of Plan #7) ---
if ! command -v ollama >/dev/null 2>&1; then
  echo "[setup-mac] Installing Ollama via Homebrew..."
  brew install ollama
else
  echo "[setup-mac] Ollama already installed: $(ollama --version)"
fi

# Ollama starts automatically on macOS after `brew install`. Probe to confirm.
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[setup-mac] Starting Ollama..."
  (ollama serve >/tmp/ollama.log 2>&1 &)
  sleep 2
fi

if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[setup-mac] ERROR: Ollama did not start. Try 'ollama serve' in a separate terminal."
  exit 1
fi

echo "[setup-mac] Pulling default models..."
ollama pull qwen3:4b
ollama pull smollm2:360m
```

Keep the Kokoro-FastAPI clone, the Whisper model download, the Python venv setup. Those are unchanged.

- [ ] **Step 3: Modify `scripts/start-mac.sh` — drop llama-server launch**

```bash
grep -n "llama-server\|llama_server\|llamaServer\|LLM_MODEL" scripts/start-mac.sh
```

Find the section that launches `llama-server` (with the `-m models/Qwen_*` flag). Delete it. Replace with a probe + launch for Ollama:

```bash
# --- Ollama (Plan #7) ---
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[start-mac] Starting Ollama..."
  (ollama serve >/tmp/ollama.log 2>&1 &)
  for i in $(seq 1 10); do
    if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi
echo "[start-mac] Ollama is up."
```

Drop any subsequent block that waits on `localhost:8081` (the old llama-server port) — Ollama lives on 11434 now.

- [ ] **Step 4: Modify `scripts/stop-mac.sh` — drop the llama-server kill**

```bash
grep -n "llama" scripts/stop-mac.sh
```

Remove any line that kills `llama-server` (e.g. `pkill -f llama-server`). Leave Ollama running on shutdown — it's a host service the user may want for other apps.

- [ ] **Step 5: Smoke-test on the current (Linux) host**

```bash
ollama --version 2>&1 | head -1
curl -fsS http://localhost:11434/api/tags | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d[\"models\"])} models pulled')"
```

Expected: prints "N models pulled" (some number ≥ 0). If Ollama isn't installed on this host, run `bash scripts/setup-linux.sh` first.

- [ ] **Step 6: Commit**

```bash
git add scripts/setup-linux.sh scripts/setup-mac.sh scripts/start-mac.sh scripts/stop-mac.sh
git commit -m "feat(scripts): install Ollama on host; remove llama.cpp install"
```

---

## Task 3: Ollama provider client

**Files:**
- Create: `services/orchestrator/orchestrator/providers/ollama.py`
- Modify: `services/orchestrator/orchestrator/providers/__init__.py`
- Modify: `services/orchestrator/orchestrator/config.py`
- Modify: `services/orchestrator/orchestrator/main.py`
- Create: `services/orchestrator/tests/test_providers_ollama.py`
- Delete: `services/orchestrator/orchestrator/providers/local.py` (after callers migrated)
- Delete: `services/orchestrator/tests/test_providers_local.py` (if exists)

`OllamaProvider` POSTs to `<OLLAMA_URL>/v1/chat/completions` (OpenAI-compatible). Critical difference from the old `LocalLlamaProvider`: Ollama REQUIRES a `model` field in the request. The provider takes a `model` at construction time and includes it in every request.

- [ ] **Step 1: Write the failing tests**

Create `services/orchestrator/tests/test_providers_ollama.py`:

```python
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
    # Expect token(s) + FinalDoneEvent
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
```

- [ ] **Step 2: Add `respx` to test deps (if not present)**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/services/orchestrator
source .venv/bin/activate
grep -E "respx" requirements.txt pyproject.toml 2>/dev/null
```

If `respx` isn't there:

```bash
echo "respx>=0.21,<0.22" >> requirements.txt
pip install "respx>=0.21,<0.22"
```

- [ ] **Step 3: Run the failing tests**

```bash
pytest tests/test_providers_ollama.py -v 2>&1 | tail -15
```

Expected: tests FAIL with `ModuleNotFoundError: No module named 'orchestrator.providers.ollama'`.

- [ ] **Step 4: Write `services/orchestrator/orchestrator/providers/ollama.py`**

```python
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
    """OpenAI-compatible chat client for Ollama."""

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
                    f"{self._base_url}/v1/chat/completions",
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
                    f"{self._base_url}/v1/chat/completions",
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
                        # Token content
                        content = delta.get("content")
                        if content:
                            yield TokenEvent(delta=content)
                        # Tool calls accumulate across delta chunks
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
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/test_providers_ollama.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 6: Update `services/orchestrator/orchestrator/config.py`**

Replace the `llama_url` field with `ollama_url`:

```python
    ollama_url: str = "http://host.docker.internal:11434"
```

Place it where `llama_url` was. Same default port (11434) regardless of platform — `host.docker.internal` resolves via Docker Desktop on Mac/Windows, and via the `extra_hosts` entry on Linux.

- [ ] **Step 7: Update `services/orchestrator/orchestrator/providers/__init__.py`**

Replace the `LocalLlamaProvider` import + export with `OllamaProvider`:

```python
from orchestrator.providers.ollama import OllamaProvider
```

and update `__all__`:

```python
__all__ = ["Provider", "OllamaProvider", "LiteLLMProvider", "pick_provider"]
```

Leave the `pick_provider` function for now — Task 7 replaces it with the dispatcher.

- [ ] **Step 8: Update `services/orchestrator/orchestrator/main.py`**

Find this block in `create_app`:

```python
    app.state.local_provider = LocalLlamaProvider(
        base_url=settings.llama_url, timeout=settings.request_timeout
    )
```

Replace with:

```python
    # Plan #7: default Ollama provider with the default brain from catalog.
    # Per-request dispatch (Task 7) overrides this based on state.brain.
    app.state.local_provider = OllamaProvider(
        base_url=settings.ollama_url,
        model="qwen3:4b",  # default; dispatcher chooses per-request in Task 7
        timeout=settings.request_timeout,
    )
```

And replace the import line at the top of `main.py`:

```python
from orchestrator.providers.local import LocalLlamaProvider
```

with:

```python
from orchestrator.providers.ollama import OllamaProvider
```

- [ ] **Step 9: Delete legacy files**

```bash
git rm services/orchestrator/orchestrator/providers/local.py
git rm services/orchestrator/tests/test_providers_local.py 2>/dev/null || true
```

If `test_providers_local.py` doesn't exist, ignore the error.

- [ ] **Step 10: Run the full test suite**

```bash
pytest tests/ 2>&1 | tail -5
```

Expected: green. Any test that referenced `LocalLlamaProvider` or `llama_url` needs to be updated to use `OllamaProvider` and `ollama_url`. If a test fails on import, update the import; on the URL field, update the field name.

- [ ] **Step 11: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add services/orchestrator/
git commit -m "feat(orch): OllamaProvider replaces LocalLlamaProvider"
```

---

## Task 4: Catalog file + parser

**Files:**
- Create: `configs/catalog.yml`
- Create: `services/orchestrator/orchestrator/catalog.py`
- Create: `services/orchestrator/tests/test_catalog.py`
- Modify: `services/orchestrator/requirements.txt`

The catalog drives every swap. Load it once at startup, validate per-kind, expose accessors.

- [ ] **Step 1: Add pyyaml to orchestrator requirements**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
grep -E "pyyaml" services/orchestrator/requirements.txt || echo "pyyaml>=6.0,<7.0" >> services/orchestrator/requirements.txt
cd services/orchestrator && source .venv/bin/activate && pip install -q "pyyaml>=6.0,<7.0"
```

- [ ] **Step 2: Create `configs/catalog.yml`**

```bash
mkdir -p /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/configs
```

Write `configs/catalog.yml`:

```yaml
brains:
  - id: qwen3-4b
    label: "Qwen3 4B (default local)"
    kind: ollama
    model: qwen3:4b
    default: true
  - id: smollm2-360m
    label: "SmolLM2 360M (tiny / dumb)"
    kind: ollama
    model: smollm2:360m
  - id: qwen3-7b
    label: "Qwen3 7B (larger; Ollama may offload to CPU on small GPUs)"
    kind: ollama
    model: qwen3:7b
  - id: claude-sonnet
    label: "Claude Sonnet 4.6 (cloud)"
    kind: cloud-litellm
    model: anthropic/claude-sonnet-4-6
    requires_key: ANTHROPIC_API_KEY
  - id: openai-gpt-4o
    label: "OpenAI GPT-4o (cloud)"
    kind: cloud-litellm
    model: openai/gpt-4o
    requires_key: OPENAI_API_KEY
  - id: groq-llama
    label: "Groq Llama-3.3-70B (cloud, fast)"
    kind: cloud-litellm
    model: groq/llama-3.3-70b-versatile
    requires_key: GROQ_API_KEY

voices:
  - id: bella
    label: "Bella (warm, conversational)"
    kokoro_voice: af_bella
    default: true
  - id: nova
    label: "Nova (clear, neutral)"
    kokoro_voice: af_nova
  - id: fenrir
    label: "Fenrir (deep, authoritative)"
    kokoro_voice: am_fenrir
  - id: emma
    label: "Emma (warm UK female)"
    kokoro_voice: bf_emma
  - id: george
    label: "George (warm UK male)"
    kokoro_voice: bm_george

avatars:
  - id: ava
    label: "Ava (default)"
    glb_path: /avatars/default-avatar.glb
    default: true

personalities:
  - id: default
    label: "Helpful Assistant (NodeAva-aware)"
    default: true
    system_prompt: |
      You are NodeAva, a helpful digital assistant. Be concise. When you
      don't know something, say so.

      When the user asks about NodeAva itself — its architecture, ports,
      models, components, configuration, or any project-specific detail —
      you MUST call wiki.list or wiki.search BEFORE answering. Do not
      answer NodeAva questions from training data; the wiki is the source
      of truth.

      When the user asks about current events, current time, news, or
      anything requiring fresh information, call browser.search BEFORE
      answering. Do not invent or guess time-sensitive information.
  - id: dry-historian
    label: "Dry Historian"
    system_prompt: |
      You are a deeply knowledgeable historian with a dry, deadpan wit.
      You enjoy correcting popular misconceptions. Keep responses tight.

      For NodeAva-specific questions, call wiki.list or wiki.search FIRST.
      For current events, call browser.search FIRST.
  - id: improv-comic
    label: "Improv Comic"
    system_prompt: |
      You are a quick-witted improv performer. Yes-and everything. Keep
      responses short and playful.

      For NodeAva-specific questions, call wiki.list or wiki.search FIRST.
      For current events, call browser.search FIRST.
  - id: tutor
    label: "Patient Tutor"
    system_prompt: |
      You are a patient tutor. Break ideas into small steps. Ask Socratic
      follow-up questions when a concept isn't clear.

      For NodeAva-specific questions, call wiki.list or wiki.search FIRST.
      For current events, call browser.search FIRST.
```

- [ ] **Step 3: Write the failing tests**

Create `services/orchestrator/tests/test_catalog.py`:

```python
"""Tests for the catalog loader."""
import textwrap
from pathlib import Path

import pytest

from orchestrator.catalog import Catalog, CatalogError, load_catalog


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "catalog.yml"
    p.write_text(textwrap.dedent(content))
    return p


def test_load_valid_catalog(tmp_path):
    path = _write(tmp_path, """
        brains:
          - id: qwen3-4b
            label: Q
            kind: ollama
            model: qwen3:4b
            default: true
        voices:
          - id: bella
            label: B
            kokoro_voice: af_bella
            default: true
        avatars:
          - id: ava
            label: A
            glb_path: /avatars/a.glb
            default: true
        personalities:
          - id: default
            label: D
            system_prompt: hi
            default: true
    """)
    c = load_catalog(path)
    assert isinstance(c, Catalog)
    assert c.brain("qwen3-4b").model == "qwen3:4b"


def test_default_brain_is_resolved(tmp_path):
    path = _write(tmp_path, """
        brains:
          - id: foo
            label: F
            kind: ollama
            model: foo:1b
            default: true
          - id: bar
            label: B
            kind: ollama
            model: bar:1b
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    c = load_catalog(path)
    assert c.default_brain().id == "foo"


def test_missing_default_in_a_section_raises(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: ollama, model: a:1b}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "default" in str(exc.value).lower()
    assert "brain" in str(exc.value).lower()


def test_unknown_brain_kind_raises(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: weird, model: a:1b, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "kind" in str(exc.value).lower()


def test_cloud_litellm_requires_requires_key(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: cloud-litellm, model: a/b, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "requires_key" in str(exc.value)


def test_openai_compatible_requires_url(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: openai-compatible, model: a, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "url" in str(exc.value).lower()


def test_lookup_unknown_id_raises(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: qwen, label: Q, kind: ollama, model: qwen:1b, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    c = load_catalog(path)
    with pytest.raises(CatalogError):
        c.brain("missing")
```

- [ ] **Step 4: Run tests — verify they fail**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/services/orchestrator
source .venv/bin/activate
pytest tests/test_catalog.py -v 2>&1 | tail -10
```

Expected: ImportError / ModuleNotFoundError for `orchestrator.catalog`.

- [ ] **Step 5: Write `services/orchestrator/orchestrator/catalog.py`**

```python
"""Catalog — single source of truth for swappable brains / voices / avatars
/ personalities. Parsed once from configs/catalog.yml at orchestrator startup.

Validation is strict: missing fields, unknown kinds, or no `default: true` in
a section all raise CatalogError at startup. The catalog is foundational; we
want fail-fast, not silent fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CatalogError(Exception):
    """Raised on any catalog-validation problem."""


_VALID_BRAIN_KINDS = {"ollama", "cloud-litellm", "openai-compatible"}


@dataclass
class BrainEntry:
    id: str
    label: str
    kind: str  # one of _VALID_BRAIN_KINDS
    model: str
    default: bool = False
    requires_key: str | None = None  # cloud-litellm only
    url: str | None = None  # openai-compatible only


@dataclass
class VoiceEntry:
    id: str
    label: str
    kokoro_voice: str
    default: bool = False


@dataclass
class AvatarEntry:
    id: str
    label: str
    glb_path: str
    default: bool = False


@dataclass
class PersonalityEntry:
    id: str
    label: str
    system_prompt: str
    default: bool = False


@dataclass
class Catalog:
    brains: list[BrainEntry] = field(default_factory=list)
    voices: list[VoiceEntry] = field(default_factory=list)
    avatars: list[AvatarEntry] = field(default_factory=list)
    personalities: list[PersonalityEntry] = field(default_factory=list)

    # Lookup helpers — raise CatalogError on unknown id.
    def brain(self, id_: str) -> BrainEntry:
        return _get_or_raise(self.brains, id_, "brain")

    def voice(self, id_: str) -> VoiceEntry:
        return _get_or_raise(self.voices, id_, "voice")

    def avatar(self, id_: str) -> AvatarEntry:
        return _get_or_raise(self.avatars, id_, "avatar")

    def personality(self, id_: str) -> PersonalityEntry:
        return _get_or_raise(self.personalities, id_, "personality")

    def default_brain(self) -> BrainEntry:
        return _default_or_raise(self.brains, "brain")

    def default_voice(self) -> VoiceEntry:
        return _default_or_raise(self.voices, "voice")

    def default_avatar(self) -> AvatarEntry:
        return _default_or_raise(self.avatars, "avatar")

    def default_personality(self) -> PersonalityEntry:
        return _default_or_raise(self.personalities, "personality")


def _get_or_raise(items, id_: str, label: str):
    for item in items:
        if item.id == id_:
            return item
    raise CatalogError(f"no {label} with id '{id_}'")


def _default_or_raise(items, label: str):
    for item in items:
        if item.default:
            return item
    raise CatalogError(f"no default {label} (one entry must set default: true)")


def load_catalog(path: Path | str) -> Catalog:
    """Read + validate the catalog YAML; return a Catalog object.

    Raises CatalogError on any structural problem.
    """
    p = Path(path)
    if not p.is_file():
        raise CatalogError(f"catalog not found: {p}")

    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        raise CatalogError(f"catalog YAML parse error: {e}") from e

    if not isinstance(data, dict):
        raise CatalogError("catalog root must be a mapping")

    brains = [_parse_brain(b) for b in (data.get("brains") or [])]
    voices = [_parse_voice(v) for v in (data.get("voices") or [])]
    avatars = [_parse_avatar(a) for a in (data.get("avatars") or [])]
    personalities = [_parse_personality(p_) for p_ in (data.get("personalities") or [])]

    cat = Catalog(brains=brains, voices=voices, avatars=avatars, personalities=personalities)
    # Validate every section has exactly one default
    cat.default_brain()
    cat.default_voice()
    cat.default_avatar()
    cat.default_personality()
    return cat


def _require(d: dict, key: str, section: str) -> Any:
    if key not in d or d[key] in (None, ""):
        raise CatalogError(f"{section} entry missing '{key}': {d!r}")
    return d[key]


def _parse_brain(d: dict) -> BrainEntry:
    id_ = _require(d, "id", "brains")
    label = _require(d, "label", "brains")
    kind = _require(d, "kind", "brains")
    model = _require(d, "model", "brains")
    if kind not in _VALID_BRAIN_KINDS:
        raise CatalogError(
            f"brain '{id_}' has unknown kind '{kind}' "
            f"(valid: {sorted(_VALID_BRAIN_KINDS)})"
        )
    requires_key = d.get("requires_key")
    url = d.get("url")
    if kind == "cloud-litellm" and not requires_key:
        raise CatalogError(
            f"brain '{id_}' kind=cloud-litellm requires 'requires_key' field"
        )
    if kind == "openai-compatible" and not url:
        raise CatalogError(
            f"brain '{id_}' kind=openai-compatible requires 'url' field"
        )
    return BrainEntry(
        id=id_, label=label, kind=kind, model=model,
        default=bool(d.get("default", False)),
        requires_key=requires_key, url=url,
    )


def _parse_voice(d: dict) -> VoiceEntry:
    return VoiceEntry(
        id=_require(d, "id", "voices"),
        label=_require(d, "label", "voices"),
        kokoro_voice=_require(d, "kokoro_voice", "voices"),
        default=bool(d.get("default", False)),
    )


def _parse_avatar(d: dict) -> AvatarEntry:
    return AvatarEntry(
        id=_require(d, "id", "avatars"),
        label=_require(d, "label", "avatars"),
        glb_path=_require(d, "glb_path", "avatars"),
        default=bool(d.get("default", False)),
    )


def _parse_personality(d: dict) -> PersonalityEntry:
    return PersonalityEntry(
        id=_require(d, "id", "personalities"),
        label=_require(d, "label", "personalities"),
        system_prompt=_require(d, "system_prompt", "personalities"),
        default=bool(d.get("default", False)),
    )
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
pytest tests/test_catalog.py -v 2>&1 | tail -10
```

Expected: 7 passed.

- [ ] **Step 7: Smoke-test loading the real catalog**

```bash
python -c "
from orchestrator.catalog import load_catalog
c = load_catalog('../../configs/catalog.yml')
print(f'brains={len(c.brains)} voices={len(c.voices)} avatars={len(c.avatars)} personalities={len(c.personalities)}')
print(f'default brain: {c.default_brain().id}')
print(f'default voice: {c.default_voice().id}')
"
```

Expected: prints counts (6/5/1/4) and `default brain: qwen3-4b`, `default voice: bella`.

- [ ] **Step 8: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add configs/catalog.yml services/orchestrator/
git commit -m "feat(orch): catalog.yml + parser with strict validation"
```

---

## Task 5: State file + atomic R/W

**Files:**
- Create: `services/orchestrator/orchestrator/state.py`
- Create: `services/orchestrator/tests/test_state.py`

State holds what's currently active. Reads from in-memory cache; writes go to disk atomically and update the cache.

- [ ] **Step 1: Write the failing tests**

Create `services/orchestrator/tests/test_state.py`:

```python
"""Tests for state.py — atomic read/write of state/current.json."""
import json
from pathlib import Path

import pytest

from orchestrator.catalog import Catalog, AvatarEntry, BrainEntry, PersonalityEntry, VoiceEntry
from orchestrator.state import StateStore


def _make_catalog() -> Catalog:
    return Catalog(
        brains=[
            BrainEntry(id="qwen3-4b", label="Q", kind="ollama", model="qwen3:4b", default=True),
            BrainEntry(id="smollm2-360m", label="S", kind="ollama", model="smollm2:360m"),
        ],
        voices=[
            VoiceEntry(id="bella", label="B", kokoro_voice="af_bella", default=True),
            VoiceEntry(id="nova", label="N", kokoro_voice="af_nova"),
        ],
        avatars=[AvatarEntry(id="ava", label="A", glb_path="/x.glb", default=True)],
        personalities=[
            PersonalityEntry(id="default", label="D", system_prompt="x", default=True),
            PersonalityEntry(id="tutor", label="T", system_prompt="t"),
        ],
    )


def test_get_state_returns_defaults_when_file_missing(tmp_path):
    s = StateStore(path=tmp_path / "state.json", catalog=_make_catalog())
    state = s.get_state()
    assert state["brain"] == "qwen3-4b"
    assert state["voice"] == "bella"
    assert state["avatar"] == "ava"
    assert state["personality"] == "default"
    assert state["tools"] == {"web_search": False, "wiki": True}


def test_get_state_loads_from_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "brain": "smollm2-360m",
        "voice": "nova",
        "avatar": "ava",
        "personality": "tutor",
        "tools": {"web_search": True, "wiki": False},
    }))
    s = StateStore(path=path, catalog=_make_catalog())
    state = s.get_state()
    assert state["brain"] == "smollm2-360m"
    assert state["voice"] == "nova"
    assert state["personality"] == "tutor"
    assert state["tools"]["web_search"] is True


def test_set_state_writes_atomically(tmp_path):
    path = tmp_path / "state.json"
    s = StateStore(path=path, catalog=_make_catalog())
    new_state = s.set_state("brain", "smollm2-360m")
    assert new_state["brain"] == "smollm2-360m"
    # File should now exist with the new value
    on_disk = json.loads(path.read_text())
    assert on_disk["brain"] == "smollm2-360m"


def test_set_tool_uses_value_param(tmp_path):
    path = tmp_path / "state.json"
    s = StateStore(path=path, catalog=_make_catalog())
    new_state = s.set_tool("web_search", True)
    assert new_state["tools"]["web_search"] is True
    assert new_state["tools"]["wiki"] is True  # default preserved


def test_invalid_id_falls_back_to_default_on_load(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "brain": "deleted-from-catalog",
        "voice": "bella", "avatar": "ava", "personality": "default",
        "tools": {"web_search": False, "wiki": True},
    }))
    s = StateStore(path=path, catalog=_make_catalog())
    state = s.get_state()
    # Falls back to default brain because the stored id doesn't exist
    assert state["brain"] == "qwen3-4b"


def test_set_state_unknown_kind_raises(tmp_path):
    s = StateStore(path=tmp_path / "state.json", catalog=_make_catalog())
    with pytest.raises(ValueError):
        s.set_state("not-a-kind", "qwen3-4b")


def test_set_state_unknown_id_raises(tmp_path):
    s = StateStore(path=tmp_path / "state.json", catalog=_make_catalog())
    with pytest.raises(ValueError) as exc:
        s.set_state("brain", "no-such-brain")
    assert "no-such-brain" in str(exc.value)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_state.py -v 2>&1 | tail -10
```

Expected: import error for `orchestrator.state`.

- [ ] **Step 3: Write `services/orchestrator/orchestrator/state.py`**

```python
"""State store — read/write the active selections (brain/voice/avatar/personality/tools).

Single user, single dashboard, single laptop. No locks. Atomic write
(tempfile + rename) guarantees concurrent reads see either the old or new
file, never a half-written one.

Invalid ids (e.g. the catalog removed an entry while state.json still
references it) fall back to the catalog default on load. set_state validates
the target id against the catalog and refuses unknown values.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from orchestrator.catalog import Catalog

log = logging.getLogger("orchestrator.state")

# Tool keys we know about. Stored as a fixed dict so the dashboard has a
# stable shape. Adding a new tool later means adding a default here.
_DEFAULT_TOOLS = {"web_search": False, "wiki": True}

# Valid swap kinds for `set_state(kind, id)`.
_VALID_KINDS = {"brain", "voice", "avatar", "personality"}


class StateStore:
    def __init__(self, *, path: Path | str, catalog: Catalog) -> None:
        self._path = Path(path)
        self._catalog = catalog
        self._cache: dict[str, Any] | None = None

    def get_state(self) -> dict[str, Any]:
        """Return the current state dict. Loads from disk on first call;
        cached in memory afterward."""
        if self._cache is None:
            self._cache = self._load_or_default()
        # Return a copy so callers can't mutate the cache directly.
        return dict(self._cache, tools=dict(self._cache["tools"]))

    def set_state(self, kind: str, id_: str) -> dict[str, Any]:
        """Update one of brain/voice/avatar/personality. Returns the new state."""
        if kind not in _VALID_KINDS:
            raise ValueError(f"unknown kind '{kind}' (valid: {sorted(_VALID_KINDS)})")
        # Validate id exists in the catalog
        lookup = {
            "brain": self._catalog.brain,
            "voice": self._catalog.voice,
            "avatar": self._catalog.avatar,
            "personality": self._catalog.personality,
        }[kind]
        lookup(id_)  # raises CatalogError if missing
        state = self.get_state()
        state[kind] = id_
        self._write(state)
        return state

    def set_tool(self, name: str, value: bool) -> dict[str, Any]:
        """Update one tool toggle. Returns the new state."""
        if name not in _DEFAULT_TOOLS:
            raise ValueError(f"unknown tool '{name}' (valid: {sorted(_DEFAULT_TOOLS)})")
        if not isinstance(value, bool):
            raise ValueError(f"tool '{name}' value must be a bool, got {type(value).__name__}")
        state = self.get_state()
        state["tools"][name] = value
        self._write(state)
        return state

    # --- internals ---

    def _defaults(self) -> dict[str, Any]:
        return {
            "brain": self._catalog.default_brain().id,
            "voice": self._catalog.default_voice().id,
            "avatar": self._catalog.default_avatar().id,
            "personality": self._catalog.default_personality().id,
            "tools": dict(_DEFAULT_TOOLS),
        }

    def _load_or_default(self) -> dict[str, Any]:
        if not self._path.is_file():
            log.info("state file %s missing; using catalog defaults", self._path)
            return self._defaults()
        try:
            on_disk = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("state file %s unreadable (%s); using defaults", self._path, e)
            return self._defaults()
        # Patch missing/invalid ids back to defaults
        defaults = self._defaults()
        patched: dict[str, Any] = {}
        for kind in ("brain", "voice", "avatar", "personality"):
            stored = on_disk.get(kind)
            try:
                lookup = {
                    "brain": self._catalog.brain,
                    "voice": self._catalog.voice,
                    "avatar": self._catalog.avatar,
                    "personality": self._catalog.personality,
                }[kind]
                if stored:
                    lookup(stored)
                    patched[kind] = stored
                else:
                    patched[kind] = defaults[kind]
            except Exception:
                log.warning(
                    "state %s='%s' not in catalog; falling back to default '%s'",
                    kind, stored, defaults[kind],
                )
                patched[kind] = defaults[kind]
        # Tools: merge stored over defaults, drop unknown keys
        stored_tools = on_disk.get("tools") or {}
        patched["tools"] = {
            k: bool(stored_tools.get(k, defaults["tools"][k]))
            for k in _DEFAULT_TOOLS
        }
        return patched

    def _write(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: tempfile in the same directory, then rename.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".state-", suffix=".tmp", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        # Update cache to match what's on disk
        self._cache = dict(state, tools=dict(state["tools"]))
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_state.py -v 2>&1 | tail -10
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add services/orchestrator/
git commit -m "feat(orch): state.py with atomic R/W + catalog-validated defaults"
```

---

## Task 6: System / residency module

**Files:**
- Create: `services/orchestrator/orchestrator/system/__init__.py`
- Create: `services/orchestrator/orchestrator/system/residency.py`
- Create: `services/orchestrator/tests/test_system_residency.py`

Residency queries Ollama's `/api/ps` and labels each loaded model `gpu` / `split` / `cpu`. Single data source — no native GPU probes.

- [ ] **Step 1: Create the package marker**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
mkdir -p services/orchestrator/orchestrator/system
echo '"""Plan #7: system-introspection helpers (Ollama residency)."""' > services/orchestrator/orchestrator/system/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `services/orchestrator/tests/test_system_residency.py`:

```python
"""Tests for orchestrator.system.residency."""
import httpx
import pytest
import respx

from orchestrator.system.residency import OllamaResidency, residency_label


def test_residency_label_gpu():
    assert residency_label(size_bytes=1000, size_vram_bytes=1000) == "gpu"


def test_residency_label_split():
    assert residency_label(size_bytes=1000, size_vram_bytes=400) == "split"


def test_residency_label_cpu():
    assert residency_label(size_bytes=1000, size_vram_bytes=0) == "cpu"


def test_residency_label_size_zero_returns_cpu():
    # Edge case — undefined behavior; report cpu rather than crash
    assert residency_label(size_bytes=0, size_vram_bytes=0) == "cpu"


@respx.mock
async def test_query_returns_normalized_loaded_models():
    respx.get("http://test-ollama:11434/api/ps").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:4b", "size": 1000, "size_vram": 1000},
                    {"name": "qwen3:7b", "size": 4000, "size_vram": 2500},
                ]
            },
        )
    )
    r = OllamaResidency(base_url="http://test-ollama:11434")
    result = await r.query()
    assert result["reachable"] is True
    assert len(result["loaded"]) == 2
    assert result["loaded"][0]["residency"] == "gpu"
    assert result["loaded"][1]["residency"] == "split"


@respx.mock
async def test_query_unreachable_returns_empty():
    respx.get("http://test-ollama:11434/api/ps").mock(
        side_effect=httpx.ConnectError("nope")
    )
    r = OllamaResidency(base_url="http://test-ollama:11434")
    result = await r.query()
    assert result["reachable"] is False
    assert result["loaded"] == []


@respx.mock
async def test_query_http_error_returns_empty():
    respx.get("http://test-ollama:11434/api/ps").mock(
        return_value=httpx.Response(500, text="boom")
    )
    r = OllamaResidency(base_url="http://test-ollama:11434")
    result = await r.query()
    assert result["reachable"] is False
    assert result["loaded"] == []
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/test_system_residency.py -v 2>&1 | tail -10
```

Expected: import error for `orchestrator.system.residency`.

- [ ] **Step 4: Write `services/orchestrator/orchestrator/system/residency.py`**

```python
"""Ollama residency probe — single source of truth for what's in VRAM right now.

Queries Ollama's GET /api/ps. Output is normalized into a dict that the
dashboard can render directly. No native GPU libraries; Ollama is canonical.
"""
import logging
from typing import Any

import httpx

log = logging.getLogger("orchestrator.system.residency")


def residency_label(*, size_bytes: int, size_vram_bytes: int) -> str:
    """Categorize a model's memory residency.

    - 'gpu'   : fully in VRAM (size_vram == size)
    - 'split' : partially in VRAM (0 < size_vram < size)
    - 'cpu'   : fully in system memory (size_vram == 0, including edge size==0)
    """
    if size_bytes <= 0 or size_vram_bytes <= 0:
        return "cpu"
    if size_vram_bytes >= size_bytes:
        return "gpu"
    return "split"


class OllamaResidency:
    def __init__(self, *, base_url: str, timeout: float = 1.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def query(self) -> dict[str, Any]:
        """Return {reachable: bool, loaded: [...]}. Never raises."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/api/ps")
                if resp.status_code >= 400:
                    log.warning("ollama /api/ps HTTP %d", resp.status_code)
                    return {"reachable": False, "loaded": []}
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.info("ollama /api/ps unreachable: %s", e)
            return {"reachable": False, "loaded": []}

        loaded = []
        for m in (data.get("models") or []):
            size_bytes = int(m.get("size") or 0)
            size_vram_bytes = int(m.get("size_vram") or 0)
            loaded.append({
                "model": m.get("name") or m.get("model") or "",
                "size_bytes": size_bytes,
                "size_vram_bytes": size_vram_bytes,
                "residency": residency_label(
                    size_bytes=size_bytes,
                    size_vram_bytes=size_vram_bytes,
                ),
            })
        return {"reachable": True, "loaded": loaded}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/test_system_residency.py -v 2>&1 | tail -10
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add services/orchestrator/
git commit -m "feat(orch): system.residency.OllamaResidency (gpu/split/cpu labels)"
```

---

## Task 7: Provider dispatcher

**Files:**
- Create: `services/orchestrator/orchestrator/providers/dispatcher.py`
- Modify: `services/orchestrator/orchestrator/providers/__init__.py`
- Modify: `services/orchestrator/orchestrator/routes/chat.py`
- Create: `services/orchestrator/tests/test_providers_dispatcher.py`

The dispatcher reads `state.brain` and returns the right Provider instance. Used by `chat.py` per request, replacing the old `pick_provider`.

- [ ] **Step 1: Write the failing tests**

Create `services/orchestrator/tests/test_providers_dispatcher.py`:

```python
"""Tests for orchestrator.providers.dispatcher."""
import pytest

from orchestrator.catalog import BrainEntry
from orchestrator.providers.dispatcher import dispatch_for_brain
from orchestrator.providers.ollama import OllamaProvider
from orchestrator.providers.litellm_provider import LiteLLMProvider


def test_dispatch_ollama_brain_returns_ollama_provider():
    brain = BrainEntry(id="q", label="Q", kind="ollama", model="qwen3:4b")
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
    assert isinstance(p, OllamaProvider)


def test_dispatch_cloud_litellm_requires_api_key():
    brain = BrainEntry(
        id="c", label="C", kind="cloud-litellm",
        model="anthropic/claude-3", requires_key="ANTHROPIC_API_KEY",
    )
    # No key → returns a fail-stub provider that yields ErrorEvent
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
    # The fail-stub is an internal class; verify by attribute, not type
    assert hasattr(p, "_missing_key_brain_id")


def test_dispatch_cloud_litellm_with_key_returns_litellm():
    brain = BrainEntry(
        id="c", label="C", kind="cloud-litellm",
        model="anthropic/claude-3", requires_key="ANTHROPIC_API_KEY",
    )
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key="sk-x")
    assert isinstance(p, LiteLLMProvider)


def test_dispatch_openai_compatible_returns_ollama_shaped_provider():
    """openai-compatible reuses OllamaProvider since the wire format is the same."""
    brain = BrainEntry(
        id="ex", label="EX", kind="openai-compatible",
        model="some-model", url="http://my-llama:8081/v1",
    )
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
    assert isinstance(p, OllamaProvider)
    # The base url should be the brain's url, not the Ollama default
    assert p._base_url == "http://my-llama:8081/v1"


def test_dispatch_unknown_kind_raises():
    brain = BrainEntry(id="?", label="?", kind="weird", model="x")
    with pytest.raises(ValueError):
        dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_providers_dispatcher.py -v 2>&1 | tail -10
```

Expected: import error for `orchestrator.providers.dispatcher`.

- [ ] **Step 3: Write `services/orchestrator/orchestrator/providers/dispatcher.py`**

```python
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
    """Construct a Provider for this brain.

    - kind=ollama          → OllamaProvider(ollama_url, model=brain.model)
    - kind=cloud-litellm   → LiteLLMProvider(model=brain.model, api_key=...) if key present, else stub
    - kind=openai-compatible → OllamaProvider(brain.url, model=brain.model)
                              (same wire format; different base URL)
    """
    if brain.kind == "ollama":
        return OllamaProvider(
            base_url=ollama_url, model=brain.model, timeout=request_timeout,
        )
    if brain.kind == "openai-compatible":
        # Same OpenAI-compatible API; just a different URL
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_providers_dispatcher.py -v 2>&1 | tail -10
```

Expected: 5 passed.

- [ ] **Step 5: Update `services/orchestrator/orchestrator/providers/__init__.py`**

Add the new dispatcher export at the top alongside existing imports:

```python
from orchestrator.providers.dispatcher import dispatch_for_brain
```

Add to `__all__`:

```python
__all__ = ["Provider", "OllamaProvider", "LiteLLMProvider", "pick_provider", "dispatch_for_brain"]
```

Keep `pick_provider` for backwards compatibility for now — it's still used by tests; Task 7's chat-route changes use the new `dispatch_for_brain` instead.

- [ ] **Step 6: Update `services/orchestrator/orchestrator/routes/chat.py` — inject system prompt + use dispatcher**

Read the file first:

```bash
sed -n '50,90p' services/orchestrator/orchestrator/routes/chat.py
```

Find this block:

```python
    web_search = bool(body.pop("web_search", False))
    wiki = bool(body.pop("wiki", False))
    messages = body.get("messages") or []
    stream = bool(body.get("stream", False))

    provider = pick_provider(request, body)
    # provider was the last consumer of body["provider"]; now strip it.
    body.pop("provider", None)

    enabled_tools = _resolve_enabled_tools(web_search=web_search, wiki=wiki)
```

Replace it with:

```python
    # Plan #7: tool toggles + brain selection live in server-side state now.
    # Body fields (web_search, wiki, provider, model) are accepted for backwards
    # compatibility but ignored — state is canonical.
    body.pop("web_search", None)
    body.pop("wiki", None)
    body.pop("provider", None)
    body.pop("model", None)

    state_store = request.app.state.state_store
    catalog = request.app.state.catalog
    state = state_store.get_state()

    # Brain selection from state
    brain = catalog.brain(state["brain"])
    api_key = (
        request.headers.get("X-Provider-Key")
        or request.headers.get("x-provider-key")
        or os.environ.get(brain.requires_key, "") if brain.requires_key else ""
    )
    provider = dispatch_for_brain(
        brain,
        ollama_url=request.app.state.settings.ollama_url,
        request_timeout=request.app.state.settings.request_timeout,
        api_key=api_key or None,
    )

    # Personality system prompt at request time
    personality = catalog.personality(state["personality"])
    messages = body.get("messages") or []
    # If the messages list already starts with a system role, leave it.
    # Otherwise inject the personality system_prompt.
    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": personality.system_prompt}] + list(messages)

    stream = bool(body.get("stream", False))

    # Tool selection from state.tools
    enabled_tools = _resolve_enabled_tools(
        web_search=bool(state["tools"].get("web_search")),
        wiki=bool(state["tools"].get("wiki")),
    )
```

Also add at the top of the file:

```python
import os
from orchestrator.providers.dispatcher import dispatch_for_brain
```

- [ ] **Step 7: Run the full test suite**

```bash
pytest tests/ 2>&1 | tail -10
```

Some chat-route tests will fail because they don't set up `app.state.state_store` / `app.state.catalog`. Fix them in the next step.

- [ ] **Step 8: Update existing chat tests to provide catalog + state on app.state**

Find existing chat tests:

```bash
grep -l "create_app\|chat" tests/test_routes_chat*.py 2>/dev/null
```

For each test that creates the app, ensure the test fixture sets up the catalog + state. The cleanest fix is in `tests/conftest.py` — add a fixture that monkey-patches the catalog + state stores onto `app.state` after `create_app()`. If `conftest.py` already has an `app_client` fixture that calls `create_app`, modify it to:

```python
from orchestrator.catalog import load_catalog
from orchestrator.state import StateStore

# ... inside the fixture that creates the app:
catalog = load_catalog("../../configs/catalog.yml")  # repo-root relative
app.state.catalog = catalog
app.state.state_store = StateStore(path="/tmp/test-state.json", catalog=catalog)
```

If `conftest.py` doesn't exist or the fixture name is different, READ it and adapt.

- [ ] **Step 9: Run the full test suite again**

```bash
pytest tests/ 2>&1 | tail -10
```

Expected: green. Fix any remaining failures.

- [ ] **Step 10: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add services/orchestrator/
git commit -m "feat(orch): per-request provider dispatch + personality system prompt"
```

---

## Task 8: Wire catalog + state into the app + new routes

**Files:**
- Create: `services/orchestrator/orchestrator/routes/catalog.py`
- Create: `services/orchestrator/orchestrator/routes/state.py`
- Create: `services/orchestrator/orchestrator/routes/swap.py`
- Modify: `services/orchestrator/orchestrator/main.py`
- Create: `services/orchestrator/tests/test_routes_catalog.py`
- Create: `services/orchestrator/tests/test_routes_state.py`
- Create: `services/orchestrator/tests/test_routes_swap.py`

- [ ] **Step 1: Update `services/orchestrator/orchestrator/main.py`**

At the top of the file, add imports:

```python
from pathlib import Path

from orchestrator.catalog import load_catalog
from orchestrator.state import StateStore
from orchestrator.system.residency import OllamaResidency
from orchestrator.routes import catalog as catalog_route
from orchestrator.routes import state as state_route
from orchestrator.routes import swap as swap_route
```

Inside `create_app(settings)`, after `app.state.settings = settings`, before the registration of routers, add:

```python
    # Plan #7: load catalog + state, attach to app.state for routes to read.
    repo_root = Path(__file__).resolve().parents[3]
    catalog_path = repo_root / "configs" / "catalog.yml"
    state_path = repo_root / "state" / "current.json"
    app.state.catalog = load_catalog(catalog_path)
    app.state.state_store = StateStore(path=state_path, catalog=app.state.catalog)
    app.state.residency = OllamaResidency(base_url=settings.ollama_url)
```

Inside the same function, after the existing `app.include_router(...)` calls, add:

```python
    app.include_router(catalog_route.router)
    app.include_router(state_route.router)
    app.include_router(swap_route.router)
```

- [ ] **Step 2: Write `services/orchestrator/orchestrator/routes/catalog.py`**

```python
"""GET /v1/catalog — full catalog with availability annotations.

Availability is computed per-request, not cached:
- kind=ollama          → Ollama /api/tags includes brain.model
- kind=cloud-litellm   → os.environ[brain.requires_key] is set
- kind=openai-compatible → TCP check on brain.url (HEAD request)
- Avatars              → file at glb_path exists on disk
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Request

log = logging.getLogger("orchestrator.routes.catalog")
router = APIRouter()


@router.get("/v1/catalog")
async def get_catalog(request: Request) -> dict:
    catalog = request.app.state.catalog
    settings = request.app.state.settings
    ollama_tags = await _fetch_ollama_tags(settings.ollama_url)

    brains_out = []
    for b in catalog.brains:
        entry = {
            "id": b.id, "label": b.label, "kind": b.kind, "model": b.model,
            "default": b.default,
        }
        if b.requires_key:
            entry["requires_key"] = b.requires_key
        if b.url:
            entry["url"] = b.url
        entry.update(await _brain_availability(b, ollama_tags))
        brains_out.append(entry)

    voices_out = [
        {"id": v.id, "label": v.label, "kokoro_voice": v.kokoro_voice,
         "default": v.default, "available": True}
        for v in catalog.voices
    ]

    # Frontend serves avatars from /avatars/* (Vite public dir). We can't
    # check on the orchestrator side, so mark all "available" and let the
    # frontend handle 404s gracefully.
    avatars_out = [
        {"id": a.id, "label": a.label, "glb_path": a.glb_path,
         "default": a.default, "available": True}
        for a in catalog.avatars
    ]

    personalities_out = [
        {"id": p.id, "label": p.label, "default": p.default, "available": True}
        for p in catalog.personalities
    ]

    return {
        "brains": brains_out,
        "voices": voices_out,
        "avatars": avatars_out,
        "personalities": personalities_out,
    }


async def _fetch_ollama_tags(ollama_url: str) -> set[str]:
    """Return a set of pulled model names, or empty set if Ollama unreachable."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{ollama_url.rstrip('/')}/api/tags")
            if resp.status_code != 200:
                return set()
            data = resp.json()
        return {m.get("name") or m.get("model") for m in (data.get("models") or [])}
    except (httpx.HTTPError, ValueError):
        return set()


async def _brain_availability(brain, ollama_tags: set[str]) -> dict:
    if brain.kind == "ollama":
        if brain.model in ollama_tags:
            return {"available": True}
        return {"available": False, "reason": f"run: ollama pull {brain.model}"}
    if brain.kind == "cloud-litellm":
        if brain.requires_key and os.environ.get(brain.requires_key):
            return {"available": True}
        return {"available": False, "reason": f"set env: {brain.requires_key}"}
    if brain.kind == "openai-compatible":
        try:
            async with httpx.AsyncClient(timeout=0.5) as client:
                resp = await client.get(f"{brain.url.rstrip('/')}/models")
                if resp.status_code < 500:
                    return {"available": True}
                return {"available": False, "reason": f"server HTTP {resp.status_code}"}
        except httpx.HTTPError:
            return {"available": False, "reason": f"unreachable at {brain.url}"}
    return {"available": False, "reason": "unknown brain kind"}
```

- [ ] **Step 3: Write `services/orchestrator/tests/test_routes_catalog.py`**

```python
"""Tests for /v1/catalog."""
import httpx
import pytest
import respx


@respx.mock
async def test_get_catalog_returns_4_sections(app_client, monkeypatch):
    # Mock Ollama /api/tags to return qwen3:4b
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
    )
    resp = await app_client.get("/v1/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert {"brains", "voices", "avatars", "personalities"} <= set(body.keys())
    assert len(body["brains"]) >= 4  # qwen3-4b + 3 cloud + maybe more


@respx.mock
async def test_get_catalog_marks_pulled_models_available(app_client, monkeypatch):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = await app_client.get("/v1/catalog")
    body = resp.json()
    q = next(b for b in body["brains"] if b["id"] == "qwen3-4b")
    assert q["available"] is True
    claude = next(b for b in body["brains"] if b["id"] == "claude-sonnet")
    assert claude["available"] is False
    assert "ANTHROPIC_API_KEY" in claude["reason"]


@respx.mock
async def test_get_catalog_unpulled_model_unavailable(app_client):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.get("/v1/catalog")
    body = resp.json()
    q = next(b for b in body["brains"] if b["id"] == "qwen3-4b")
    assert q["available"] is False
    assert "ollama pull qwen3:4b" in q["reason"]


@respx.mock
async def test_get_catalog_ollama_unreachable_unavailable(app_client):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        side_effect=httpx.ConnectError("nope")
    )
    resp = await app_client.get("/v1/catalog")
    body = resp.json()
    # All ollama brains marked unavailable
    ollama_brains = [b for b in body["brains"] if b["kind"] == "ollama"]
    assert all(not b["available"] for b in ollama_brains)
```

- [ ] **Step 4: Run catalog route tests**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/services/orchestrator
source .venv/bin/activate
pytest tests/test_routes_catalog.py -v 2>&1 | tail -10
```

Expected: 4 passed.

- [ ] **Step 5: Write `services/orchestrator/orchestrator/routes/state.py`**

```python
"""GET /v1/state — current active selections + Ollama residency snapshot."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/state")
async def get_state(request: Request) -> dict:
    state_store = request.app.state.state_store
    residency = request.app.state.residency
    ollama_status = await residency.query()
    return {
        "active": state_store.get_state(),
        "system": {"ollama": ollama_status},
    }
```

- [ ] **Step 6: Write `services/orchestrator/tests/test_routes_state.py`**

```python
"""Tests for /v1/state."""
import httpx
import pytest
import respx


@respx.mock
async def test_get_state_returns_active_and_system(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "qwen3:4b", "size": 100, "size_vram": 100}]},
        )
    )
    resp = await app_client.get("/v1/state")
    assert resp.status_code == 200
    body = resp.json()
    assert "active" in body
    assert "system" in body
    assert body["active"]["brain"] == "qwen3-4b"  # default
    assert body["system"]["ollama"]["reachable"] is True
    assert body["system"]["ollama"]["loaded"][0]["residency"] == "gpu"


@respx.mock
async def test_get_state_when_ollama_unreachable(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        side_effect=httpx.ConnectError("nope")
    )
    resp = await app_client.get("/v1/state")
    body = resp.json()
    assert body["system"]["ollama"]["reachable"] is False
    assert body["system"]["ollama"]["loaded"] == []
    # active selections still present
    assert "brain" in body["active"]
```

- [ ] **Step 7: Run state route tests**

```bash
pytest tests/test_routes_state.py -v 2>&1 | tail -10
```

Expected: 2 passed.

- [ ] **Step 8: Write `services/orchestrator/orchestrator/routes/swap.py`**

```python
"""POST /v1/swap — flip a valve."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from orchestrator.catalog import CatalogError

router = APIRouter()


_VALID_KINDS = {"brain", "voice", "avatar", "personality", "tools"}


class SwapBody(BaseModel):
    kind: str
    id: str
    value: bool | None = None  # only used when kind=='tools'


@router.post("/v1/swap")
async def post_swap(request: Request, body: SwapBody) -> JSONResponse:
    if body.kind not in _VALID_KINDS:
        return JSONResponse({"error": f"unknown kind '{body.kind}'"}, status_code=400)

    state_store = request.app.state.state_store

    if body.kind == "tools":
        if body.value is None or not isinstance(body.value, bool):
            return JSONResponse(
                {"error": f"tools swap requires 'value' (boolean), got {body.value!r}"},
                status_code=400,
            )
        try:
            state_store.set_tool(body.id, body.value)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    else:
        # Check availability against the catalog
        try:
            state_store.set_state(body.kind, body.id)
        except CatalogError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    # Return the same shape as GET /v1/state for the dashboard to update from
    residency = request.app.state.residency
    return JSONResponse(
        {
            "active": state_store.get_state(),
            "system": {"ollama": await residency.query()},
        },
        status_code=200,
    )
```

- [ ] **Step 9: Write `services/orchestrator/tests/test_routes_swap.py`**

```python
"""Tests for /v1/swap."""
import httpx
import pytest
import respx


@respx.mock
async def test_swap_brain_updates_state(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "brain", "id": "smollm2-360m"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"]["brain"] == "smollm2-360m"


@respx.mock
async def test_swap_unknown_brain_returns_400(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "brain", "id": "no-such-brain"}
    )
    assert resp.status_code == 400
    assert "no-such-brain" in resp.json()["error"]


@respx.mock
async def test_swap_tools_requires_value(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "tools", "id": "web_search"}
    )
    assert resp.status_code == 400


@respx.mock
async def test_swap_tools_with_value_updates_state(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "tools", "id": "web_search", "value": True}
    )
    assert resp.status_code == 200
    assert resp.json()["active"]["tools"]["web_search"] is True


@respx.mock
async def test_swap_unknown_kind_returns_400(app_client):
    resp = await app_client.post(
        "/v1/swap", json={"kind": "weird", "id": "x"}
    )
    assert resp.status_code == 400
```

- [ ] **Step 10: Run swap tests**

```bash
pytest tests/test_routes_swap.py -v 2>&1 | tail -10
```

Expected: 5 passed.

- [ ] **Step 11: Run the full suite**

```bash
pytest tests/ 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 12: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add services/orchestrator/
git commit -m "feat(orch): GET /v1/catalog, GET /v1/state, POST /v1/swap"
```

---

## Task 9: Frontend integration

**Files:**
- Modify: `frontend/src/tts/TTSManager.js`
- Modify: `frontend/src/avatar/AvatarManager.js`
- Modify: `frontend/src/ui/components/ControlPanel.js`
- Modify: `frontend/src/pipeline/Orchestrator.js`
- Modify: `frontend/vite.config.js`

Frontend reads voice + avatar from `/v1/state` on init. Toggle changes go to POST /v1/swap. Body fields for wiki/web_search go away — server-side state is canonical.

- [ ] **Step 1: Add `/api/orch` proxy to `frontend/vite.config.js`**

Find the existing `proxy:` block and add a new entry alongside `/api/stt`, `/api/llm`, `/api/tts`:

```javascript
      '/api/orch': {
        target: 'http://localhost:8082',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/orch/, ''),
      },
```

This gives the frontend a clean `/api/orch/v1/catalog`, `/api/orch/v1/state`, `/api/orch/v1/swap`.

- [ ] **Step 2: Modify `frontend/src/tts/TTSManager.js` — read voice from state**

Find this line near the top of the constructor:

```javascript
    this._voice = config.ttsDefaultVoice;
```

Replace with:

```javascript
    this._voice = config.ttsDefaultVoice;  // fallback until state loads
    this._loadVoiceFromState();
```

Then add this method to the class (after `setVoice` is fine):

```javascript
  async _loadVoiceFromState() {
    try {
      const resp = await fetch('/api/orch/v1/state');
      if (!resp.ok) return;
      const body = await resp.json();
      const stateVoice = body?.active?.voice;
      if (!stateVoice) return;
      // Get the catalog to translate "bella" → "af_bella"
      const catResp = await fetch('/api/orch/v1/catalog');
      if (!catResp.ok) return;
      const cat = await catResp.json();
      const v = (cat.voices || []).find((x) => x.id === stateVoice);
      if (v?.kokoro_voice) this._voice = v.kokoro_voice;
    } catch (_e) {
      // Best-effort. Keep the fallback voice.
    }
  }
```

- [ ] **Step 3: Modify `frontend/src/avatar/AvatarManager.js` — read avatar from state**

Find the `loadAvatar` method (around line 37):

```javascript
async loadAvatar(url = config.avatarUrl, onProgress = null) {
```

Add a helper method that resolves the active avatar's glb_path:

```javascript
async _resolveAvatarUrl() {
    try {
      const resp = await fetch('/api/orch/v1/state');
      if (!resp.ok) return config.avatarUrl;
      const stateBody = await resp.json();
      const avatarId = stateBody?.active?.avatar;
      if (!avatarId) return config.avatarUrl;
      const catResp = await fetch('/api/orch/v1/catalog');
      if (!catResp.ok) return config.avatarUrl;
      const cat = await catResp.json();
      const entry = (cat.avatars || []).find((a) => a.id === avatarId);
      return entry?.glb_path || config.avatarUrl;
    } catch (_e) {
      return config.avatarUrl;
    }
  }
```

Then modify `loadAvatar`'s default-url resolution. Change:

```javascript
async loadAvatar(url = config.avatarUrl, onProgress = null) {
```

to:

```javascript
async loadAvatar(url = null, onProgress = null) {
    if (url === null) {
      url = await this._resolveAvatarUrl();
    }
```

(The rest of the method stays the same.)

- [ ] **Step 4: Modify `frontend/src/ui/components/ControlPanel.js` — POST /v1/swap on toggle**

Find the `_buildToggle` helper. It currently writes to `localStorage[storageKey]`. Modify it to ALSO POST to /v1/swap when the toggle is a tool toggle.

Find this block in `_buildToggle`:

```javascript
    cb.addEventListener('change', () => {
      const v = cb.checked;
      localStorage.setItem(storageKey, v ? 'true' : 'false');
      if (onChange) onChange(v);
    });
```

Replace with:

```javascript
    cb.addEventListener('change', async () => {
      const v = cb.checked;
      localStorage.setItem(storageKey, v ? 'true' : 'false');
      // Plan #7: tool toggles also live server-side; POST to /v1/swap.
      // The mapping localStorage key → tool name is encoded in the key suffix.
      const toolName = storageKey.replace('nodeava.toggle.', '');
      try {
        await fetch('/api/orch/v1/swap', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({kind: 'tools', id: toolName, value: v}),
        });
      } catch (_e) {
        // Best-effort. State will catch up on next page load.
      }
      if (onChange) onChange(v);
    });
```

Also: on construction of each toggle, fetch initial state from `/v1/state` so the dashboard reflects server-side truth (overriding localStorage if they differ).

After the `cb.checked = ...` line that reads from localStorage in `_buildToggle`, add:

```javascript
    // Plan #7: prefer server-side state over local cache when available.
    fetch('/api/orch/v1/state').then((r) => r.ok ? r.json() : null).then((body) => {
      if (!body) return;
      const toolName = storageKey.replace('nodeava.toggle.', '');
      const serverValue = body?.active?.tools?.[toolName];
      if (typeof serverValue === 'boolean' && serverValue !== cb.checked) {
        cb.checked = serverValue;
        localStorage.setItem(storageKey, serverValue ? 'true' : 'false');
      }
    }).catch(() => {});
```

- [ ] **Step 5: Modify `frontend/src/pipeline/Orchestrator.js` — drop body field overrides**

Find this block (around line 228):

```javascript
        {
          webSearch: this._webSearchEnabled,
          wiki: this._wikiEnabled,
        },
```

The orchestrator backend now reads these from server-side state. Replace with:

```javascript
        {
          // Plan #7: server-side state is canonical; these are sent for
          // backwards compatibility but ignored by the orchestrator.
          webSearch: this._webSearchEnabled,
          wiki: this._wikiEnabled,
        },
```

(No code change required — keep the body fields for backwards compatibility. The orchestrator already strips them per Task 7. Just leave a comment.)

- [ ] **Step 6: Manual smoke check**

If the stack is up (from prior test session):

```bash
docker compose ps 2>&1 | head -8
```

Refresh `http://localhost:5173` in the browser. Open devtools network tab. Observe:
- A `state` request fires shortly after page load
- A `catalog` request fires
- Wiki toggle reflects the server's `state.tools.wiki` value (probably `true` after init)
- Toggling web search sends a POST to `/api/orch/v1/swap`

If Vite hasn't reloaded after the proxy change, restart the dev server.

- [ ] **Step 7: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/
git commit -m "feat(frontend): read voice/avatar/tools from /v1/state; toggles POST /v1/swap"
```

---

## Task 10: Teaching scripts (interactive)

**Files:**
- Create: `scripts/demos/_audio.sh`
- Create: `scripts/demos/test-llm.sh`
- Create: `scripts/demos/test-tts.sh`
- Create: `scripts/demos/test-stt.sh`
- Create: `scripts/demos/test-pipeline.sh`
- Create: `scripts/demos/test-orchestrator.sh`
- Create: `scripts/demos/list-models.sh`
- Create: `assets/demos/sample-stt.wav`

- [ ] **Step 1: Create `scripts/demos/_audio.sh`**

```bash
mkdir -p /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/scripts/demos
```

Write `scripts/demos/_audio.sh`:

```bash
# Sourced helper for cross-platform mic recording + audio playback.
# Workshop attendees run scripts on Linux, WSL2, or macOS.
# Usage: source this file; then call record_5s OUTPUT_WAV or play_wav INPUT_WAV

_audio_detect() {
  case "$(uname -s)" in
    Darwin) AUDIO_OS=mac;;
    Linux)  AUDIO_OS=linux;;
    *)      AUDIO_OS=unknown;;
  esac
}
_audio_detect

record_5s() {
  local out="$1"
  if [ -z "$out" ]; then echo "record_5s: missing output path" >&2; return 2; fi
  echo "Recording 5s — speak now in: 3..."; sleep 1
  echo "                       2..."; sleep 1
  echo "                       1..."; sleep 1
  printf "\a"  # terminal bell
  echo "GO. Recording..."
  case "$AUDIO_OS" in
    linux)
      if ! command -v arecord >/dev/null 2>&1; then
        echo "ERROR: arecord not found. Install: sudo apt install alsa-utils" >&2
        return 1
      fi
      arecord -d 5 -f S16_LE -r 16000 -c 1 "$out" >/dev/null 2>&1
      ;;
    mac)
      if ! command -v sox >/dev/null 2>&1; then
        echo "ERROR: sox not found. Install: brew install sox" >&2
        return 1
      fi
      sox -d -c 1 -r 16000 -b 16 "$out" trim 0 5 >/dev/null 2>&1
      ;;
    *)
      echo "ERROR: unsupported OS for mic recording" >&2; return 1;;
  esac
  printf "\a"  # done bell
  echo "Recorded $(du -h "$out" | cut -f1) → $out"
}

play_wav() {
  local in="$1"
  if [ -z "$in" ]; then echo "play_wav: missing input path" >&2; return 2; fi
  case "$AUDIO_OS" in
    linux)
      if command -v aplay >/dev/null 2>&1; then aplay -q "$in"; else paplay "$in" 2>/dev/null || echo "ERROR: no aplay/paplay" >&2; fi
      ;;
    mac)
      afplay "$in"
      ;;
    *)
      echo "ERROR: unsupported OS for playback" >&2; return 1;;
  esac
}

# Endpoint defaults — overridable via env
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
TTS_URL="${TTS_URL:-http://localhost:8880}"
STT_URL="${STT_URL:-http://localhost:8080}"
ORCH_URL="${ORCH_URL:-http://localhost:8082}"
```

- [ ] **Step 2: Create `scripts/demos/test-llm.sh`**

```bash
#!/bin/bash
# Slide 13: Test the local LLM end-to-end (no agentic loop, just chat).
# Streams tokens as they arrive so attendees see the latency.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

if $FIXTURE; then
  PROMPT="Explain digital humans in one paragraph."
  echo "Using fixture prompt: $PROMPT"
else
  read -r -p "Your prompt: " PROMPT
fi

MODEL=$(curl -fsS "$OLLAMA_URL/api/tags" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("models")or[{}])[0].get("name",""))')
echo "Calling Ollama (model=$MODEL):"

curl -fsSN "$OLLAMA_URL/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'model':sys.argv[1],'messages':[{'role':'user','content':sys.argv[2]}],'stream':True}))" "$MODEL" "$PROMPT")" \
  | while IFS= read -r line; do
      case "$line" in
        data:*)
          payload="${line#data: }"
          [ "$payload" = "[DONE]" ] && break
          token=$(python3 -c "import json,sys;d=json.loads(sys.argv[1]);c=d.get('choices')or[{}];print(c[0].get('delta',{}).get('content',''),end='')" "$payload" 2>/dev/null || true)
          printf '%s' "$token"
          ;;
      esac
    done
echo
```

```bash
chmod +x scripts/demos/test-llm.sh
```

- [ ] **Step 3: Create `scripts/demos/test-tts.sh`**

```bash
#!/bin/bash
# Slide 14: Test the TTS engine. Type a phrase, hear it synthesized.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

if $FIXTURE; then
  PHRASE="The pipeline is up and running."
else
  read -r -p "Phrase to synthesize: " PHRASE
fi

# Get active voice from orchestrator state
VOICE=$(curl -fsS "$ORCH_URL/v1/state" 2>/dev/null \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);
v=d.get("active",{}).get("voice");
import urllib.request,json as j
cat=j.loads(urllib.request.urlopen("'"$ORCH_URL"'/v1/catalog").read());
print(next((x["kokoro_voice"] for x in cat.get("voices",[]) if x["id"]==v),"af_bella"))' 2>/dev/null || echo "af_bella")

OUT="$(mktemp -t tts-XXXX.wav)"
echo "Synthesizing with voice=$VOICE ..."
curl -fsS -X POST "$TTS_URL/dev/captioned_speech" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'model':'kokoro','input':sys.argv[1],'voice':sys.argv[2],'response_format':'pcm','stream':False,'return_timestamps':False}))" "$PHRASE" "$VOICE")" \
  | python3 -c 'import sys, wave, json
# Read JSON envelope, extract base64 audio
import base64
d = json.load(sys.stdin)
audio_b64 = d.get("audio") or d.get("data") or ""
pcm = base64.b64decode(audio_b64) if audio_b64 else b""
w = wave.open(sys.argv[1], "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm); w.close()' "$OUT"
echo "Playing $OUT"
play_wav "$OUT"
rm -f "$OUT"
```

```bash
chmod +x scripts/demos/test-tts.sh
```

- [ ] **Step 4: Create `scripts/demos/test-stt.sh`**

```bash
#!/bin/bash
# Slide 15: Test STT with mic input (or --fixture for a shipped WAV).
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DEMOS/../.." && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

if $FIXTURE; then
  WAV="$REPO_ROOT/assets/demos/sample-stt.wav"
  if [ ! -f "$WAV" ]; then
    echo "ERROR: fixture not found at $WAV" >&2; exit 1
  fi
  echo "Using fixture: $WAV"
else
  WAV="$(mktemp -t stt-XXXX.wav)"
  record_5s "$WAV"
fi

echo "Sending to Whisper..."
TRANSCRIPT=$(curl -fsS -X POST "$STT_URL/v1/audio/transcriptions" \
  -F "file=@$WAV" -F "model=base.en" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("text",""))')

echo "Transcript: $TRANSCRIPT"
$FIXTURE || rm -f "$WAV"
```

```bash
chmod +x scripts/demos/test-stt.sh
```

- [ ] **Step 5: Create `scripts/demos/test-pipeline.sh`**

```bash
#!/bin/bash
# Slide 23: End-to-end digital human in bash.
# Mic → Whisper → Ollama (active brain) → Kokoro (active voice) → speakers.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

# Step 1: Get spoken (or fixture) input
WAV="$(mktemp -t pipe-XXXX.wav)"
if $FIXTURE; then
  cp "$(cd "$DEMOS/../.." && pwd)/assets/demos/sample-stt.wav" "$WAV"
  echo "Using fixture audio"
else
  record_5s "$WAV"
fi

# Step 2: Transcribe
echo "[1/3] Transcribing..."
TRANSCRIPT=$(curl -fsS -X POST "$STT_URL/v1/audio/transcriptions" \
  -F "file=@$WAV" -F "model=base.en" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("text",""))')
echo "       \"$TRANSCRIPT\""
rm -f "$WAV"

# Step 3: Ask the orchestrator (this exercises the agentic loop + state)
echo "[2/3] Asking the agent..."
ANSWER=$(curl -fsS -X POST "$ORCH_URL/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'messages':[{'role':'user','content':sys.argv[1]}],'stream':False}))" "$TRANSCRIPT")" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("choices",[{}])[0].get("message",{}).get("content",""))')
echo "       \"$ANSWER\""

# Step 4: Synthesize the answer with the active voice + play
echo "[3/3] Speaking..."
VOICE=$(curl -fsS "$ORCH_URL/v1/state" \
  | python3 -c 'import json,sys,urllib.request;d=json.load(sys.stdin);
v=d.get("active",{}).get("voice");
cat=json.loads(urllib.request.urlopen("'"$ORCH_URL"'/v1/catalog").read())
print(next((x["kokoro_voice"] for x in cat.get("voices",[]) if x["id"]==v),"af_bella"))')

OUT="$(mktemp -t reply-XXXX.wav)"
curl -fsS -X POST "$TTS_URL/dev/captioned_speech" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'model':'kokoro','input':sys.argv[1],'voice':sys.argv[2],'response_format':'pcm','stream':False,'return_timestamps':False}))" "$ANSWER" "$VOICE")" \
  | python3 -c 'import sys,wave,json,base64
d=json.load(sys.stdin); a=d.get("audio") or d.get("data") or ""
pcm=base64.b64decode(a) if a else b""
w=wave.open(sys.argv[1],"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm); w.close()' "$OUT"
play_wav "$OUT"
rm -f "$OUT"
echo "Done."
```

```bash
chmod +x scripts/demos/test-pipeline.sh
```

- [ ] **Step 6: Create `scripts/demos/test-orchestrator.sh`**

```bash
#!/bin/bash
# Slide 24+33: Interactively poke the orchestrator's swap endpoints.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

show_state() {
  echo "--- /v1/state ---"
  curl -fsS "$ORCH_URL/v1/state" | python3 -m json.tool
}

swap_kind() {
  local kind="$1"
  echo "Available ${kind}s:"
  curl -fsS "$ORCH_URL/v1/catalog" \
    | python3 -c "import json,sys;d=json.load(sys.stdin)
for x in d.get(\"${kind}s\",[]):
    avail = '✓' if x.get('available',True) else '✗'
    print(f'  {avail} {x[\"id\"]:25s} {x[\"label\"]}')"
  read -r -p "Swap to id: " ID
  curl -fsS -X POST "$ORCH_URL/v1/swap" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys;print(json.dumps({'kind':sys.argv[1],'id':sys.argv[2]}))" "$kind" "$ID")" \
    | python3 -m json.tool
}

toggle_tool() {
  read -r -p "Tool to toggle (web_search|wiki): " T
  read -r -p "Value (true|false): " V
  curl -fsS -X POST "$ORCH_URL/v1/swap" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys;print(json.dumps({'kind':'tools','id':sys.argv[1],'value':sys.argv[2].lower()=='true'}))" "$T" "$V")" \
    | python3 -m json.tool
}

while true; do
  cat <<EOF

NodeAva Orchestrator Demo Menu
  [1] show state
  [2] swap brain
  [3] swap voice
  [4] swap personality
  [5] toggle tool
  [q] quit
EOF
  read -r -p "> " choice
  case "$choice" in
    1) show_state;;
    2) swap_kind brain;;
    3) swap_kind voice;;
    4) swap_kind personality;;
    5) toggle_tool;;
    q|Q|exit|quit) break;;
    *) echo "unknown: $choice";;
  esac
done
```

```bash
chmod +x scripts/demos/test-orchestrator.sh
```

- [ ] **Step 7: Create `scripts/demos/list-models.sh`**

```bash
#!/bin/bash
# Print the catalog. Highlights unavailable items in yellow.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

curl -fsS "$ORCH_URL/v1/catalog" \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
RESET="\033[0m"; YELLOW="\033[33m"; GREEN="\033[32m"
for section in ("brains","voices","avatars","personalities"):
    print(f"\n=== {section} ===")
    for item in d.get(section, []):
        avail = item.get("available", True)
        color = GREEN if avail else YELLOW
        mark = "✓" if avail else "✗"
        reason = "" if avail else f"  ({item.get(\"reason\",\"unavailable\")})"
        print(f"  {color}{mark} {item[\"id\"]:25s}{RESET} {item[\"label\"]}{reason}")
'
```

```bash
chmod +x scripts/demos/list-models.sh
```

- [ ] **Step 8: Create `assets/demos/sample-stt.wav`**

```bash
mkdir -p assets/demos
# Generate a 5-second sample audio: speak the canonical phrase using Kokoro
curl -fsS -X POST "${TTS_URL:-http://localhost:8880}/dev/captioned_speech" \
  -H 'Content-Type: application/json' \
  -d '{"model":"kokoro","input":"Hello NodeAva, what time is it?","voice":"af_bella","response_format":"pcm","stream":false,"return_timestamps":false}' \
  | python3 -c 'import json,sys,wave,base64
d=json.load(sys.stdin); a=d.get("audio") or d.get("data") or ""
pcm=base64.b64decode(a) if a else b""
w=wave.open(sys.argv[1],"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm); w.close()' \
  assets/demos/sample-stt.wav
ls -la assets/demos/sample-stt.wav
```

Expected: a wav file ~150 KB. If Kokoro isn't running yet you can defer creating this fixture — the scripts work without `--fixture` mode.

- [ ] **Step 9: Smoke-test list-models.sh**

```bash
bash scripts/demos/list-models.sh 2>&1 | head -20
```

Expected: prints brains/voices/avatars/personalities sections with ✓/✗ markers.

- [ ] **Step 10: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add scripts/demos/ assets/demos/
git commit -m "feat(scripts): interactive teaching demos for slides 13-24"
```

---

## Task 11: Documentation updates

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `services/orchestrator/README.md`

- [ ] **Step 1: Update `CLAUDE.md` — LLM section + port table**

Read the file first, find the LLM section (referencing Qwen3 thinking mode, `--jinja --reasoning-format none`):

```bash
grep -n "Qwen3 Thinking\|llama-server\|--jinja" CLAUDE.md
```

Replace the Qwen3 Thinking section with:

```markdown
## Local LLM via Ollama (Plan #7)

Local model serving uses **Ollama on the host** — not in Docker. Ollama runs
on all three supported platforms (Linux, WSL2, macOS Apple Silicon) and
manages model residency in VRAM automatically.

- Install: `curl -fsSL https://ollama.com/install.sh | sh` (Linux/WSL2) or `brew install ollama` (macOS)
- Default models: `ollama pull qwen3:4b smollm2:360m`
- Endpoint: `http://localhost:11434` on the host; the orchestrator container reaches it via `host.docker.internal:11434` (on Linux this requires `extra_hosts: ["host.docker.internal:host-gateway"]` in the compose service — already configured)
- Wire format: OpenAI-compatible at `/v1/chat/completions`
- Residency: `GET /api/ps` reports loaded models with `size` + `size_vram` for the dashboard's gpu/split/cpu chips
- Thinking-mode (`<think>` tags from Qwen3) is still stripped client-side in `Orchestrator.js` — Ollama returns the raw model output unchanged
```

Find the port table and update it:

```markdown
## Port Mappings

| Service | Internal | External |
|---------|----------|----------|
| Frontend/nginx | 80 | 3000 |
| STT (whisper.cpp) | 8080 | 8080 |
| Orchestrator | 8082 | 8082 |
| TTS (Kokoro-FastAPI) | 8880 | 8880 |
| Ollama (host process, not in Docker) | 11434 | 11434 |
```

Append a Plan #7 section at the end of CLAUDE.md:

```markdown
## Plan #7 — command center backend

- Three new endpoints power the workshop dashboard:
  - `GET /v1/catalog` — list brains/voices/avatars/personalities with `available` annotations
  - `GET /v1/state` — current active selections + Ollama residency snapshot (gpu/split/cpu)
  - `POST /v1/swap` — `{kind, id, value?}` flips a valve; returns the new state
- Source-of-truth files: `configs/catalog.yml` (what's swappable) and `state/current.json` (what's active)
- Provider dispatcher routes per-request: `kind: ollama` → OllamaProvider, `kind: cloud-litellm` → LiteLLMProvider with env-var key, `kind: openai-compatible` → OllamaProvider against the brain's `url`
- Personality system prompt: injected at request time from `state.personality`; default personality instructs the model to use wiki + browser tools for project + current-events questions
- Tool toggles (web_search / wiki) now live in `state.tools` rather than browser localStorage; frontend's ControlPanel POSTs to /v1/swap on change
- Interactive teaching scripts in `scripts/demos/` (test-llm, test-tts, test-stt, test-pipeline, test-orchestrator, list-models) back slides 13-24 of the workshop deck
- Setup: `bash scripts/setup-linux.sh` (Linux/WSL2) or `bash scripts/setup-mac.sh` (macOS) installs Ollama and pulls default models
```

- [ ] **Step 2: Update `README.md` install section**

```bash
grep -n "Install\|setup-mac\|llama" README.md | head
```

Find the install/setup section. Add a prereq line:

```markdown
**Prerequisites:**
- Docker + Docker Compose
- Ollama installed on the host (the workshop installer runs it for you):
  - Linux/WSL2: `bash scripts/setup-linux.sh`
  - macOS: `bash scripts/setup-mac.sh`
```

Remove any reference to downloading `Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf` — that's no longer needed.

- [ ] **Step 3: Update `services/orchestrator/README.md` — document new endpoints**

Find a good insertion point (right after the existing "Ingest endpoint" section from Plan #6). Add:

```markdown
## Command Center endpoints (Plan #7)

### `GET /v1/catalog`

Returns the full catalog of swappable items:
\```json
{
  "brains": [{"id":"qwen3-4b","label":"...","kind":"ollama","model":"qwen3:4b","available":true}, ...],
  "voices": [...],
  "avatars": [...],
  "personalities": [...]
}
\```

Each entry has an `available` boolean computed per-request:
- `kind: ollama` → `available: true` if the model name is in Ollama's `/api/tags`
- `kind: cloud-litellm` → `available: true` if `requires_key` env var is set
- `kind: openai-compatible` → `available: true` if the server's `/models` returns < 500

### `GET /v1/state`

Returns the active selections + Ollama residency:
\```json
{
  "active": {"brain":"qwen3-4b","voice":"bella","avatar":"ava","personality":"default","tools":{"web_search":false,"wiki":true}},
  "system": {
    "ollama": {
      "reachable": true,
      "loaded": [{"model":"qwen3:4b","size_bytes":3000,"size_vram_bytes":3000,"residency":"gpu"}]
    }
  }
}
\```

`residency` is `gpu` / `split` / `cpu` based on Ollama's `size_vram / size` ratio.

### `POST /v1/swap`

Body shape:
| `kind`          | `id`                   | `value`       |
|-----------------|------------------------|---------------|
| `brain`         | catalog brain id       | (ignored)     |
| `voice`         | catalog voice id       | (ignored)     |
| `avatar`        | catalog avatar id      | (ignored)     |
| `personality`   | catalog personality id | (ignored)     |
| `tools`         | tool name              | bool (req.)   |

Returns the full new state (same shape as `GET /v1/state`).

400 on unknown kind/id or missing `value` for tools. 200 on success.
```

(Replace `\```` with literal triple-backticks when writing.)

- [ ] **Step 4: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add CLAUDE.md README.md services/orchestrator/README.md
git commit -m "docs: Plan #7 — Ollama, command center endpoints, teaching scripts"
```

---

## Task 12: End-to-end smoke test

**Files:** none modified — verification step.

After all prior tasks, run a clean validation pass against a running stack.

- [ ] **Step 1: Bring up the stack with Ollama on host**

```bash
# Ensure Ollama is running on the host
curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 || ollama serve &
sleep 2
ollama pull qwen3:4b 2>&1 | tail -3

# Bring up the docker stack
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml up -d --force-recreate orchestrator tts stt searxng
sleep 5
docker compose ps
```

Expected: all containers healthy, no `llm` container in the list.

- [ ] **Step 2: Test the catalog endpoint**

```bash
curl -fsS http://localhost:8082/v1/catalog | python3 -m json.tool | head -40
```

Expected: 4 sections present; `qwen3-4b` has `"available": true`; cloud entries have `"available": false` with `"reason"` mentioning the env var.

- [ ] **Step 3: Test the state endpoint**

```bash
curl -fsS http://localhost:8082/v1/state | python3 -m json.tool
```

Expected: `active.brain == "qwen3-4b"`, `system.ollama.reachable == true`, and at least one loaded model with a `residency` field.

- [ ] **Step 4: Swap the brain**

```bash
curl -fsS -X POST http://localhost:8082/v1/swap \
  -H 'Content-Type: application/json' \
  -d '{"kind":"brain","id":"smollm2-360m"}' \
  | python3 -m json.tool
```

Expected: returns full state with `"brain":"smollm2-360m"`. Run a chat afterwards to confirm the smaller model is used.

- [ ] **Step 5: Run a chat with personality + wiki active**

```bash
curl -fsS -X POST http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What ports do NodeAva services run on?"}],"stream":false}' \
  | python3 -m json.tool | head -20
```

Expected: the response references concrete NodeAva ports (8082, 8880, 8080, 11434) — confirming the personality system prompt triggered a wiki tool call and the wiki content reached the model.

If the response is vague ("I don't have specific information..."), the personality system prompt isn't firing — verify Task 7's chat-route changes are deployed and that `state.personality == "default"`.

- [ ] **Step 6: Run the teaching scripts**

```bash
bash scripts/demos/list-models.sh
bash scripts/demos/test-llm.sh --fixture
bash scripts/demos/test-tts.sh --fixture
bash scripts/demos/test-stt.sh --fixture
bash scripts/demos/test-pipeline.sh --fixture
```

Expected: each script runs cleanly. `test-pipeline.sh` produces audible speech.

- [ ] **Step 7: Run the full orchestrator test suite**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/services/orchestrator
source .venv/bin/activate
pytest tests/ 2>&1 | tail -5
```

Expected: all tests green. Number should be ≥ 109 (Plan #6 baseline) + roughly 25 new (Tasks 3, 4, 5, 6, 7, 8 tests).

- [ ] **Step 8: Commit the smoke-test marker**

If anything failed, fix it and create the appropriate commit. If everything passed and no code changes were needed, no commit is needed for this task.

```bash
git log --oneline -15
```

Expected: clean Plan #7 commit history visible.

---

## Self-Review Checklist (already run; documenting for clarity)

**Spec coverage:**
- Goal 1 (catalog source of truth): Task 4
- Goal 2 (state source of truth): Task 5
- Goal 3 (three endpoints): Tasks 8 (catalog/state/swap routes)
- Goal 4 (Ollama replaces llama.cpp): Tasks 1, 2, 3
- Goal 5 (residency reporting): Task 6
- Goal 6 (interactive teaching scripts): Task 10
- Implementation note (wiki-priming personality): Task 4 (catalog.yml personality definitions) + Task 7 (system prompt injection)

**Type consistency:**
- `BrainEntry` fields used consistently across tasks 4, 5, 7
- `StateStore.set_state(kind, id)` signature used in tasks 5, 8
- `StateStore.set_tool(name, value)` signature used in tasks 5, 8
- `dispatch_for_brain(brain, *, ollama_url, request_timeout, api_key)` used in tasks 7, 8 (chat route)
- `OllamaProvider(*, base_url, model, timeout)` used in tasks 3, 7

**No placeholders:** every step has the actual code/commands/expected output an engineer needs.

---

## What comes next

After Plan #7 lands, Plan #8 (dashboard frontend) brainstorm begins — visual flow diagram, valves, panels rendering from the catalog/state endpoints and the event stream. Plan #9 (installer) wraps Ollama install + `ollama pull` for default models, reusing the catalog defined here.
