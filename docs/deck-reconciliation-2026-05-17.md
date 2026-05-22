# Deck Reconciliation — 2026-05-17

**Posture:** Built reality is the source of truth. The deck adapts to what
shipped — either by adding new content, cutting unbuilt references, or
rewording overstated claims.

**Audit by:** Plan #10 Task 13
**Inventory source:** `git log`, `docs/superpowers/specs/`, `configs/catalog.yml`,
`services/orchestrator/orchestrator/routes/`, `scripts/demos/`,
`scripts/install/`, `frontend/src/dashboard/`, `frontend/public/avatars/`,
`wiki/`.

**Deck file:** [NOT FOUND IN REPO — please share location for List B audit]

---

## List A — Built (inventory for deck cross-check)

This list is what shipped. Compare against your deck slide-by-slide. For
anything in List A not mentioned in the deck, decide where to insert it.
For anything in your deck not in List A, add it to List B below.

---

### Block 1 — Install / Preflight

1. **Single-command installer entry point** (`scripts/install.sh`). Runs 9
   sequentially sourced wizard steps. The attendee types one command at the
   repo root; the wizard handles the rest. Landed: Plan #9, commit `19c6002`.

2. **Chatty teaching banner** (`scripts/install/01-welcome.sh`). Prints the
   full workshop agenda and explains what the wizard will build before
   touching anything. Color-coded (green OK / yellow warn / red fail via
   `_lib.sh`).

3. **5-check preflight** (`scripts/install/02-preflight.sh`). Checks: (a)
   platform (Linux / WSL2 / macOS), (b) GPU + VRAM (8 GB floor, warns at
   6–8 GB), (c) Docker + compose plugin, (d) free disk (20 GB minimum),
   (e) outbound network / captive-portal detection. Catches problems before
   they cause cascading failures.

4. **Inventory + idempotent reset** (`scripts/install/03-inventory.sh`).
   Detects what's already installed (Ollama, models, stack, catalog state)
   and offers Keep / Reset / Selective per component. This is also where
   `--full-reset` lives; no separate `reset.sh` needed.

5. **LLM branch** (`scripts/install/04-llm-choice.sh`). Attendees choose
   Ollama (default) or bring their own llama.cpp container (advanced). The
   wizard branches and registers a catalog entry accordingly.
   Files: `04-llm-choice.sh`, `05-install-ollama.sh`, `06-pull-models.sh`,
   `06-register-llamacpp.sh`.

6. **Model pull step** (`scripts/install/06-pull-models.sh`). Pulls
   `qwen3:4b-instruct` + `smollm2:360m` via Ollama. USB-stick fallback:
   models already in `~/.ollama/models` are detected by the inventory step
   and pull is skipped.

7. **Smoke verification step** (`scripts/install/09-smoke.sh`). Curls
   `/v1/catalog` and `/v1/state`; checks frontend is reachable on port 3000;
   confirms all services are green before declaring "you're ready." Detects
   port conflicts.

8. **macOS native path** (`scripts/setup-mac.sh`, `scripts/start-mac.sh`,
   `scripts/stop-mac.sh`). Runs STT + TTS natively (no Docker) using
   Metal/MPS. Same ports as Docker path. PID files in `.pids/`, logs in
   `logs/`.

9. **GPU detection script** (`scripts/detect-gpu.sh`). Standalone script
   that probes NVIDIA / AMD / Apple Silicon and emits the appropriate Docker
   compose flags. Used by the installer.

10. **Windows + AMD status**: explicitly unsupported (Docker Desktop /
    WSL2 limitation). Deck should state this clearly.

---

### Block 2 — Tier A tour (pipeline visualization)

11. **Dashboard drawer** (`frontend/src/dashboard/Dashboard.js`). Right-side
    panel over the existing avatar canvas. Floating toggle button (top-right)
    or `]` key. Remains closed by default; opens for teaching moments.
    Landed: Plan #8, commit `9521eed`.

12. **FlowDiagram — spatial pipeline lanes** (`frontend/src/dashboard/components/FlowDiagram.js`).
    Displays the pipeline as labeled swim-lanes: 🎤 → STT → LLM →
    [tool branch] → TTS → 🔊. Each lane lights up as it becomes active
    during a turn.

13. **FlowDiagram — per-stage timing chips** (same file). Small chips on
    each lane show the actual duration of that stage in milliseconds. The
    chip is blank until the stage fires, then shows e.g. `320ms`. Shows
    where time goes per turn at a glance. Landed: Plan #10, commit `fe14820`.

14. **Stage names wired to real events**: STT, first_token (TTFT), tts,
    avatar_speak — client-side timing events emitted by `Orchestrator.js`
    and consumed by the flow diagram. Corrected stage alignment landed
    `2616e6e`.

15. **EventLog component** (`frontend/src/dashboard/components/EventLog.js`).
    Scrolling log beneath the flow diagram; mirrors pipeline events with full
    timestamps and payload previews. Landed: Plan #8, commit `ef01478`.

16. **Thinking-model support end-to-end**: Qwen3 `<think>` blocks are
    streamed as separate `thinking_token` SSE events; the frontend strips
    them from the spoken text and subtitle, but they are visible in the event
    log. Gate: `brain.thinks: true` flag in `configs/catalog.yml`.
    Files: `LLMClient.js`, `Orchestrator.js`, `configs/catalog.yml`.

17. **Ollama residency chips** (`frontend/src/dashboard/components/ControlsPanel.js`).
    Live "gpu / split / cpu" badges beside the brain selector show which
    models Ollama has resident in VRAM. Source: `GET /v1/state →
    system.residency`.

18. **7-state state machine** (`frontend/src/app/state.js`). States: IDLE,
    LISTENING, TRANSCRIBING, THINKING, TOOL_CALLING, WIKI_QUERY, SPEAKING.
    StatusBar labels update on each transition.

19. **Tool-call verbal fillers** (`frontend/src/pipeline/Orchestrator.js`).
    When a tool round exceeds 800 ms, the avatar speaks a deterministic
    phrase: "Let me check the wiki." (wiki tools) or "Let me look that up."
    (browser tools). Audible pipeline-stage signaling — the attendee hears
    the tool fire even with eyes closed. Landed: Plan #10, commit `181b212`.

---

### Block 3 — Wiki RAG

20. **Preloaded self-knowledge wiki** (`wiki/`). 20 pages compiled by Sonnet
    4.6 from NodeAva's own source files and specs. Covers:
    - 10 concept pages: agentic-loop, avatar-rendering, language-model,
      nodeava-overview, pipeline-architecture, speech-to-text,
      text-to-speech, tool-registry, web-search, wiki-system.
    - 5 entity pages: kokoro-tts, qwen3-4b, searxng, talkinghead,
      whisper-base-en.
    - 5 FAQ pages: add-to-wiki, change-voice, enable-web-search, swap-model,
      system-requirements.
    Landed: Plan #6, commit `e89d746`.

21. **Wiki compiler** (`services/wiki-compiler/compile_wiki.py`). Driven by
    `services/wiki-compiler/manifest.yml`. Reads source files → Sonnet 4.6
    → markdown pages. Bundled into the orchestrator Docker image.

22. **Three wiki tools registered in the orchestrator agentic loop**:
    `wiki.list` (index of 10 concepts + 5 entities + 5 FAQs),
    `wiki.search` (lenient whitespace-flex + per-word matching across all
    pages), `wiki.open` (fetch any single page). Landed: Plan #4/5.

23. **Default personality primes wiki use**: system prompt includes a trigger
    map that fires `wiki.search` on any NodeAva-related question before
    answering from memory. Prevents hallucination about the project itself.
    File: `configs/catalog.yml` (default personality).

24. **POST /v1/ingest** (`services/orchestrator/orchestrator/routes/ingest.py`).
    Multipart file upload → saves to `/app/raw/uploads/` → invokes wiki
    compiler → returns list of changed pages. Requires `ANTHROPIC_API_KEY`.
    5 MB upload cap. argv-style subprocess (no shell injection). Attended:
    Plan #6, commit `7dd36a5`.

25. **Lenient wiki search** (`wiki/` via orchestrator). Whitespace-flexible
    + per-word matching + context windows. Fixed `601a133`.

---

### Block 4 — Swap brain / voice / avatar / personality

26. **`GET /v1/catalog`** (`routes/catalog.py`). Returns all brains, voices,
    avatars, and personalities with `available` flags. Brain availability is
    cross-checked against `GET /api/ps` on Ollama (live residency). Landed:
    Plan #7, commit `5e69c34`.

27. **`GET /v1/state`** (`routes/state.py`). Returns current active brain,
    voice, avatar, personality, tool toggles, and Ollama residency snapshot
    (gpu/split/cpu labels per loaded model).

28. **`POST /v1/swap`** (`routes/swap.py`). `{kind, id, value?}` flips any
    one valve atomically. Swap takes effect on the next turn. Returns new
    state. Kinds: `brain`, `voice`, `avatar`, `personality`, `tool`.

29. **State persisted across restarts** (`state/current.json`). Atomic R/W
    via `services/orchestrator/orchestrator/state.py`. Fixed `b8f51cb`.

30. **Brain catalog — 8 entries** (`configs/catalog.yml`): Qwen3 4B
    Instruct (default), SmolLM2 360M (tiny), Qwen3 4B Thinking (reasoning),
    DeepSeek-R1 8B (reasoning), Claude Sonnet 4.6 (cloud), GPT-4o (cloud),
    Groq Llama-3.3-70B (cloud). Local brains require Ollama; cloud brains
    require an env-var API key.

31. **Voice catalog — 5 entries**: Bella (warm, default), Nova (clear/neutral),
    Fenrir (deep/authoritative), Emma (warm UK female), George (warm UK male).
    All Kokoro-82M voices; hot-swap takes effect next sentence.

32. **Avatar gallery — 4 entries** (`frontend/public/avatars/`, `configs/catalog.yml`).
    Ava/default (photoreal, CC BY-NC 4.0), Aria/mpfb (MakeHuman, CC0),
    Yui/vroid (anime, VRoid Studio non-commercial), Maya/avaturn (photoreal,
    Avaturn non-commercial). Live swap via `AvatarManager.reload(url)` —
    no page reload needed. Landed: Plan #10, commit `4d5ba9e`.

33. **Avatar LICENSES.md** (`frontend/public/avatars/LICENSES.md`). Per-file
    license attribution table. Notes commercial-use caveat for non-CC0
    avatars. Landed: Plan #10, commit `22ce95a`.

34. **Personality catalog — 4 prebuilt personalities** (`configs/catalog.yml`):
    Helpful Assistant (NodeAva-aware, default), Dry Historian, Improv Comic,
    Patient Tutor. Each is a full system prompt (identity + output format +
    tool-use trigger map). Personality is injected at request time; no restart.

35. **ControlsPanel UI** (`frontend/src/dashboard/components/ControlsPanel.js`).
    Brain / voice / avatar / personality / tool selectors in the dashboard
    drawer. Each selector POSTs `/v1/swap` on change. Brain selector shows
    residency chips beside each option. Landed: Plan #8.

36. **Selector component** (`frontend/src/dashboard/components/Selector.js`).
    Reusable chip-slot selector; used by ControlsPanel for all four swap
    kinds.

37. **Personality editor UI** (`frontend/src/dashboard/components/PersonalityEditor.js`).
    Textarea pre-populated with the current personality's system prompt.
    "Save as My Personality" POSTs to `POST /v1/personality/custom` and
    switches the active personality live. Reset button restores the default.
    Landed: Plan #10, commit `2a875e7`.

38. **`POST /v1/personality/custom`** (`routes/personality.py`). Accepts a
    free-form system prompt string; writes `state/custom-personality.json`;
    injects it as the active personality for all subsequent requests.
    Returns the updated system state including `system.ollama`. Landed:
    Plan #10, commit `8bee529`.

39. **Emotion system** (`frontend/src/avatar/EmotionController.js`). LLM
    prefixes each response with a bracketed emotion tag `[happy]`, `[neutral]`,
    etc. EmotionController strips the tag and drives TalkingHead mood
    transitions. 8 emotions supported.

---

### Block 5 — Web search + provider swap + benchmark

40. **Agentic loop** (`services/orchestrator/orchestrator/agentic/`). Multi-
    round tool execution. The orchestrator calls the LLM, executes tool calls,
    feeds results back, and iterates until no more tool calls. Named SSE event
    types: `token`, `thinking_token`, `tool_call_start`, `tool_call_end`.
    Landed: Plan #4.

41. **Browser tools** (`browser.search` + `browser.open`). `browser.search`
    queries the bundled SearXNG meta-search engine and returns top-N results.
    `browser.open` fetches a URL, extracts readable text via trafilatura,
    caches in an in-process LRU. SSRF guard rejects private/loopback hosts.
    5 MB fetch cap.

42. **SearXNG service** (`docker-compose.yml`). Bundled as a Docker service
    at internal port 8080; not exposed to host. Workshop default secret key
    (rotate for non-localhost). DNS: `http://searxng:8080` from the
    orchestrator container.

43. **Cloud provider swap** (catalog `kind: cloud-litellm`). Brain swap to
    Claude Sonnet / GPT-4o / Groq Llama via LiteLLM. Requires setting the
    matching env var (`ANTHROPIC_API_KEY`, etc.) before starting the stack.
    No restart needed once the key is in env. Landed: Plan #7.

44. **Web search toggle + wiki toggle** (`POST /v1/swap` kind `tool`).
    Toggles live in server-side state (`state.tools.web_search`,
    `state.tools.wiki`). Frontend ControlsPanel POSTs to swap on change.
    Default: wiki on, web_search off.

45. **Benchmark panel** (`frontend/src/dashboard/components/BenchmarkPanel.js`).
    Runs 3 fixed prompts against the currently-active brain (a factual, a
    creative, and a current-events query). Captures TTFT, tokens/sec, and
    end-to-end latency per prompt. Results appended to a persistent comparison
    table (browser memory; cleared on reload). Landed: Plan #10, commit
    `cbc1460`.

46. **Benchmark API helper** (`frontend/src/api/benchmark.js`). Drives
    `/v1/chat/completions` with streaming; approximates token count via
    word-count. Exposes a progress callback for the UI. Landed: Plan #10,
    commit `d5e7130`.

47. **Interactive teaching demo scripts** (`scripts/demos/`). 8 scripts
    covering slides 13-24 of the deck:
    - `test-llm.sh` — direct Ollama chat
    - `test-tts.sh` — Kokoro TTS (audio output via speakers)
    - `test-stt.sh` — Whisper transcription (records from mic)
    - `test-pipeline.sh` — end-to-end mic → STT → Ollama → TTS → speakers
    - `test-orchestrator.sh` — interactive swap via `/v1/catalog` + `/v1/swap`
    - `list-models.sh` — `GET /api/ps` Ollama residency
    - `personality-set.sh` — set a custom personality from a file
    - `_audio.sh` — shared audio helpers (record, play)
    Landed: Plan #7 (most), Plan #10 (personality-set).

---

### Block 6 — Make it yours + Q&A

48. **Personality CLI parity** (`scripts/demos/personality-set.sh`). Takes
    a text file as argument; POSTs its contents to `/v1/personality/custom`
    and switches Ava live. Mirrors the dashboard Personality Editor exactly.
    Landed: Plan #10, commit `2a875e7`.

49. **4 prebuilt personality presets** (see item 34). Attendees can switch
    among them in the dashboard or via `curl /v1/swap`; or write their own
    in the editor. Workshop teachable moment: the system prompt is the
    program.

50. **Voice cloning docs** (`docs/cloning-a-voice.md`). Step-by-step guide:
    record a reference clip, run Kokoro's clone script, add the `.pt` tensor
    to the voices directory, register in catalog. GPU required for <1-hour
    turnaround. For attendees to take home after the workshop. Landed:
    Plan #10, commit `dd7399d`.

51. **7-step walkthrough overlay** (`frontend/src/dashboard/components/Walkthrough.js`).
    Spotlight tour of every demoable surface in order: Meet Ava → Talk or
    type → Open control drawer → Swap her brain → Give her tools → See the
    pipeline → Benchmark + make it yours. Spotlight renders a bounding-box
    cutout over the target element with a positioned tooltip. Landed:
    Plan #10, commit `cbc0699`.

52. **Walkthrough auto-start on first load** (`frontend/src/dashboard/components/WalkthroughTrigger.js`).
    Detects `localStorage.nodeava.walkthrough.done`; triggers the tour
    automatically on first visit. The `?` button re-triggers at any time.
    Landed: Plan #10, commit `b641295`.

53. **Post-RPM avatar context** (`frontend/public/avatars/README.md`).
    Rewritten to document the 2026 landscape honestly: Ready Player Me shut
    down Jan 2026; current supply of TalkingHead-compatible avatars (52
    ARKit + 15 Oculus visemes) is thin; curated gallery is the pragmatic
    choice; Microsoft Rocketbox is the planned commercial-clean path.
    Landed: Plan #10, commit `22ce95a`.

54. **`/health` endpoint** (`routes/health.py`). `GET /health` probes Ollama
    reachability and returns `{status, backend}`. Used by smoke test and
    future monitoring.

55. **State machine CLAUDE.md documentation** (`CLAUDE.md` Plan #5 section).
    Documents the 7-state machine, `LLMClient` handler/opts signature,
    `synthesizeFiller`, ControlPanel toggle persistence. Reference for deck
    speaker notes.

---

## List B — In deck but not built (FILL IN MANUALLY)

After reading List A and reviewing your slides, list any deck claim or
demo that doesn't have a shipped counterpart here. For each:

- **Slide ref:** e.g., "Block 3 / slide 14"
- **Claim:** quote what the slide says
- **Recommendation:** build / cut / reword
- **Rationale:** one line

| Slide ref | Claim | Recommendation | Rationale |
|-----------|-------|----------------|-----------|
| _(empty — fill from deck review)_ | | | |

**Suggested areas to check against the deck:**

- Any mention of "preset URL share" — not shipped. Personalities are local
  only (no export/import URL).
- Any mention of quantization slider / quantization explainer — explicitly
  a non-goal in the MVP spec.
- Any mention of side-by-side model comparison in the avatar canvas — not
  shipped. Benchmark panel compares sequentially, not side-by-side.
- Any mention of voice cloning UI — not shipped. Docs only (`docs/cloning-a-voice.md`).
- Any mention of drop-to-ingest UI — not shipped. Ingest is API-only
  (`POST /v1/ingest`); no drag-and-drop widget in the dashboard.
- Any mention of multi-language UI — not shipped.
- Any mention of Windows + AMD GPU — explicitly unsupported.
- Any mention of "USB-stick fallback" as an explicit UI feature — implicit
  only (inventory step detects pre-pulled models; no USB menu).

---

## Quick wins to add to the deck

The standout shipped-but-likely-undocumented items that the deck should
highlight if they are not already in it:

1. **Plan #9 installer wizard — 9 idempotent steps, teaching output at
   every step.** Most workshop decks gloss over install with "run this
   command." The NodeAva wizard is itself a teaching artifact: it explains
   WHY each step exists (preflight, GPU check, model pull, smoke verify) in
   plain language before executing it. An attendee who watches the wizard
   output has already had a 15-minute lecture on the system architecture.
   Insert: Block 1 / pre-demo. Show the terminal output — it's worth a slide.

2. **Plan #10 walkthrough overlay — 7-step guided tour, auto-starts on
   first load.** A cold-start attendee opens the browser and immediately sees
   a spotlight tour hitting every demoable surface in sequence. This is the
   missing "what do I touch first?" moment for block 2. Insert: Block 2 intro.
   Screenshot the walkthrough tooltip on the FlowDiagram step — it makes the
   "pipeline visible" claim concrete.

3. **Tool-call verbal fillers — audible pipeline-stage signaling.** When
   the avatar uses a browser or wiki tool, she says "Let me look that up." or
   "Let me check the wiki." before the answer arrives. The audience hears the
   tool fire without looking at the FlowDiagram. This is the most teachable
   moment in Block 3 and Block 5: the spoken filler is the LLM telling you
   it entered the tool branch. Pair with a slide that shows the 800 ms timer
   logic — it is a concrete example of prompt engineering (verbal filler) +
   system design (800 ms threshold) + UX (no dead silence during tool round).

4. **Plan #10 personality editor + CLI parity — the prompt is the program.**
   The personality editor exposes the raw system prompt in a textarea. An
   attendee can type "You are a pirate" and press Save — Ava immediately
   speaks like a pirate. Then `scripts/demos/personality-set.sh pirate.txt`
   does the same from the terminal. This is the cleanest live demo of the
   "prompt is the program" principle. Insert: Block 6 opener. It's a 90-
   second demo that earns the whole session's pedagogical payoff.

5. **Post-RPM avatar landscape context — workshop honesty.** The
   `frontend/public/avatars/README.md` rewrite documents that Ready Player
   Me shut down in January 2026. This is a real-world event attendees will
   ask about. A slide that acknowledges the thin supply of TalkingHead-
   compatible avatars, explains why the curated gallery is the pragmatic
   choice, and points to the Microsoft Rocketbox path for commercial use
   pre-empts the "why can't I just upload any avatar?" question. Insert:
   Block 6 / avatar section or as a "state of the ecosystem in 2026" aside.

---

## Summary

- **List A count:** 55 features inventoried across 6 blocks.
- **List B count:** _(filled by Lucasmind during deck review)_
- **Suggested areas to check in deck:** 8 items listed in List B header.
- **Quick wins:** 5 items — installer wizard teaching output, walkthrough
  overlay, verbal fillers, personality editor CLI parity, post-RPM avatar
  context.
