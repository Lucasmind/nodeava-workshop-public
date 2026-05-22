# NodeAva — Development Guide

Self-contained digital avatar that runs entirely on one machine. No cloud APIs.

## Architecture

3 Docker services + Ollama (on host) behind nginx:

```
Browser (localhost:3000)
  └── nginx ──┬── /api/stt/ ──► whisper.cpp (port 8080)        [Vulkan]
              ├── /api/tts/ ──► Kokoro-FastAPI (port 8880)      [CUDA/ROCm]
              └── /api/llm/ ──► Orchestrator (port 8082)
                                 ├─► LM Studio on host (:1234, native /api/v0)  [default, Plan #11]
                                 └─► Ollama on host (:11434)                    [LLM_BACKEND=ollama]
```

- **Frontend**: Vite + Three.js + TalkingHead + VAD-web (browser-based orchestrator)
- **LLM**: LM Studio on host (native `/api/v0` API; whole library auto-discovered) OR
  Qwen3-4B via Ollama — selected by `LLM_BACKEND` (see `docs/lmstudio-runbook.md`)
- **TTS**: Kokoro-82M via Kokoro-FastAPI (returns PCM + word timestamps)
- **STT**: Whisper base.en via whisper.cpp (Vulkan)
- **Orchestrator**: OpenAI-compatible proxy + agentic tool loop + command center backend

## Key Files

| File | Purpose |
|------|---------|
| `frontend/src/pipeline/Orchestrator.js` | Main pipeline: LLM streaming → thinking filter → sentence split → TTS queue |
| `frontend/src/app/config.js` | All configuration: endpoints, system prompt, VAD thresholds |
| `frontend/src/llm/LLMClient.js` | OpenAI-compatible SSE streaming client |
| `frontend/src/tts/TTSManager.js` | Kokoro-FastAPI client, PCM decoding, timestamp mapping |
| `frontend/src/stt/STTManager.js` | VAD (Silero) + Whisper transcription |
| `frontend/src/avatar/AvatarManager.js` | TalkingHead wrapper, 3D model, lip sync |
| `docker-compose.yml` | Base service definitions |
| `docker-compose.gpu-nvidia.yml` | NVIDIA CUDA overrides |
| `docker-compose.gpu-amd.yml` | AMD Vulkan + ROCm overrides |

## Development

```bash
# Frontend dev server (hot reload)
cd frontend && npm install && npm run dev

# Services (need GPU profile)
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml up stt tts llm
```

Vite dev proxies: STT → localhost:8080, TTS → localhost:8880, LLM → localhost:8081

## GPU Profiles

- **NVIDIA**: `docker-compose.gpu-nvidia.yml` — CUDA for LLM+TTS, Vulkan for STT
- **AMD**: `docker-compose.gpu-amd.yml` — Vulkan for LLM+STT, ROCm for TTS (built from `docker/kokoro-rocm/Dockerfile`)
- **Windows + AMD**: Not supported (Docker Desktop limitation)

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

## Port Mappings

| Service | Internal | External |
|---------|----------|----------|
| Frontend/nginx | 80 | 3000 |
| STT (whisper.cpp) | 8080 | 8080 |
| Orchestrator | 8082 | 8082 |
| TTS (Kokoro-FastAPI) | 8880 | 8880 |
| Ollama (host process, not in Docker) | 11434 | 11434 |

## Vite/ONNX Compatibility (DO NOT CHANGE)

- `vad-web` is CJS: must NOT be excluded from optimizeDeps
- `talkinghead` uses dynamic workers: MUST be excluded from optimizeDeps
- ONNX WASM files served by custom Vite plugin (`serveOnnxFiles()`)
- VAD init is lazy (first mic click) — getUserMedia blocks page load otherwise
- After changing optimizeDeps: delete `node_modules/.vite` cache

## Testing

```bash
# Check Ollama is loaded
curl http://localhost:11434/api/tags

# Check Orchestrator can reach Ollama
curl http://localhost:8082/v1/models

# Test TTS
curl -X POST http://localhost:8880/dev/captioned_speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"kokoro","input":"Hello","voice":"af_bella","response_format":"pcm","stream":false,"return_timestamps":true}'

# Test STT (with a WAV file)
curl -X POST http://localhost:8080/v1/audio/transcriptions \
  -F "file=@test.wav" -F "model=base.en"

# Test LLM via Orchestrator
curl -X POST http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Hi"}],"stream":false}'
```

## macOS (Apple Silicon) — Native Mode

macOS runs STT/TTS natively (no Docker) for Metal/MPS GPU acceleration. LLM is Ollama (also on host, managed separately).

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup-mac.sh` | Install Homebrew packages, install Ollama, clone Kokoro-FastAPI, download models |
| `scripts/start-mac.sh` | Launch STT + TTS + Vite dev server (Ollama runs as macOS app) |
| `scripts/stop-mac.sh` | Kill STT/TTS services |

### How It Works

- **LLM**: Ollama on macOS (installed via Homebrew) — Metal GPU auto-enabled; models pulled via `ollama pull`
- **TTS**: Kokoro-FastAPI cloned to `~/.nodeava/kokoro-fastapi/`, run via `uv` with `DEVICE_TYPE=mps` (PyTorch MPS)
- **STT**: `whisper-server` via Homebrew — Metal GPU auto-enabled
- **Frontend**: Vite dev server (no nginx) — same proxy config routes to native services
- **Same ports**: Orchestrator 8082, TTS 8880, STT 8080, Ollama 11434, Frontend 3000 — identical to Docker setup
- **PID files**: Written to `.pids/` for service process management
- **Logs**: Written to `logs/` (both dirs gitignored)

### Why Not Docker on Mac

Docker Desktop on macOS runs a Linux VM — no GPU passthrough to Metal/MPS. Docker services would run CPU-only, too slow for TTS inference.

## Known Constraints

- Default avatar (default-avatar.glb) is CC BY-NC-SA 4.0, licensed separately from project code (Apache-2.0).
- AMD TTS uses ROCm (first build ~20-30 min, ~22GB image)
- Windows + AMD GPU = not supported (Docker Desktop/WSL2 limitation)
- Minimum 8 GB VRAM recommended (~4.8 GB actual usage)
- macOS: requires Apple Silicon (M1+), 16 GB unified memory recommended

## Plan #5 — frontend tool toggles + state machine

- State machine in `frontend/src/app/state.js` now has 7 states: IDLE, LISTENING, TRANSCRIBING, THINKING, TOOL_CALLING, WIKI_QUERY, SPEAKING.
- `LLMClient.chatCompletion(messages, handlers, opts)` uses an object-bag handlers signature. Handlers: `onToken`, `onDone`, `onError`, `onToolCallStart`, `onToolCallEnd`, `onStageTiming`, `onThinkingToken`. Opts: `webSearch`, `wiki` (booleans → body fields).
- TTSManager has a `synthesizeFiller(text)` helper that prepends to the queue (used for "let me look that up..." when tool rounds run >800ms).
- ControlPanel exposes 2 tool toggles (web search, wiki). Persisted to localStorage keys `nodeava.toggle.web_search` and `nodeava.toggle.wiki`.
- Plan #8 will replace these toggles with a full command center.

## Plan #6 — preloaded wiki + ingest

- `wiki/` is pre-populated with 20 pages of NodeAva self-knowledge,
  compiled via `services/wiki-compiler/compile_wiki.py` using
  Anthropic Sonnet 4.6. The compiler reads `services/wiki-compiler/manifest.yml`
  (a list of topics → source files) and emits markdown into `wiki/concepts/`,
  `wiki/entities/`, `wiki/faqs/`.
- `POST /v1/ingest` accepts a multipart file upload, saves it to
  `/app/raw/uploads/`, invokes the compiler with `--ingest <path>`,
  returns the list of pages changed. Requires `ANTHROPIC_API_KEY` env var.
  Subprocess invocation uses `asyncio.create_subprocess_exec` (argv-style,
  no shell — user-supplied filenames cannot inject).
- The compiler is bundled into the orchestrator image (Dockerfile COPYs
  `wiki-compiler/`); docker-compose mounts `./wiki:/app/wiki:ro` and
  `./raw:/app/raw:rw`.
- The `wiki.list` tool now returns a useful index (10 concepts +
  5 entities + 5 FAQs); `wiki.search` finds matches across all pages;
  `wiki.open` retrieves any individual page. Workshop attendees with
  the 📚 Wiki toggle can ask "What is NodeAva?" and get a coherent
  answer from the agentic loop.

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

## Plan #11 — LM Studio backend (native API + dynamic discovery)

Full guide: **`docs/lmstudio-runbook.md`**. Selected by `LLM_BACKEND` env (`lmstudio` default | `ollama`).

- **New brain kind `lmstudio`** → `LMStudioProvider` (`providers/lmstudio.py`), a 3-line subclass of
  `OllamaProvider` that targets LM Studio's NATIVE endpoint `POST /api/v0/chat/completions`. The wire
  format is identical OpenAI-shaped SSE — streaming + `tool_calls` both verified — so the parser is reused.
  The native response also carries `stats`/`model_info`/`runtime` (TTFT, tok/s).
- **Discovery + residency** in `system/lmstudio.py` (`LMStudioBackend`): `GET /api/v0/models` →
  `list_models()` (filters to `llm`/`vlm`, flags `loaded` + `thinks`) and `query()` (residency snapshot in
  the same shape as `OllamaResidency`). Never raises.
- **Dynamic catalog**: `/v1/catalog` calls `Catalog.sync_dynamic_brains(...)` to merge every LM Studio model
  as an `lmstudio:<id>` brain (loaded-first). The dashboard Brain dropdown auto-lists the whole library.
- **`lmstudio-auto` brain** (`model: auto`) resolves at request time to the loaded model, else
  `LMSTUDIO_DEFAULT_MODEL`. `main.py` promotes it to the default brain when `LLM_BACKEND=lmstudio` and
  resets a stale non-LM-Studio active brain on boot.
- **Backend-aware routes**: `/v1/models`, `/v1/state`, `/v1/swap`, `/v1/catalog`, `/v1/chat/completions`
  all follow `llm_backend`. `nginx.conf` + `vite.config.js` add `/api/lmstudio/` (raw passthrough, Lab 1).
- **TTS unchanged**: LM Studio has no audio API (tested — see runbook §5). Kokoro remains the TTS engine.
- Tests: `tests/test_lmstudio.py` (config, provider, discovery/residency, dispatcher, dynamic merge, and
  route-level catalog + chat-auto). Whole suite: 171 passing.
