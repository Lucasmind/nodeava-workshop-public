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
| `LLAMA_URL` | `http://localhost:8081` | Backend llama-server URL (used when provider=local) |
| `REQUEST_TIMEOUT` | `300` | Seconds, applies to all backend calls |
| `BIND_HOST` | `127.0.0.1` | Listener host. Default = localhost only. |
| `BIND_PORT` | `8082` | Listener port. |
| `PROVIDER` | `local` | Default provider when request omits one |
| `PROVIDER_MODEL` | `""` | Default model id (only used when PROVIDER != "local") |
| `SEARXNG_URL` | `http://searxng:8080` | URL of the bundled SearXNG service (Docker DNS) |
| `WIKI_DIR` | `wiki` | On-disk wiki directory the wiki.* tools read |

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
The default `data:` stream stays clean for OpenAI-SDK clients.

Note: `EventSource` is GET-only, so the brain-pane parses the SSE body
from a `fetch` POST response instead:

```js
const resp = await fetch('/v1/chat/completions', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({messages: [...], stream: true}),
});
const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buf = '';
while (true) {
  const {value, done} = await reader.read();
  if (done) break;
  buf += decoder.decode(value, {stream: true});
  // SSE frames are separated by blank lines
  let idx;
  while ((idx = buf.indexOf('\n\n')) !== -1) {
    const frame = buf.slice(0, idx);
    buf = buf.slice(idx + 2);
    const lines = frame.split('\n');
    let event = 'message', data = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) event = line.slice(7);
      else if (line.startsWith('data: ')) data += line.slice(6);
    }
    if (event === 'thinking_token') {
      const {delta} = JSON.parse(data);
      brainPane.append(delta);
    }
    // event === 'message' (default) carries OpenAI-style content chunks
  }
}
```

OpenAI o-series models hide reasoning entirely — no thinking events
will be emitted for those.

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

## Ingest endpoint (Plan #6)

```
POST /v1/ingest
Content-Type: multipart/form-data
Body: file=<binary>
```

Saves the upload to `/app/raw/uploads/<sanitized-name>`, invokes the
wiki-compiler against it, and returns the list of wiki pages that changed.

**Synchronous.** The request blocks until the compile finishes (~10-30s
for typical sources). Plan #10 may add async polling.

Example:

```bash
curl http://localhost:8082/v1/ingest \
  -F file=@README.md
```

Response (success):

```json
{
  "ok": true,
  "pages_changed": ["sources/readme-md.md", "concepts/pipeline-architecture.md"],
  "source_path": "/app/raw/uploads/README.md",
  "stdout_tail": "..."
}
```

Response (compiler failure):

```json
{
  "ok": false,
  "error": "compiler exited with code 2",
  "stderr_tail": "ANTHROPIC_API_KEY env var not set"
}
```

**Required**: `ANTHROPIC_API_KEY` env var on the orchestrator container.
See the wiki-compiler README for setup.

## Command Center endpoints (Plan #7)

### `GET /v1/catalog`

Returns the full catalog of swappable items:

```json
{
  "brains": [{"id":"qwen3-4b","label":"...","kind":"ollama","model":"qwen3:4b","available":true}, ...],
  "voices": [...],
  "avatars": [...],
  "personalities": [...]
}
```

Each entry has an `available` boolean computed per-request:
- `kind: ollama` → `available: true` if the model name is in Ollama's `/api/tags`
- `kind: cloud-litellm` → `available: true` if `requires_key` env var is set
- `kind: openai-compatible` → `available: true` if the server's `/models` returns < 500

### `GET /v1/state`

Returns the active selections + Ollama residency:

```json
{
  "active": {"brain":"qwen3-4b","voice":"bella","avatar":"ava","personality":"default","tools":{"web_search":false,"wiki":true}},
  "system": {
    "ollama": {
      "reachable": true,
      "loaded": [{"model":"qwen3:4b","size_bytes":3000,"size_vram_bytes":3000,"residency":"gpu"}]
    }
  }
}
```

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

## Run locally (dev)

```bash
cd services/orchestrator
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .

# Point at a running llama-server (the workshop default port is 8081).
export LLAMA_URL=http://localhost:8081

# Production-style — honors BIND_HOST / BIND_PORT from env.
python -m orchestrator.main

# Or for hot-reload during development:
uvicorn orchestrator.main:app --reload --port 8082
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

## Why a custom service when LLMRunners has one?

NodeAva needs a NodeAva-flavored orchestrator: provider switching,
wiki tools, named SSE events for visualizers, localhost-only default.
The LLMRunners orchestrator is the inspiration but is shaped for a
different deployment (chimera, MoE thinking models, OpenWebUI). See
`docs/superpowers/specs/2026-05-16-nodeava-workshop-mvp-design.md`.
