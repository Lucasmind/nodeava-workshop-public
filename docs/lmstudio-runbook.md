# LM Studio Backend — Runbook (Plan #11)

Switch NodeAva's brain from **Ollama** to **LM Studio**, with a live, auto-discovered
picker for *every* model in your LM Studio library. The avatar's LLM now runs through
LM Studio's **native** REST API (`/api/v0`); TTS (Kokoro) and STT (Whisper) are unchanged.

> **Verified end-to-end** against a live LM Studio (115-model library): backend switch,
> 112-model auto-discovery, residency, per-model swap, and streaming + non-streaming chat
> all working (`[happy] Welcome to NodeAva!` in ~155 ms on `qwen/qwen3-4b-2507`).

---

## 0. Prerequisites (one-time)

1. **LM Studio is running** with the local server started (Developer tab → **Start Server**,
   or `lms server start`). Default port **1234**.
2. **"Serve on Local Network" is ON** (Developer ▸ Server Settings). This binds the server to
   `0.0.0.0` so the orchestrator *container* can reach it via `host.docker.internal:1234`.
   Without it, LM Studio only listens on `127.0.0.1` and Docker can't see it.
3. At least one chat model downloaded (e.g. `qwen/qwen3-4b-2507` — small & fast, good default).
   Models JIT-load on first use; you don't need to pre-load.

Quick reachability check from the host:

```bash
curl http://localhost:1234/api/v0/models | head      # should list your models
```

---

## 1. Activate

LM Studio is the **default** backend now (`LLM_BACKEND=lmstudio` in `docker-compose.yml`).
Rebuild + restart so the new orchestrator code, env, and dashboard take effect:

```bash
docker compose up -d --build orchestrator frontend
# or rebuild the whole stack:  docker compose up -d --build
```

- **orchestrator** rebuild → new provider/discovery code + `LLM_BACKEND=lmstudio` env.
- **frontend** rebuild → dashboard brain-picker chips + the `/api/lmstudio/` nginx route.
- `configs/catalog.yml` is bind-mounted, so brain edits there only need a restart, not a rebuild.

---

## 2. Verify

```bash
# Active brain + LM Studio residency (which model is loaded right now)
curl -s http://localhost:8082/v1/state | python3 -m json.tool

# The full picker: your LM Studio library merged as lmstudio:<model> brains
curl -s http://localhost:8082/v1/catalog | python3 -c \
 "import sys,json;b=json.load(sys.stdin)['brains'];d=[x for x in b if x.get('dynamic')];\
print('dynamic LM Studio brains:',len(d));print('loaded first:',[x['id'] for x in d[:3]])"

# A real chat through LM Studio's native API
curl -s -X POST http://localhost:8082/v1/chat/completions -H 'Content-Type: application/json' \
 -d '{"messages":[{"role":"user","content":"Hi in five words"}],"stream":false}'
```

Then open the dashboard (**http://localhost:3000**, drawer ▸ Controls). The **Brain**
dropdown now lists every LM Studio model — loaded ones first, with a green **loaded** chip.

---

## 3. Using it

- **Pick any model live** from the Brain dropdown. Selecting one and chatting JIT-loads it in
  LM Studio. (Big 27B–35B models take a few seconds + VRAM to load the first time.)
- **`LM Studio (auto)`** brain = "use whatever I have loaded in LM Studio right now". It resolves
  at request time to your loaded model, else falls back to `LMSTUDIO_DEFAULT_MODEL`.
- **Thinking models** (names containing `thinking`/`reasoning`/`r1`/`magistral`/`qwq`) are auto-flagged
  `thinks: true` so the frontend buffers the `<think>` block instead of speaking it.
- **Native API bonus**: chat runs on `/api/v0/chat/completions`, which also returns
  `stats` (tokens/sec, TTFT), `model_info`, and `runtime` — available for a future telemetry hook.

### Raw model playground (Lab 1)
**Lab 1 ("The Brain")** now talks directly to LM Studio's native API: pick any model from
your library (loaded ones first) and measure raw TTFT / tokens-per-sec — it even logs LM
Studio's own *server-measured* stats. Powered by the `/api/lmstudio/` passthrough, available
in both Docker (nginx) and `npm run dev` (Vite proxy). Labs 4 & 6 already exercise LM Studio
via the orchestrator.

---

## 4. Switch back to Ollama

```bash
echo "LLM_BACKEND=ollama" >> .env      # (or edit .env)
docker compose up -d --build orchestrator frontend
```

Everything reverts to the host-Ollama path. Both backends coexist in the catalog; only the
*default* and the discovery source change.

Per-deploy overrides (in `.env`):

| Var | Default | Meaning |
|---|---|---|
| `LLM_BACKEND` | `lmstudio` | `lmstudio` or `ollama` |
| `LMSTUDIO_URL` | `http://host.docker.internal:1234` | LM Studio server as seen from the container |
| `LMSTUDIO_DEFAULT_MODEL` | `qwen/qwen3-4b-2507` | fallback for the `auto` brain |

---

## 5. TTS reality check ⚠️

**LM Studio cannot do text-to-speech — through any API.** This was tested, not assumed:

| Probe | Result |
|---|---|
| `POST /v1/audio/speech` (OpenAI-compat) | `{"error":"Unexpected endpoint or method"}` |
| `POST /v1/audio/transcriptions`, `/v1/audio/generations`, `/api/v0/audio/speech` | none exist |
| Official docs (`lmstudio.ai/docs/developer/rest`) | "no audio endpoints" |
| `voxtral-4b-tts-2603` prompted directly | `arch: llama`, `type: llm`; returned **empty** — it's a text model, not a vocoder |

The same is true of **Ollama** — both are *LLM inference engines* (text / embeddings / vision-input).
Text→speech is a different model class needing a dedicated server, which is why this kit uses
**Kokoro-FastAPI**. So TTS stays Kokoro:

- **Change voice** in the dashboard (Voice dropdown: Bella / Nova / Fenrir / Emma / George), or
- **Swap the TTS engine** entirely (Piper / XTTS / Orpheus) by replacing the `tts` service in
  `docker-compose.yml`. (A future *experimental* path: an Orpheus-style model that emits SNAC audio
  tokens via LM Studio chat + an external SNAC decoder — that's a separate service, not wired here.)

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| Brain dropdown shows no LM Studio models | LM Studio not reachable from the container. Confirm **Serve on Local Network** is ON and `curl http://localhost:1234/api/v0/models` works on the host. |
| `LM Studio unreachable` in `/v1/catalog` | Server stopped, or port ≠ 1234. Set `LMSTUDIO_URL` in `.env`. |
| Chat errors / long pause on first message | Model JIT-loading in LM Studio (esp. 27B+). Pick a smaller model or pre-load it in LM Studio. |
| Avatar speaks the `<think>` reasoning | You picked a thinking model not caught by the name heuristic. Use an `-instruct` model, or mark it `thinks: true`. |
| Want it to "just use whatever I loaded" | Select the **LM Studio (auto)** brain. |
