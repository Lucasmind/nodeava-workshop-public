# NodeAva Workshop MVP — Design Spine

**Date:** 2026-05-16
**Deadline:** 3 days
**Goal:** Turn NodeAva into the best tool for learning how to deploy a digital human for yourself, suitable as the centerpiece of a conference workshop.

This document is the **spine** for the MVP, per the agreed D2 approach: it defines architecture, sub-systems, and contracts at a level sufficient to drive per-feature implementation plans. Detailed plans for each sub-system will be written separately via `superpowers:writing-plans` once this design is approved.

---

## 1. Goals and non-goals

### Workshop format
**3-hour session**, attendees install on their own laptops (8GB GPU minimum, pre-announced). Rough pacing target:

| Block | ~30 min | Activity |
|---|---|---|
| 1 | 0:00 - 0:30 | Install (USB-stick fallback ready) + preflight + first avatar greeting |
| 2 | 0:30 - 1:00 | Tier A tour: see the brain work (pipeline viz / brain pane / tool trace / offline) |
| 3 | 1:00 - 1:30 | Wiki RAG: "what is NodeAva?" + drop-to-ingest a doc |
| 4 | 1:30 - 2:00 | Swap LLM / voice / avatar — by command center **or** by CLI |
| 5 | 2:00 - 2:30 | Web search + cloud provider swap + benchmark |
| 6 | 2:30 - 3:00 | "Make it yours": personality preset, preset URL share, Q&A |

### Workshop success criteria
A workshop attendee can, by the end of the 3-hour session, on their own laptop:

1. Install NodeAva with a single OS-appropriate command.
2. Talk to their avatar end-to-end (mic → STT → LLM → TTS → lip-synced 3D head).
3. **See** what's happening: pipeline visualizer with live timings, model's thinking, tool calls, offline status.
4. Ask "what is NodeAva?" and get a coherent answer from the preloaded wiki.
5. Swap the LLM, TTS voice, or avatar via the command center.
6. Switch from local LLM to a cloud provider (Anthropic/OpenAI/Groq) with their own API key, without restarting.
7. Run a one-button benchmark and see token/sec, TTS RTF, first-spoken-word latency, peak VRAM.
8. Trigger a web search and watch the tool-call trace.
9. Drop a file into the wiki, ask a question about it.

### Non-goals for this MVP (parked for v1.1+)
- Voice cloning (Chatterbox / XTTS)
- Vision input (multimodal LLM)
- Screen capture / "look at my screen"
- Two-avatar debate mode
- Side-by-side model comparison
- Self-improving wiki (conversation → wiki append, lint, gap-find)
- Marp slide generation
- Quantization slider explainer
- Windows + AMD GPU support — investigated only if Day 3 has slack
- In-browser avatar creation (refer attendees to Ready Player Me)

### Pedagogical priority
Features that make the *pipeline visible and swappable* > features that add raw capability. Workshop attendees should leave understanding how a digital human is *assembled*, not just having used one.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                  Browser (localhost:3000)                            │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Avatar canvas        Command Center        Tier A panels      │ │
│  │  (TalkingHead)        (model/voice/         (pipeline viz,     │ │
│  │                        avatar/wiki/         brain pane,        │ │
│  │                        provider)            tool trace,        │ │
│  │                                             offline badge)     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│  Orchestrator.js → STTManager, LLMClient, TTSManager, WikiClient    │
└────────────┬─────────────────────────────────────────────────────────┘
             │
             │ /api/* (nginx in prod, vite proxy in dev)
             │
             ▼
┌────────────────────────────────────────────────────────────────────┐
│  Local services (Docker or native)                                 │
│                                                                    │
│   ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│   │ /api/stt        │  │ /api/llm  →     │  │ /api/tts         │  │
│   │ whisper.cpp     │  │ nodeava-orch    │  │ Kokoro-FastAPI   │  │
│   │  (Vulkan/Metal) │  │ (LiteLLM +      │  │  (CUDA/ROCm/MPS) │  │
│   └─────────────────┘  │  agentic loop)  │  └──────────────────┘  │
│                        └──┬──────────────┘                         │
│                           │                                        │
│              ┌────────────┴────────────┐                           │
│              │                         │                           │
│   ┌──────────▼─────────┐  ┌────────────▼────────┐                  │
│   │ Local llama-server │  │ Cloud provider via  │                  │
│   │ (Qwen3-4B default) │  │ LiteLLM (Anthropic, │                  │
│   │                    │  │ OpenAI, Groq, ...)  │                  │
│   └────────────────────┘  └─────────────────────┘                  │
│                                                                    │
│   ┌────────────────────────────────────────────┐                   │
│   │ /api/wiki  (filesystem-backed RAG)         │                   │
│   │   wiki/index.md, wiki/concepts/, ...       │                   │
│   └────────────────────────────────────────────┘                   │
│                                                                    │
│   ┌────────────────────────────────────────────┐                   │
│   │ /api/command  (service control + config)   │                   │
│   │   model swap, voice swap, preset load      │                   │
│   └────────────────────────────────────────────┘                   │
└────────────────────────────────────────────────────────────────────┘
```

### New components introduced by this MVP

1. **`nodeava-orch`** — a stripped-down, NodeAva-flavored fork of the LLMRunners FastAPI orchestrator. Sits between the frontend and the LLM (local or cloud). Hosts the agentic tool loop, LiteLLM provider abstraction, wiki tools, and SSE event stream for the Tier A visualizers.
2. **Command center backend** — additional routes inside `nodeava-orch` (not a separate service) that expose model/voice/avatar/wiki state and accept swap commands. Routes live in `services/orchestrator/routes/command.py`. Localhost-only by default.
3. **Wiki RAG store** — a `wiki/` directory in the repo, plus a tool surface (`wiki.search`, `wiki.open`, `wiki.list`) registered with the orchestrator.
4. **Frontend command center UI + Tier A panels** — plain JS components consistent with existing Vite + vanilla approach (no framework introduction).

### Things that stay
- Frontend `Orchestrator.js` pipeline coordinator (state machine + sentence streaming).
- `TalkingHead` avatar.
- `vad-web` + `whisper.cpp` for STT.
- `Kokoro-FastAPI` for default TTS.
- Vite dev / nginx prod proxy split.

---

## 3. Sub-systems

Each sub-system below has: **purpose**, **contract** (interface or shape), **key files**, **dependencies**, **day target**, and **open questions** if any. Implementation plans for each will be written via `superpowers:writing-plans` after this design is approved.

### 3.1 nodeava-orch — orchestrator integration + improvements

**Purpose:** Single LLM-facing service that handles agentic tool calls, provider switching (local ↔ cloud), wiki/web tool execution, and emits structured SSE events that the Tier A panels render.

**Origin:** Fork/port of the LLMRunners orchestrator (`services/orchestrator/main.py`, ~1150 LOC), simplified for the NodeAva use case and tightened per the pre-mortem.

**Contract:**
- OpenAI-compatible `POST /v1/chat/completions` (streaming and non-streaming).
- Accepts extra body fields: `web_search: bool`, `wiki: bool`, `thinking: bool`, `provider: "local" | "anthropic" | "openai" | ...`.
- Emits SSE events of types: `token`, `tool_call_start`, `tool_call_end`, `thinking_token`, `final_done`, `stage_timing`.
- Pluggable tool registry — tools register with a `name`, `schema`, `handler(args)` triple. Initial tools: `browser.search`, `browser.open`, `browser.find`, `wiki.search`, `wiki.open`, `wiki.list`.

**Improvements applied from the pre-mortem:**
- Dedupe `agentic_chat` and `stream_agentic` into one async generator that yields typed events.
- Stream `tool_call_start` / `tool_call_end` events during tool rounds (does NOT buffer the whole loop).
- Replace `_backend_type_cache` substring-match with explicit `provider_kind` config.
- Move page cache to Redis (shared with SearXNG if used).
- Add `/v1/metrics` endpoint: per-request token counts, tool round count, tool latencies, cache hit rate.

**Key files:**
- `services/orchestrator/main.py` (FastAPI app + routing + agentic loop)
- `services/orchestrator/providers/` (LiteLLM wrapper + per-provider quirks)
- `services/orchestrator/tools/` (registry + browser tools + wiki tools)
- `services/orchestrator/cache.py` (Redis-backed page cache)
- `services/orchestrator/events.py` (SSE event schema)

**Dependencies:** LiteLLM (3.2), wiki tools (3.3).

**Day target:** Day 1 (plumbing only — tool execution wired but UI not necessarily there).

**Open questions:**
- SearXNG bundled into NodeAva for local web search, or rely on a hosted endpoint? Bundling adds another container (~250MB image) but preserves the "fully local" pitch. **Default: bundle**, with an env var to point at an external SearXNG.
- Wiki tools live in the orchestrator process or in their own service? **Default: in-process** for v1; revisit if wiki grows large.

---

### 3.2 LiteLLM adapter — cloud provider switch

**Purpose:** Allow attendees to flip from local llama-server to a cloud LLM (their own API key) with no restart, no frontend change.

**Why LiteLLM:** Single library that translates OpenAI request format to/from Anthropic, OpenAI, Groq, Together, Mistral, Ollama, etc. Solves tool-format differences (Anthropic `tool_use`/`tool_result` ↔ OpenAI `tool_calls`) and reasoning-content differences across providers in one place.

**Why NOT ClaudeCliAdapter from OfflineMailProcessor:** Subprocess-per-call (1-2s startup), no streaming, no tool calls, no multi-provider — breaks the streaming pipeline that feeds TTS sentence-by-sentence. Kept where it is for its current use; not reused here.

**Contract:**
- Inside `nodeava-orch`, a `Provider` abstraction with `chat(messages, tools, stream) -> AsyncIterator[Event]`.
- One built-in `LocalLlamaProvider` (talks to llama-server on localhost:8081).
- One `LiteLLMProvider` parameterized by `provider_name` + `model` + `api_key`.
- API keys come from request headers (`X-Provider-Key`) or env vars; never logged, never persisted server-side.

**UI surface (3.4 command center):**
- Provider dropdown: `Local` | `Anthropic` | `OpenAI` | `Groq` | (extensible).
- Per-provider model picker (curated list of recommended models).
- API key field (stored in browser localStorage, sent per-request).

**Reasoning visibility table** (drives the brain-pane fallback):

| Provider | Reasoning visible? | Brain-pane behavior |
|---|---|---|
| Local Qwen3 | Yes (`<think>` tags) | Stream into pane |
| Anthropic (extended thinking) | Yes | Stream into pane |
| OpenAI o1/o3 | No (hidden) | "Reasoning hidden by provider" placeholder |
| OpenAI gpt-4 / 4o | No (no reasoning mode) | Pane disabled |
| Groq | Model-dependent | Detect at request time |

**Key files:**
- `services/orchestrator/providers/local.py`
- `services/orchestrator/providers/litellm.py`
- `services/orchestrator/providers/__init__.py` (registry)

**Day target:** Day 1.

**Open questions:**
- Default cloud provider in the dropdown? **Default: Anthropic** (Claude Haiku for cost; user can override).

---

### 3.3 Wiki RAG (Karpathy-style)

**Purpose:** Give the avatar a maintained, on-disk knowledge base that it queries via tool calls. Preloaded with NodeAva self-knowledge so attendees can ask the avatar to explain itself.

**Approach:** Karpathy-style, not vector RAG. Two directories:

```
raw/                  immutable source documents (user drops files here)
wiki/
  index.md            top-level catalog, one-line summary per page
  log.md              append-only ingest/query timeline
  concepts/           concept articles (e.g. how TTS works)
  entities/           people/projects/things
  sources/            per-source summaries
  comparisons/        side-by-side comparison pages
```

**Q&A flow** (executed by the LLM via tool calls):
1. LLM calls `wiki.list()` or reads `wiki/index.md` to discover available pages.
2. LLM calls `wiki.open(path)` for 1-3 relevant pages.
3. LLM synthesizes answer with `[[wiki-link]]` references stripped before TTS reads aloud.

**Tool surface:**
- `wiki.search(query)` — full-text grep over the wiki, returns matching lines with page refs.
- `wiki.open(path, num_lines=200, cursor=0)` — paginated read.
- `wiki.list()` — returns `wiki/index.md` verbatim.

**Preloaded wiki — NodeAva self-knowledge (CRITICAL):**
- Compiled **once, offline, by a strong model** (Claude Opus or equivalent), then committed to the repo as a static artifact.
- Coverage: architecture overview, each pipeline stage, model choices, the four GPU profiles, how to use the command center, glossary of digital-human terms, "how do I..." FAQs.
- QA: hand-verify the first ~15 likely-question answers before workshop. These are the first-impression that determines whether attendees trust the system.

**Long-context tuning** (per agreed direction):
- llama-server flags: `-c 32768 --cache-type-k q4_0 --cache-type-v q4_0` (KV-cache quantization, ~4x memory reduction at minor quality cost).
- `wiki_max_pages_per_query = 3`, `wiki_max_tokens_per_page = 2000` (hard ceilings).
- Conversation history sliding window at 24K with summary keep-around.

**Drop-to-ingest flow** (workshop demo moment):
- User drags a file (PDF, URL, MD) into the command center.
- Backend writes to `raw/`, kicks off an LLM-driven compile step that creates/updates wiki pages.
- Compile uses **whichever LLM is currently configured** (local or cloud). With local Qwen3-4B this is slow but visible — pedagogical win.

**Key files:**
- `wiki/` (committed; preloaded)
- `raw/` (gitignored runtime dir)
- `services/orchestrator/tools/wiki.py`
- `services/wiki-compiler/` (offline script to (re)build wiki from sources)
- `scripts/build-self-wiki.sh` (one-shot: read NodeAva's own docs, generate wiki)

**Day target:**
- Preloaded wiki: **Day 0** (pre-work, before the 3-day clock).
- Wiki tools in orchestrator: Day 1.
- UI panel + drop-to-ingest: Day 2.

**Open questions:**
- Bracket-link rendering for TTS: strip on the way to TTS? Convert to footnotes? **Default: strip — avatar reads `[[NodeAva]]` as "NodeAva".**
- Wiki output is markdown, but for visible reading we need a renderer. Use a tiny markdown-to-HTML lib (e.g. `marked`) — already small.

---

### 3.4 Command center (web UI shell)

**Purpose:** The web surface that holds every other feature. The shell that attendees drive during the workshop.

**Layout:** Single page, three regions —

```
┌─────────────────────────────────────────────────────────────┐
│  Avatar canvas (large)        │  Tier A panel rail (right)  │
│                               │   • Pipeline visualizer     │
│                               │   • Brain pane              │
│                               │   • Tool trace              │
│                               │   • Offline badge           │
├─────────────────────────────────────────────────────────────┤
│  Command center (bottom drawer, collapsible)                │
│   [Provider] [Model] [Voice] [Avatar] [Wiki] [Benchmark]    │
│   [Reset] [Preset URL] [Walkthrough]                        │
└─────────────────────────────────────────────────────────────┘
```

**Implementation approach:** Plain JS + Vite, consistent with existing codebase. No framework introduction (no React/Vue/Svelte). Each panel is a class instance in `frontend/src/ui/commandCenter/`.

**Security defaults:**
- All command center endpoints bind to **127.0.0.1 only** by default.
- LAN sharing is opt-in via a `--lan` flag on the start script + a generated single-use token. Documented as a separate "share with phone" feature.
- API keys (for cloud LLM) stored in `localStorage` keyed by provider name, never sent to backend except per-request.

**Key files:**
- `frontend/src/ui/commandCenter/` (UI components)
- `services/orchestrator/routes/command.py` (model/voice/avatar/preset endpoints)

**Day target:** Day 2 (shell + most panels). Wiki and provider panels rely on Day-1 plumbing.

---

### 3.5 Tier A visualizers (all four)

**Purpose:** Make the pipeline visible. The workshop's identity feature.

**The four panels:**

1. **Pipeline visualizer** — horizontal flow diagram with 4 nodes (Mic → STT → LLM → TTS → Mouth). Each node has a status dot (idle/active/done) and a latency badge populated from per-stage timings the orchestrator emits via SSE.
2. **Brain pane** — dim, side-scrolling stream of `<think>` content (or extended-thinking blocks). Visible only when the active provider exposes reasoning. Falls back to a "reasoning hidden by this provider" placeholder for OpenAI o-series.
3. **Tool trace** — vertical strip of tool calls as they happen: `🔍 search("kokoro")` → `📚 wiki.open("tts.md")` → ... Each entry expandable to see arguments and result preview. Populated by `tool_call_start` / `tool_call_end` SSE events.
4. **Offline badge** — green dot when configured-offline (provider=local, no web_search active). Red flash if any provider is non-local. **Honest copy: "configured offline"**, not "verified offline" — actual outbound-traffic verification is out of scope for MVP.

**Plumbing required (all Day 1):**
- Orchestrator SSE event types defined and emitted.
- Frontend SSE parser routes events to the right panel.
- Per-stage timing instrumentation in `Orchestrator.js` (STT start/end, first LLM token, first TTS audio chunk, mouth-starts-moving).

**Key files:**
- `frontend/src/ui/panels/PipelineVisualizer.js`
- `frontend/src/ui/panels/BrainPane.js`
- `frontend/src/ui/panels/ToolTrace.js`
- `frontend/src/ui/panels/OfflineBadge.js`
- `frontend/src/pipeline/Orchestrator.js` (instrumentation)
- `services/orchestrator/events.py` (event schema)

**Day target:** Day 2 (after Day-1 plumbing).

---

### 3.6 Model / voice / avatar swap

**Purpose:** Attendees can swap any pipeline component live from the command center.

**LLM swap:**
- Curated list of recommended models per hardware tier (1.5B / 4B / 8B / 14B Q4_K_M).
- Hardware preflight runs on first launch, sets recommended tier as default.
- Swap = stop llama-server container/process, swap model file, restart, wait for `/health`. UI shows "Loading model..." with a determinate progress bar driven by `/health` polling.
- Mid-conversation swap drops conversation history with a confirm dialog.

**TTS voice swap:**
- Kokoro voices (≈50 available) exposed via existing Kokoro-FastAPI endpoint.
- Voice picker in command center. Live preview button speaks a sample sentence.
- Out-of-scope for MVP: alternative TTS engines (Piper, XTTS) — would break lip-sync timestamp contract.

**Avatar swap:**
- TalkingHead supports any RPM-compatible `.glb` file. Drop into `frontend/public/avatars/`, picker lists them.
- Ship 3-4 curated avatars + clear instructions for getting your own from Ready Player Me.

**Key files:**
- `services/orchestrator/routes/command.py`
- `services/orchestrator/services/model_swap.py`
- `frontend/src/ui/commandCenter/ModelPicker.js`
- `frontend/src/ui/commandCenter/VoicePicker.js`
- `frontend/src/ui/commandCenter/AvatarPicker.js`
- `scripts/hardware-preflight.{sh,ps1}`

**Day target:** Day 2.

---

### 3.7 Cloud provider UI

**Purpose:** Surface for the LiteLLM adapter (3.2).

**Contract:**
- Provider dropdown writes `provider` field on every chat request.
- API-key field per provider stored in `localStorage`.
- Visible per-token cost estimate when cloud provider is active (best-effort from LiteLLM's pricing table).

**Day target:** Day 2 (UI). Backend on Day 1.

---

### 3.8 Fast benchmark

**Purpose:** One-button "how fast is my digital human?" — measure and display key performance numbers.

**Metrics (30-sec test):**
- LLM token generation rate (tok/s)
- LLM prompt processing rate (tok/s)
- TTS real-time factor (RTF; audio-seconds-generated / wall-clock-seconds)
- First-spoken-word latency (mic-stop → first audio sample played)
- Peak VRAM (where measurable)
- Active context size / budget

**Implementation:**
- A fixed-prompt test ("Tell me about the moon in three sentences.") triggered by the benchmark button.
- Per-stage timings are already being captured for the pipeline visualizer (3.5) — benchmark just averages them over a few runs and renders a result card.
- Result card is shareable (copy-to-clipboard as markdown).

**Key files:**
- `frontend/src/ui/panels/Benchmark.js`
- Reuses orchestrator events from 3.5.

**Day target:** Day 3.

---

### 3.9 Installer / preflight / reset

**Purpose:** Workshop attendees go from `curl | bash` (or PowerShell equivalent) to a running avatar in <15 minutes.

**Components:**

- **Hardware preflight:** Check GPU (NVIDIA/AMD/Apple/none), VRAM, RAM, disk, Docker version, network reachability. Fail loudly with specific guidance.
- **Per-OS quickstart scripts:**
  - `scripts/install-mac.sh` (extension of existing setup-mac.sh)
  - `scripts/install-linux.sh` (wraps `detect-gpu.sh` + docker compose)
  - `scripts/install-windows.ps1` (WSL2 + NVIDIA; AMD parked)
- **Reset-to-defaults:** Single command that restores model/voice/avatar/preset to ship defaults. Available from command center button and CLI script.
- **Save/share preset URL:** Encode `{provider, model, voice, avatar, system_prompt}` into a short URL. Attendees can share working setups.

**Pre-shipped artifacts** (avoid conference wifi):
- Model files in a USB-stick distribution: Qwen3-4B Q4, Kokoro-82M, Whisper base.en, default avatars.
- A `--from-usb /path` flag on the installer that skips downloads.

**Key files:**
- `scripts/install-*.{sh,ps1}`
- `scripts/preflight.{sh,ps1}`
- `scripts/reset-defaults.sh`
- `frontend/src/ui/commandCenter/Reset.js`
- `frontend/src/ui/commandCenter/PresetShare.js`

**Day target:** Day 1 (skeleton + preflight), Day 3 (per-OS polish + clean-VM smoke tests).

---

### 3.10 Walkthrough / tutorial overlay

**Purpose:** Workshop runs from this — a guided overlay that highlights UI elements step-by-step so the presenter doesn't have to repeat "click the dropdown labeled..." 30 times.

**Implementation:**
- Plain JS overlay with backdrop + spotlight + step text.
- Steps anchored to stable `data-tour="..."` attributes on UI elements (added during component build so they don't drift).
- Skippable per step; can be invoked from command center button (`Walkthrough → Start`).
- Initial walkthrough: "First five minutes with NodeAva" covering Listen → Speak → Swap voice → Wiki query → Provider swap.

**Key files:**
- `frontend/src/ui/walkthrough/Tour.js`
- `frontend/src/ui/walkthrough/tours/first-five-minutes.json`

**Day target:** Day 3.

---

### 3.11 State machine refactor + filler-speech UX

**Purpose:** Existing 5-state machine (IDLE / LISTENING / TRANSCRIBING / THINKING / SPEAKING) doesn't accommodate agentic loops or wiki queries. Refactor before Tier A panels are built or panels will reference states that don't exist yet.

**Proposed states:**
```
IDLE → LISTENING → TRANSCRIBING → THINKING ↔ TOOL_CALLING ↔ WIKI_QUERY → SPEAKING → IDLE
```

- `TOOL_CALLING` — agent has issued a tool call, awaiting result.
- `WIKI_QUERY` — sub-state of TOOL_CALLING for wiki tools (distinct UI affordance).
- Both can re-enter THINKING repeatedly across an agentic loop.

**Interruption / barge-in policy** (explicit decision, not implicit):
- User barge-in during TOOL_CALLING or WIKI_QUERY: **cancel the current tool round, drop in-flight results, transition to TRANSCRIBING.** Avatar acknowledges with a brief "Hold on—" filler.
- User barge-in during SPEAKING: **stop TTS playback immediately**, transition to TRANSCRIBING (existing behavior).

**Filler speech UX:**
- On entering TOOL_CALLING, after 800ms, queue a short filler ("Let me look that up..." / "One moment...") into the TTS pipeline. Cancel if tool completes before filler audio is generated.

**Key files:**
- `frontend/src/app/state.js`
- `frontend/src/pipeline/Orchestrator.js`

**Day target:** Day 1.

---

## 4. Cross-cutting concerns

### CLI parity with the command center (workshop dual-track)

**Every operation in the command center MUST also be doable from a shell script.** Workshop attendees split into two tracks based on preference:

- **GUI track:** click around the command center.
- **CLI track:** run the same operation from `scripts/` — for attendees who want to see what's actually happening under the hood.

Pedagogically critical: the CLI track is where attendees learn that "swap a model" is just an HTTP POST + a process restart, not magic. The same scripts also let presenters demo from a terminal on the projector.

**Required CLI scripts** (parity with command center actions):

| Command center action | CLI counterpart |
|---|---|
| Swap LLM model | `scripts/swap-model.sh <model-name>` |
| Swap TTS voice | `scripts/swap-voice.sh <voice>` |
| Swap avatar | `scripts/swap-avatar.sh <avatar.glb>` |
| Switch provider | `scripts/set-provider.sh <local\|anthropic\|openai\|groq> [--model X]` |
| Load preset | `scripts/load-preset.sh <preset-url-or-file>` |
| Run benchmark | `scripts/benchmark.sh` |
| Reset to defaults | `scripts/reset-defaults.sh` |
| Drop file into wiki | `scripts/ingest.sh <file-or-url>` |
| Trigger web search | `scripts/ask.sh --search "query"` |
| Health check all services | `scripts/health.sh` |

**Contract:** each script is a thin wrapper that POSTs to the same `nodeava-orch` endpoint the command center uses. No business logic in the script — pure curl-and-jq style. PowerShell equivalents (`.ps1`) for Windows attendees.

**Day target:** Day 2 (alongside their UI counterparts).

### Long context tuning
- Default llama-server flags: `-c 32768 --cache-type-k q4_0 --cache-type-v q4_0`.
- Hard ceilings: wiki ≤ 3 pages × 2000 tokens; conversation sliding window at 24K with summary.
- Documented in install script outputs so attendees know why they're getting these settings.

### Security
- Command center backend binds 127.0.0.1 only by default.
- `--lan` mode requires explicit flag + generated bearer token.
- API keys never logged; visible "your key stays in your browser" hint in the provider UI.
- Workshop slides include a "what this software can do to your machine" callout.

### Observability
- `/v1/metrics` endpoint on orchestrator returns Prometheus-text-ish (no Prometheus dependency required).
- Frontend dev-mode `?debug=1` enables an extra panel with raw event stream.

### Failure modes
- Cloud provider unreachable → fall back to local with a visible warning banner.
- Local llama-server crash → command center shows error, restart button visible.
- Wiki query returns no relevant pages → agent says so explicitly, doesn't hallucinate.
- TTS service down → switch to text-only mode with banner.

### Windows + AMD
Parked. Add a note in README's "supported configurations" table referencing this design's stance. Revisit only if Day 3 has slack.

---

## 5. Day-by-day plan

| Day | Theme | Items |
|---|---|---|
| **Day 0 (pre-clock)** | Wiki seed | Compile NodeAva self-knowledge wiki using strong model; commit artifact. QA top 15 likely questions. |
| **Day 1** | Invisible plumbing | (a) nodeava-orch fork with deduped agentic loop and SSE event schema. (b) LiteLLM provider adapter + Local provider. (c) State machine refactor (TOOL_CALLING / WIKI_QUERY) + filler speech. (d) Wiki tools in orchestrator. (e) Hardware preflight + installer skeleton. |
| **Day 2** | Visible scaffolding | (a) Command center shell (panels + bottom drawer). (b) All four Tier A panels (pipeline visualizer, brain pane, tool trace, offline badge). (c) Model/voice/avatar swap UI **and matching CLI scripts** (CLI parity). (d) Provider swap UI + CLI. (e) Wiki drop-to-ingest UI + `scripts/ingest.sh`. |
| **Day 3** | Completion + polish | (a) Walkthrough overlay. (b) Benchmark button. (c) Preset URL share + reset-to-defaults. (d) Per-OS install polish + clean-VM smoke tests. (e) README rewrite per-OS. (f) **If slack remains, pick at most one from:** Windows+AMD path, voice clone PoC. |

---

## 6. Risk register (from the pre-mortem; mitigations baked in)

| Risk | Mitigation in design |
|---|---|
| Claude wrapper isn't usable | LiteLLM adapter (3.2) |
| Tier A blocked on orchestrator changes | Day 1 plumbing precedes Day 2 panels |
| Latency feels broken | 8GB GPU floor + filler speech (3.11) |
| Cross-OS installer drift | Day-1 skeleton + Day-3 clean-VM tests + USB stick fallback |
| Wiki first-impression | Day-0 pre-compile with strong model + QA top 15 questions |
| Command center is RCE | Localhost-only default + opt-in LAN mode |
| Reasoning hidden by some providers | Brain pane has explicit fallback state (3.2 table) |
| Tool format differences | LiteLLM normalizes |
| Streaming required end-to-end | Day-1 SSE event schema; ClaudeCliAdapter explicitly NOT reused |
| Context overflow | Long-context defaults + hard ceilings in wiki tools |

---

## 7. Out of scope (parked for v1.1)

Documented here so we don't sneak them in mid-MVP and don't lose them after:

- Voice cloning (Chatterbox / XTTS)
- Vision input (multimodal LLM, e.g. Qwen2.5-VL)
- Screen capture / "look at my screen"
- Two-avatar debate mode
- Side-by-side model comparison
- Self-improving wiki (conversation-append, lint, gap-find)
- Marp slide generation
- Quantization slider explainer
- Windows + AMD GPU support
- In-browser avatar creation
- Persistent user memory across sessions
- LAN-share QR code feature (planned, but post-MVP)

---

## 8. Acceptance — workshop dress rehearsal

Before the workshop, run the **dress rehearsal scenario** on a clean VM per OS:

1. Run installer → preflight passes → services up.
2. Avatar speaks first sentence within 15s of mic permission grant.
3. Pipeline visualizer shows latency on all four stages.
4. "What is NodeAva?" → coherent wiki-sourced answer with brain pane visible.
5. Swap voice → preview plays. Swap avatar → renders. Swap LLM model → reloads.
6. Switch provider to Anthropic with a test key → next message routed through cloud, brain pane shows extended thinking.
7. "Search the web for today's news" → tool trace populates, search results surface, final answer cites URLs.
8. Drop a PDF into command center → wiki gains a new page → ask a question about it.
9. Benchmark button → result card renders, shareable.
10. Reset button → returns to ship defaults.
11. **Repeat steps 5-9 from the CLI** (`scripts/swap-model.sh`, `scripts/set-provider.sh`, `scripts/ingest.sh`, etc.) — verify CLI parity with the command center.

If any step fails on a tested OS, that's a blocker, not a polish item.

---

## Next steps

1. **You review this document.** Anything missing, wrong-sized, or wrong-priority gets called out.
2. **I revise** if needed.
3. **Transition to `superpowers:writing-plans`** for the first implementation plan. Recommended order of plans: (a) State machine + orchestrator scaffolding, (b) LiteLLM provider, (c) Wiki tools + preloaded wiki, (d) Tier A SSE event schema + panels, (e) Command center shell, (f) remaining Day-3 features.
