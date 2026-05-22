# Plan #7 — Command Center Backend Design

**Status:** Draft (awaiting user review)
**Author:** Rob Lucas + Claude
**Date:** 2026-05-16
**Implements slides:** 24, 25, 31, 33 of NodeAvaWorkshopDeck v10

## Why this exists

The workshop arc ends with attendees customizing their digital human: choosing
a different LLM, voice, avatar, or personality and watching the same prompt
behave differently. The deck calls this Demo 16 — "Change voice, avatar,
model, and personality" — and Demo 15 — "Switch model providers" (local Qwen
vs. cloud Claude / OpenAI / Groq).

Today the system has none of this. The LLM container is hardcoded to one
model. The voice is hardcoded in `config.js`. There is no avatar picker. The
system prompt is fixed. Tool toggles live in browser local-storage with no
server-side memory.

This spec defines the **backend** the dashboard will talk to. The dashboard
itself (visual flow diagram, valves, panels) is Plan #8.

## Goals

1. A single source of truth for what's swappable (`configs/catalog.yml`).
2. A single source of truth for what's active right now
   (`state/current.json`), persisted across orchestrator restarts.
3. Three endpoints the dashboard can use: list catalog, read state, swap a thing.
4. Cross-platform local LLM serving via **Ollama** (replaces llama.cpp).
5. Honest VRAM **reporting** (not prediction) — the dashboard shows what
   Ollama currently has resident in GPU memory, split between GPU and
   system memory, or fully offloaded to CPU. Attendees see consequences
   of their swap after the fact rather than getting a forecast.
6. A short set of **interactive** "test the organs" CLI scripts for the
   early-workshop low-level demos (slides 13–22). Each script prompts the
   attendee live (typed prompt, mic recording, audio playback) rather than
   just printing canned output. These are teaching scripts, not management
   parity for the dashboard.

## Non-goals

- The dashboard UI. That's Plan #8.
- The "senior colleague" escalation router (slide 32). Could land in a later plan.
- Benchmark feature (slide 34). That's Plan #10.
- The installer (Plan #9) — but Plan #9 will reuse the catalog defined here to know which models to pull at install time.
- Per-attendee multi-tenancy. Single user, localhost.
- Auth on the new endpoints. They're localhost-only like everything else.

## Architecture overview

```
Browser dashboard (Plan #8)
  │ GET /v1/catalog → list of brains/voices/avatars/personalities + availability
  │ GET /v1/state   → what's active + residency snapshot
  │ POST /v1/swap   → flip a valve, get new state
  ▼
nodeava-orch (FastAPI, in Docker)
  ├── catalog.py    — loads + validates configs/catalog.yml
  ├── state.py      — atomic R/W of state/current.json
  ├── dispatcher.py — picks LLM backend at request time (Ollama or LiteLLM or external)
  ├── residency.py  — proxies Ollama /api/ps; derives gpu/split/cpu labels
  └── routes/
        catalog.py — GET /v1/catalog
        state.py   — GET /v1/state
        swap.py    — POST /v1/swap

Backends:
  ├── Ollama  — runs NATIVELY on the host (not in Docker), reached via
  │              http://host.docker.internal:11434 from the orchestrator
  │              container (extra_hosts: host-gateway on Linux)
  ├── kokoro-fastapi (in Docker, unchanged) — voice arg per request
  ├── whisper.cpp (in Docker, unchanged)
  └── LiteLLM (in-process inside orchestrator) — cloud providers
```

Why Ollama native and not Docker? Three reasons: (1) Docker Desktop on
macOS has no Metal passthrough, so Mac was already forced to native;
(2) Ollama's host install (`curl ... | sh` on Linux, `brew install ollama`
on Mac) gives the user a single source of truth for which models are
pulled and how much VRAM they use, shared across NodeAva and any other
LLM tooling the attendee runs; (3) one install pattern across all three
supported platforms (Linux, WSL2, Mac) is simpler than maintaining a
Docker variant.

The orchestrator container reaches the host Ollama via
`host.docker.internal:11434`. On Mac/Windows this is built into Docker
Desktop. On Linux, the orchestrator's compose service declares
`extra_hosts: ["host.docker.internal:host-gateway"]` to get the same name.

The dashboard rendering of "current pipe routing" comes from the existing
typed event stream (Plan #4): every request emits `llm.first_token`,
`tool.call`, `tts.first_audio`, etc. The dashboard correlates events with
current state to draw the active path.

## The catalog file

Path: `configs/catalog.yml`. Bundled with the workshop kit; editable by
attendees who know what they're doing (adding a new model is a YAML edit
+ `ollama pull`).

```yaml
brains:
  # kind: ollama — local model served by Ollama; residency reported via /api/ps
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

  # kind: cloud-litellm — cloud provider via in-process LiteLLM; needs API key
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

  # kind: openai-compatible — power-user escape hatch for any OpenAI-compatible
  # server (llama.cpp, vLLM, LocalAI, TGI). No residency introspection — the
  # dashboard shows "external server" for these. Example (commented):
  # - id: llamacpp-local
  #   label: "Local llama.cpp (advanced)"
  #   kind: openai-compatible
  #   url: http://localhost:8081/v1
  #   model: qwen3-4b-q4_k_m

voices:
  - id: bella
    label: "Bella (warm, conversational)"
    kokoro_voice: af_bella
    default: true
  - id: adam
    label: "Adam (clear, neutral)"
    kokoro_voice: am_adam
  # ... a curated 4-6 voices, not every Kokoro voice

avatars:
  - id: ava
    label: "Ava (default)"
    glb_path: /avatars/default-avatar.glb
    default: true
  # additional avatars added by the installer or by hand-dropping .glb files

personalities:
  - id: default
    label: "Helpful Assistant"
    system_prompt: |
      You are NodeAva, a helpful digital assistant. Be concise.
      When you don't know something, say so. Use tools when they help.
    default: true
  - id: dry-historian
    label: "Dry Historian"
    system_prompt: |
      You are a deeply knowledgeable historian with a dry, deadpan
      wit. You enjoy correcting popular misconceptions.
  - id: improv-comic
    label: "Improv Comic"
    system_prompt: |
      You are a quick-witted improv performer. Yes-and everything.
      Keep responses short and playful.
  - id: tutor
    label: "Patient Tutor"
    system_prompt: |
      You are a patient tutor. Break ideas into small steps.
      Ask Socratic follow-up questions when a concept isn't clear.
```

Validation: on orchestrator startup, `catalog.py` loads the file, validates
required fields per kind, and exposes the parsed model in-memory. Validation
errors fail startup loudly (the catalog is foundational).

**Availability check** (computed per-request, not cached):
- `kind: ollama` → call Ollama `/api/tags`; mark `available: true` if the model name appears
- `kind: cloud-litellm` → check `os.environ.get(requires_key)` is set; mark accordingly
- Avatars → check `glb_path` exists on disk

The `available` boolean is returned in `GET /v1/catalog` so the dashboard can
grey-out unavailable items.

For `kind: openai-compatible`, availability = a successful `GET <url>/models`
(or just a TCP check on the host:port). If the server is unreachable, mark
`available: false` with reason "external server unreachable at <url>".

## The state file

Path: `state/current.json` at the repo root. In Docker, mounted as `./state:/app/state:rw` (similar to the wiki + raw mounts from Plan #6) so the file survives container restarts. On Mac native, written directly to `<repo>/state/current.json`.

```json
{
  "brain": "qwen3-4b",
  "voice": "bella",
  "avatar": "ava",
  "personality": "default",
  "tools": {
    "web_search": false,
    "wiki": true
  }
}
```

`state.py` provides:
- `get_state() -> dict` — returns current state, lazy-loading defaults from catalog if file missing
- `set_state(key, value) -> dict` — atomic write (tempfile + rename), returns new state
- Defaults: any field missing or invalid falls back to whichever catalog entry has `default: true`

State is loaded ONCE at orchestrator startup and cached in memory; swap
operations update both the file and the in-memory copy. Single user,
single dashboard, single laptop — no locking needed. Atomic write
(tempfile + rename) guarantees a concurrent read sees either the old or
new file, never a half-written one.

## Endpoints

### GET /v1/catalog

Returns the full catalog with availability annotations:

```json
{
  "brains": [
    {"id":"qwen3-4b","label":"...","kind":"ollama","vram_mb":3000,"available":true,"default":true},
    {"id":"claude-sonnet","label":"...","kind":"cloud-litellm","vram_mb":0,"available":false,"requires_key":"ANTHROPIC_API_KEY"}
  ],
  "voices": [...],
  "avatars": [...],
  "personalities": [...]
}
```

The dashboard renders unavailable entries differently (greyed, with a tooltip
explaining why — "ollama pull qwen3:4b" or "set ANTHROPIC_API_KEY").

### GET /v1/state

```json
{
  "active": {
    "brain": "qwen3-4b",
    "voice": "bella",
    "avatar": "ava",
    "personality": "default",
    "tools": {"web_search": false, "wiki": true}
  },
  "system": {
    "ollama": {
      "reachable": true,
      "loaded": [
        {
          "model": "qwen3:4b",
          "size_bytes": 3122589696,
          "size_vram_bytes": 3122589696,
          "residency": "gpu"
        },
        {
          "model": "qwen3:7b",
          "size_bytes": 7234567890,
          "size_vram_bytes": 4500000000,
          "residency": "split"
        }
      ]
    }
  }
}
```

The `system.ollama` block is the single source of truth for "what's resident
right now." Backed entirely by Ollama's own `/api/ps`. The orchestrator
adds the `residency` convenience field by comparing `size_vram_bytes`
against `size_bytes`:

| Condition                                | `residency` |
|------------------------------------------|-------------|
| `size_vram_bytes == size_bytes`          | `"gpu"`     |
| `0 < size_vram_bytes < size_bytes`       | `"split"`   |
| `size_vram_bytes == 0`                   | `"cpu"`     |

If Ollama is unreachable, return `{"reachable": false, "loaded": []}` and
log a warning. The request never fails on Ollama issues.

The dashboard renders a small chip per loaded model: green dot for `gpu`,
yellow for `split` ("partially offloaded to system RAM — will be slower"),
red for `cpu` ("running on CPU — much slower"). No prediction, no green/yellow/red
math — just labelled facts from Ollama.

For non-Ollama brains (cloud-litellm, openai-compatible), `system.ollama.loaded`
simply doesn't include them — the dashboard shows a "cloud" badge or
"external server" badge instead, with no residency claim.

### POST /v1/swap

Request body schema:

| `kind`         | `id`             | `value`         | Effect                                                  |
|----------------|------------------|-----------------|---------------------------------------------------------|
| `brain`        | catalog brain id | (ignored)       | Updates `state.brain`                                   |
| `voice`        | catalog voice id | (ignored)       | Updates `state.voice`                                   |
| `avatar`       | catalog avatar id| (ignored)       | Updates `state.avatar`                                  |
| `personality`  | catalog personality id | (ignored) | Updates `state.personality`                             |
| `tools`        | tool name (`web_search` \| `wiki`) | boolean | Updates `state.tools[id] = value` |

Examples:
```json
{"kind": "brain", "id": "smollm2-360m"}
{"kind": "tools", "id": "web_search", "value": true}
```

For non-`tools` kinds: looks up the target id in the catalog. If not found,
returns 400. If catalog says `available: false`, returns 409 with the reason
(missing API key, model not pulled, file not found).

For `tools` kind: `id` must be a known tool name; `value` must be a boolean.
Returns 400 otherwise.

On success: writes the new state and returns the full state object (same
shape as `GET /v1/state`).

No restart logic: swapping a brain ID is just a state change. The next
inference request goes through the dispatcher which routes to whichever brain
is active. Ollama loads/unloads models in VRAM on demand.

Response includes the same `system` block as `GET /v1/state` so the dashboard
can update its VRAM panel after the swap.

## Provider dispatcher

`services/orchestrator/orchestrator/providers/dispatcher.py` replaces the
direct use of `local.py` in the agentic loop. At request time:

1. Read `state.brain` → look up catalog entry
2. If `kind: ollama` → use `OllamaProvider(url=OLLAMA_URL, model=entry.model)`
3. If `kind: cloud-litellm` → use `LiteLLMProvider(model=entry.model)` (already exists from Plan #2 in spirit)

The agentic loop in Plan #4 currently constructs an LLM client once at
startup. That changes: it instead asks the dispatcher per-request. Small
refactor; preserves all existing event streaming and tool-call behavior.

System prompt at request time = `catalog.personalities[state.personality].system_prompt`.
The old hardcoded prompt in `config.js` becomes the fallback for "no
personality set" (shouldn't happen, but defensive).

TTS request reads `state.voice` → looks up `catalog.voices[state.voice].kokoro_voice`
→ passes that to Kokoro. The frontend's `TTSManager.js` currently hardcodes
the voice — it now reads it from `GET /v1/state` on startup. After a swap,
the frontend uses the response body of `POST /v1/swap` (which echoes the
full new state) to update its in-memory copy. SSE push for cross-tab sync
is deferred (not needed for single-user workshop demos).

Avatar: same pattern. `state.avatar` resolves to `glb_path`. Frontend on load
calls `/v1/state` and uses `active.avatar` → catalog → `glb_path`. On swap,
the frontend takes the new glb_path from the swap response, calls
`AvatarManager.loadAvatar(new_glb_path)`, and Three.js disposes the old one
and loads the new.

Tools: the agentic loop already supports `web` and `wiki` toggles per Plan
#5 (currently sent as request body fields). With Plan #7, the orchestrator
reads them from `state.tools` instead of trusting client booleans. The Plan
#5 ControlPanel toggles become read/write proxies to `POST /v1/swap` with
`kind: "tools"`.

## Ollama migration

The first task of the implementation plan. Touch points:

| File | Change |
|------|--------|
| `docker-compose.yml` | **Delete** the `llm` service entirely (no replacement service — Ollama runs on the host). Add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `orchestrator` service so it can reach the host on Linux. Add env `OLLAMA_URL=http://host.docker.internal:11434` to the orchestrator service. |
| `docker-compose.gpu-nvidia.yml` | **Delete** the `llm` override (no llm service to override). |
| `docker-compose.gpu-amd.yml` | **Delete** the `llm` override. |
| `services/orchestrator/orchestrator/providers/local.py` | Rename/replace with `ollama.py` — uses Ollama's OpenAI-compatible endpoint at `<OLLAMA_URL>/v1/chat/completions`; passes `model=<id>` per request |
| `scripts/setup-linux.sh` (new) | Install Ollama natively (`curl -fsSL https://ollama.com/install.sh \| sh`); `ollama pull qwen3:4b smollm2:360m` |
| `scripts/setup-mac.sh` | `brew install ollama`; remove llama.cpp install; `ollama pull qwen3:4b smollm2:360m` |
| `scripts/start-mac.sh` | Ensure `ollama serve` is running (Ollama auto-starts on Mac after `brew install`; script checks `pgrep ollama` and starts if needed). Drop `llama-server` launch. |
| `scripts/stop-mac.sh` | Drop `pkill llama-server`. Leave Ollama running (it's a host service the user may want for other apps). |
| `README.md` / install docs | Add "install Ollama" as the prereq step for Linux/WSL2 (curl-pipe) and Mac (brew). |
| `CLAUDE.md` | Update LLM section (delete `--jinja --reasoning-format none` flags discussion; document Ollama model pull workflow; note that Ollama runs on the host, not in Docker). |
| Tests | Update orchestrator tests that mocked the local llama endpoint. Mock target is now Ollama's OpenAI-compatible endpoint. |

Important behavior preserved across the migration:
- Qwen3 thinking-mode (`<think>` tags) — Ollama returns the raw model output; frontend Orchestrator.js still strips `<think>` tags client-side (already does this — no change).
- Tool/function calling — Ollama supports OpenAI-compatible function calling for capable models including Qwen3. The agentic loop continues to work.
- Streaming — Ollama supports SSE-style streaming via the OpenAI-compatible endpoint.

Ports: Ollama uses 11434 on the host (its default). The orchestrator
points at `http://host.docker.internal:11434` from inside its container.
External port mapping is unnecessary — Ollama is already listening on the
host. Update the port table in CLAUDE.md to reflect that Ollama is a host
service, not a container.

GPU acceleration: handled entirely by the host's Ollama install. CUDA
attendees get CUDA, ROCm attendees get ROCm, Mac attendees get Metal —
all configured by the standard Ollama installer, with no NodeAva-specific
runtime config in docker-compose.

## Personality presets

Defined in `catalog.yml` (see example above). Four presets ship:
default, dry-historian, improv-comic, tutor. Attendees can add more by
editing the catalog file. No UI for editing personality text in Plan #7;
"author your own personality" could be a Plan #8 polish item.

## Voice swap mechanics

Per-request voice. No state on the TTS side — Kokoro accepts a `voice` param
per call. The orchestrator carries `state.voice → catalog → kokoro_voice`
through to every Kokoro request. Swap is instant (next TTS call uses the
new voice).

The frontend's `TTSManager.js` currently builds the request body with a
hardcoded voice. Change: the request body is built on the orchestrator side
(if the orchestrator proxies TTS) OR the frontend reads `state.voice` and
includes it in its own Kokoro request. The cleaner answer is the frontend
reads state — minimal orchestrator touch — but the orchestrator MUST hold
the canonical state. Frontend updates its local copy on swap-success.

## Avatar swap mechanics

Backend: `state.avatar` → `catalog.avatars[id].glb_path`. The avatar files
live in the frontend's static assets (`/avatars/*.glb` served by Vite/nginx).
Catalog entries just point to those URLs.

Frontend: on load, `AvatarManager.js` fetches `/v1/state`, resolves the
glb_path, and loads it. On swap, the frontend receives the new state
(either via re-fetching after a swap response or via an SSE event — decision
in plan), and calls `AvatarManager.loadAvatar(new_glb_path)`. Three.js
disposes the old one and loads the new.

## Tools state mechanics

The Plan #5 ControlPanel currently writes to `localStorage` keys
`nodeava.toggle.web_search` and `nodeava.toggle.wiki`, and the frontend
sends those booleans as `web_search` / `wiki` body fields on every LLM
request.

Plan #7 changes:
- The booleans live in `state.tools` (server-side, canonical)
- ControlPanel reads from `GET /v1/state` on mount, posts to `/v1/swap`
  with `kind: "tools"` on user toggle
- The agentic loop ignores any `web_search` / `wiki` fields in the request
  body (or, transitionally, accepts them as overrides but logs a deprecation)

The orchestrator state is canonical. Browser local-storage becomes a cache,
not a source of truth.

## VRAM reporting

Implementation lives in `services/orchestrator/orchestrator/system/residency.py`.
Single source of data: Ollama's `GET /api/ps`. The module:

1. Calls `<OLLAMA_URL>/api/ps` with a 1-second timeout.
2. For each entry in the response, computes the `residency` label
   (`gpu` / `split` / `cpu`) from the `size` and `size_vram` fields.
3. Returns the normalized structure that ends up in `GET /v1/state`'s
   `system.ollama` block.

No native GPU probes (no pynvml, no rocm-smi, no `nvidia-smi` shelling out).
This is a deliberate scope reduction from earlier drafts — Ollama already
knows authoritative answers to the questions the dashboard actually needs,
and adding native GPU libraries adds cross-platform packaging pain for
information that wouldn't change UX.

What we lose vs. native probes: a "total VRAM" / "free VRAM" reading
independent of Ollama. Trade-off accepted — the workshop demo focuses on
"what is Ollama actually doing right now," and Ollama's `/api/ps` answers
that directly.

Predictions ("will this swap fit?") are explicitly out of scope. Attendees
swap; the dashboard re-renders the residency chips; they observe what
Ollama decided. If Ollama offloaded the model to system memory, they see
a yellow `split` chip and feel the slower response. That's the teaching
moment.

For the `kind: openai-compatible` escape hatch (llama.cpp, vLLM, etc.):
the orchestrator has no introspection into those servers. The dashboard
shows "external server" badge with the URL. Attendees who want to know
GPU state on those servers use that server's own tools (e.g., `nvidia-smi`
in another terminal).

## Teaching scripts

`scripts/demos/` directory. Each script is small, self-contained, prints
what it's doing, and is **interactive** — meant to be run live in workshop,
not just read. Bash only (PowerShell parity not in scope).

### Interactivity model

Each script defaults to live interaction (typed prompts, microphone capture,
audio playback through speakers). Each also accepts a `--fixture` flag for
non-interactive runs against shipped sample inputs, so attendees with broken
mic permissions or facilitators doing a dry run can still demo.

Cross-platform audio handled by a tiny `scripts/demos/_audio.sh` helper
sourced by the scripts:

| OS detection | Record (5 s, 16 kHz, mono, S16_LE WAV)            | Playback                |
|--------------|---------------------------------------------------|-------------------------|
| Linux        | `arecord -d 5 -f S16_LE -r 16000 -c 1 <out.wav>`  | `aplay <file>`          |
| macOS        | `sox -d -c 1 -r 16000 -b 16 <out.wav> trim 0 5`   | `afplay <file>`         |
| Windows      | Out of scope (point users to WSL2 or `ffmpeg`)    | (same)                  |

Setup script checks for these tools at install time and prints install
hints if missing (`sudo apt install alsa-utils` / `brew install sox`).

### Scripts

- **`test-llm.sh`** — `read -p` for a user prompt; `curl -N` to Ollama's
  OpenAI-compatible endpoint with `stream: true`; pipe through a tiny SSE
  parser that prints tokens as they arrive. Shows token-by-token latency.
  `--fixture` uses a canned prompt ("Tell me about NodeAva").

- **`test-tts.sh`** — `read -p` for a phrase; POST to Kokoro with the
  currently-active voice (read from `GET /v1/state`); decode the returned
  PCM to a temp WAV; play through speakers. Optional `--voice <id>` overrides.

- **`test-stt.sh`** — Records 5 seconds from the default microphone (says
  "Recording — speak now…" with a visible countdown), POSTs the WAV to
  Whisper, prints the transcript. `--fixture` uses `assets/demos/sample-stt.wav`
  (a shipped fixture: "Hello NodeAva, what time is it?").

- **`test-pipeline.sh`** — The full digital-human-in-bash. Record 5 s of
  mic input → Whisper transcript → Ollama (active brain, with personality
  system prompt from `/v1/state`) → Kokoro (active voice) → play through
  speakers. End-to-end loop in a shell pipeline. This is the script that
  proves the parts can be assembled by hand.

- **`test-orchestrator.sh`** — Menu: `[1] show state, [2] swap brain,
  [3] swap voice, [4] swap personality, [5] toggle tool, [q] quit`. Each
  menu item prompts for the relevant value and POSTs to `/v1/swap`. Useful
  for the "see how the same prompt behaves differently" portion of
  Demo 16 — run `test-pipeline.sh`, then swap brain, then run pipeline
  again to hear the difference.

- **`list-models.sh`** — Non-interactive. Prints the catalog
  (`curl /v1/catalog | jq`) so attendees see what's available. Highlights
  unavailable items (model not pulled, API key missing) in yellow.

### Shared conventions

Every script has a top comment block stating:
- Which workshop slide it backs (e.g., "Slide 14: Test text-to-speech")
- What to teach with it (the workshop point, in one sentence)
- How to invoke (with and without `--fixture`)

All endpoint URLs come from environment variables (`OLLAMA_URL`, `TTS_URL`,
`STT_URL`, `ORCH_URL`) with sensible defaults pointing at localhost
ports. A customized install (different host/ports) still works without
edits.

Recording feedback is visible: each script prints a countdown ("Recording
in 3… 2… 1… GO") and a tone (terminal bell) when recording starts/stops,
so attendees know when to speak.

## Cross-platform notes

**Ollama runs natively on every platform.** Orchestrator, Kokoro, and Whisper
run in Docker (Mac arrangement is unchanged; Linux/WSL2 gains the
`host.docker.internal:host-gateway` extra_hosts entry). One install
pattern, one config — no per-platform Docker GPU variants.

| Platform                  | Ollama install                                              | GPU                |
|---------------------------|-------------------------------------------------------------|--------------------|
| Linux + NVIDIA            | `curl -fsSL https://ollama.com/install.sh \| sh`            | CUDA (Ollama auto) |
| Linux + AMD (ROCm-capable)| Same installer, ROCm auto-detected                          | ROCm               |
| Windows (any GPU)         | **WSL2 → same as Linux**                                    | Whatever WSL2 sees |
| macOS Apple Silicon       | `brew install ollama`                                       | Metal              |

**Power-user escape hatch (all platforms):** any OpenAI-compatible local
server (llama.cpp, vLLM, TGI, LocalAI) can be added as a `kind:
openai-compatible` catalog entry. The workshop teaching path does not cover
this; it's documented in CLAUDE.md with a commented example in `catalog.yml`
for attendees who want to bring their own.

The migration removes the AMD-Vulkan llama.cpp path that the existing
`docker-compose.gpu-amd.yml` offers as a default. Ollama uses ROCm on AMD,
which is a stricter requirement. Attendees with non-ROCm AMD GPUs (or who
prefer Vulkan for any reason) can fall back via the power-user escape
hatch — bring up llama.cpp + Vulkan themselves, add a catalog entry. The 8
GB GPU workshop floor still holds for Ollama on any of the three GPU
paths above.

## Out of scope

- Dashboard UI rendering (Plan #8)
- Editing catalog/personality text via UI (Plan #8 polish or later)
- Multi-user / per-session state (single-user localhost stays)
- The senior-colleague escalation router (slide 32) — separate plan
- Benchmark feature (Plan #10)
- Authenticated endpoints
- The installer downloading the bundled models (Plan #9 reuses our catalog
  to know what to `ollama pull`)
- PowerShell variants of the teaching scripts (Windows attendees use WSL2)
- Native Windows support outside WSL2 (any GPU)
- **Predicting** whether a swap will fit in VRAM. We report what Ollama
  decided after the swap; we do not forecast before it.
- Native GPU memory probes (pynvml, rocm-smi, nvidia-smi). Ollama's
  `/api/ps` is our only VRAM data source.

## Risks & open questions

1. **Ollama in Docker on Apple Silicon**: Docker Desktop has no GPU
   passthrough to Metal. So on Mac, Ollama must run **natively** (brew
   install) outside Docker; only the orchestrator + nginx + Kokoro + Whisper
   run in containers. This matches today's macOS arrangement (per
   CLAUDE.md), so the only change is replacing `llama-server` with `ollama serve`.

2. **AMD-Vulkan attendees lose the default path**: the existing
   `docker-compose.gpu-amd.yml` uses llama.cpp Vulkan. After migration, the
   default AMD path is Ollama on ROCm, which requires a ROCm-supported GPU.
   Mitigation: the power-user escape hatch (`kind: openai-compatible`
   catalog entry pointing at an attendee-managed llama.cpp + Vulkan
   container) is documented for the attendees who need it. Workshop teaching
   path doesn't cover this; advanced attendees opt in.

3. **Model pull at workshop time** is slow over conference wifi. Mitigation:
   pre-loaded USB sticks (already in the workshop plan per memory). Default
   catalog only references models small enough to pull in a few minutes if
   wifi works.

4. **Personality preset = system prompt only** in v1. No temperature, no
   tool whitelist, no per-personality model preference. Sufficient for the
   workshop demos. Easy to extend later.

5. **Catalog file evolution**: if we add a new `kind` later, existing state
   files might reference IDs that no longer validate. State load falls back
   to catalog defaults if the active ID is missing — covered.

6. **Mic permissions on Linux** (for the teaching scripts): pulseaudio /
   pipewire vs. raw ALSA can be inconsistent across attendee distros. The
   recording helper script prints a clear error and `--fixture` fallback
   instruction if the recording command fails.

7. **Ollama not installed** on the host: orchestrator startup probes
   `<OLLAMA_URL>/api/tags` and logs a clear error if Ollama isn't
   reachable. `GET /v1/state` returns `system.ollama.reachable: false`
   so the dashboard shows "Ollama not running — install it from
   ollama.com." Attendee runs the install command, restarts the
   orchestrator (or just waits — health check polls), and proceeds.

## Success criteria

Plan #7 is done when:

1. Host has Ollama installed and `qwen3:4b` pulled.
   `docker compose up -d orchestrator tts stt searxng` brings up a stack
   that boots cleanly and successfully reaches the host Ollama via
   `host.docker.internal:11434`.
2. `curl localhost:8082/v1/catalog | jq '.brains | length'` returns ≥ 4
   (qwen3-4b + smollm2-360m + at least 2 cloud entries, with cloud entries
   showing `available: false` if no API keys set).
3. `curl localhost:8082/v1/state` returns the current selections + a
   `system.ollama` block listing each currently-loaded model with its
   `residency` field (`gpu` / `split` / `cpu`).
4. `curl -X POST localhost:8082/v1/swap -d '{"kind":"brain","id":"smollm2-360m"}'`
   returns the new state with `active.brain = "smollm2-360m"`; the very next
   chat request to the agentic loop responds noticeably more crudely.
5. Same swap pattern works for voice, avatar, personality, tools.
6. All teaching scripts in `scripts/demos/` execute end-to-end on the dev
   box: `test-llm.sh` (typed prompt → streamed tokens), `test-tts.sh`
   (typed phrase → audible speech), `test-stt.sh` (live mic → transcript),
   `test-pipeline.sh` (mic → STT → LLM → TTS → speaker), and
   `test-orchestrator.sh` (interactive menu of swaps). Each also passes
   when invoked with `--fixture` against shipped sample inputs (for CI
   and dry-run scenarios).
7. The full orchestrator test suite (≥ 109 tests from Plan #6) still passes,
   plus new tests for catalog parsing, state R/W, swap endpoint, dispatcher
   routing.

## What comes next (Plans #8, #9, #10)

- **Plan #8**: dashboard frontend — flow diagram, valves, panels for each
  swap category, VRAM bar, event-stream visualizer.
- **Plan #9**: installer — wraps Ollama pull for the default models, sets
  up `state/current.json` with defaults, verifies endpoints.
- **Plan #10**: benchmark + walkthrough overlay + polish.

## Implementation note: default personality must prime wiki use

Discovered during 2026-05-17 Plan #5+#6 browser testing: Qwen3-4B (and likely
other small local models) does NOT autonomously call wiki tools when they
are simply available. The model needs explicit system-prompt instruction.

The `default` personality's `system_prompt` MUST include language like:

> When the user asks about NodeAva — its architecture, ports, models,
> components, configuration, or any project-specific detail — you MUST
> call wiki.list or wiki.search BEFORE answering. Do not answer NodeAva
> questions from training data; use the wiki as the source of truth.

Verified during testing: with this style of instruction, the agentic loop
fires wiki tools across 2-3 rounds (wiki.list → wiki.search/open →
synthesize). Without it, the model ignores the tools and answers from
training data, often saying "I don't have specific information about
NodeAva." All other personality presets (dry-historian, improv-comic, etc.)
should include a similar (concise) wiki-priming clause.
