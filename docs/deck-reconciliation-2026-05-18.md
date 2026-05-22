# Deck Reconciliation — 2026-05-18

**Posture:** Built reality is the source of truth. The deck adapts.

**Deck file:** `/home/rob/Downloads/NodeAvaWorkshopDeck_v10_slide2_wording.html` (v10)
**Audit by:** Plan #10 deck-sync pass (executed today, post-overnight gallery work)

---

## Pattern 1 — Script naming drift across all "Demo" slides

The deck assumes a separate `nodeava-workshop/` repo with numbered scripts:
`00-preflight.sh`, `01-brain-local-llm.sh`, …, `10-full-digital-human.sh`.

The shipped reality is more **integrated** and uses different filenames:

| Deck script name | Shipped reality |
|---|---|
| `00-preflight.sh` | **`./install.sh`** — Plan #9 wizard. 9 idempotent steps including preflight, inventory, install, model pull, stack up, smoke verify. ~1s on re-runs. |
| `01-brain-local-llm.sh` | `scripts/demos/test-llm.sh` — verifies orchestrator + Ollama path |
| `02-voice-tts.sh` | `scripts/demos/test-tts.sh` |
| `03-ears-stt-file.sh` | `scripts/demos/test-stt.sh` (with WAV file arg) |
| `04-ears-stt-mic.sh` | **No CLI** — live mic happens in the browser. The "🎤 Mic" button in the page header (plus the new 900 ms VAD grace period). |
| `05-ears-to-brain.sh` | **No standalone CLI** — implicit when STT → Orchestrator inside the running browser |
| `06-brain-to-voice.sh` | **No standalone CLI** — implicit in the browser |
| `07-full-voice-loop.sh` | **Open the browser** at `http://localhost:3000` (or 3001 dev) |
| `08-latency-trace.sh` | **In-browser:** the FlowDiagram timing chips + EventLog populate per turn |
| `09-avatar-say.sh` | **No standalone CLI** — implicit in pipeline |
| `10-full-digital-human.sh` | `./install.sh` then open the browser |
| `11-wiki-knowledge.sh` | In-browser: enable the 📚 Wiki toggle and ask a NodeAva question |
| `12-drop-in-docs.sh` | `POST /v1/ingest` endpoint (orchestrator's wiki-compiler hook) |
| `14-swap-voice.sh` | Dashboard voice selector OR `POST /v1/swap` (see `scripts/demos/personality-set.sh` for pattern) |

**Two options to resolve:**

- **(A) Update deck** — change script names + recommend running things via `./install.sh` + the browser. Honest, fast (no new code).
- **(B) Add wrapper scripts** to match the deck's numbered names. Workshop "harness" feel, but it's duplicate code that runs the actual scripts.

**Recommendation: (A).** The shipped reality is *better* than the deck's plan (1 installer + 5 demo scripts + everything else in-browser is cleaner than 14 numbered scripts). Update the deck.

---

## Pattern 2 — Port mismatches

| Slide | Claim | Reality |
|---|---|---|
| 12 | Whisper on `http://localhost:8178` | Whisper is on **`localhost:8080`** |
| 12 | llama.cpp on `http://localhost:8080` | llama.cpp on **`localhost:8181`** (when opt-in; default is Ollama at host port 11434) |
| 23 | `http://localhost:3000/workshop` | Frontend is at `/` (no `/workshop` path); host port is `3000` (nginx) or `3001` (Vite dev) |

**Action:** edit the port-display blocks. The terminal mock-up on slide 12 needs the corrected port set.

---

## Pattern 3 — Backend defaults

| Slide | Claim | Reality |
|---|---|---|
| 13 | "Backend: llama.cpp" in terminal mock | Default is **Ollama (`host.docker.internal:11434`)**, per Plan #7. llama.cpp is the opt-in alternate the installer offers. |
| 17 | "Backend: llama.cpp / Qwen3-4B" | Same — Ollama is default; model is **`qwen3:4b-instruct`** (Plan #10 — non-thinking variant). |
| 28 | wiki structure: `index.md, architecture.md, install.md, ...` | Reality: `wiki/concepts/*.md`, `wiki/entities/*.md`, `wiki/faqs/*.md` — sub-organized, not flat. |

---

## List A — Built but not in deck (recommended additions)

For each: **shipped feature** → **proposed deck insertion**.

### 1. Installer wizard (Plan #9)
The first thing every attendee runs. 9 idempotent steps. Re-runs in ~1s.
**Insert:** new slide between current 11 ("Inspecting components") and 12 ("Preflight"), titled **"Demo 00 · `./install.sh`"**. Show the 9-step wizard banner output. Existing slide 12 (Preflight) becomes part of the wizard, not a separate script.

### 2. Walkthrough overlay (Plan #10)
First-page-load auto-tour: 7 spotlight steps walking through the avatar, mic, drawer, brain swap, tools, flow diagram, benchmark. Re-triggerable via the `?` button.
**Insert:** could be its own slide before Demo 10 (full digital human) OR a sidebar callout on slide 23. Screenshot: `01-walk-step1-meet-ava.png`.

### 3. FlowDiagram per-stage timing chips (Plan #10)
Per-lane duration chips (stt 0.3s · llm 1.2s · tts 0.4s · avatar 2.1s). Real-time per turn.
**Insert:** add to slide 19 (Latency trace) — the chips are the in-browser equivalent of `08-latency-trace.sh`. Screenshot: `04-flow-with-chips.png`. Slide 25 (Inspect running system) also benefits.

### 4. Benchmark widget (Plan #10)
"Benchmark this brain" button → runs 3 fixed prompts → comparison table with TTFT / tokens-sec / e2e / token count. Swap brains, click again, rows accumulate.
**Insert:** **replace slide 34** ("Benchmark the system") with a screenshot of the real comparison table. Screenshot: `05-benchmark-table.png`. Drop the 4-metric "what we benchmark" grid in favor of a real screenshot — the screenshot teaches the concept more directly.

### 5. Personality editor modal (Plan #10)
In-app textarea (full modal, 90vw × 80vh) for editing the system prompt at runtime. Saves as the "custom" personality, activates immediately. CLI parity: `scripts/demos/personality-set.sh <file.txt>`.
**Insert:** add to slide 33 ("Change voice, avatar, model, and personality") — the "Prompt → Behavior" card is the abstract version; this is the concrete demo. Screenshot: `06-personality-modal.png`.

### 6. 8-avatar gallery + post-RPM story
8 avatars (4 male + 4 female), all photoreal. RPM died Jan 2026; `readyplayerme/visage` is the new MIT-licensed source. Commercial-clean subset is rpm-male + rpm-female + mpfb.
**Insert:** add to slide 33 OR a new dedicated slide. The 4-male / 4-female balance + the licensing story is workshop-credible. Screenshot: `07-controls-with-8-avatars.png`.

### 7. Tool-call verbal fillers (Plan #10)
When a tool fires, the avatar says a phrase mapped to the tool family ("Let me look that up" for `wiki.*`, "Let me search the web for that" for `browser.*`). System layer fills the gap; the model is told NOT to narrate tool use.
**Insert:** add as a callout on slide 28 (tool call trace) OR slide 30 (Tools). Pedagogically rich — each phrase = one tool family.

### 8. The 7 prompt-engineering teachable moments
Live findings from testing Plan #8:
1. Multiple system prompts confuse the model
2. Word-level priming sensitivity ("can you search X" vs "search the web for X")
3. The "narration trap" (model says "I'll look that up" then stops without firing the tool)
4. The "I can't access real-time information" trap (RLHF disclaimer overriding tool access)
5. STT artifacts feed back ("NodeAva" → "Node Ava")
6. Tool-result snippet shape matters (thin snippets → no chain to wiki.open)
7. Thinking variants stall on cheap questions

**Insert:** **NEW SLIDE 32½** between slide 32 (Escalate to stronger model) and slide 33 (Change voice/avatar/model/personality). Title: **"The prompt is the program"**. Show 3-4 of the 7 findings as live-from-development screenshots / quote pairs. This is workshop gold — honest, technical, pedagogically dense.

### 9. Status-bar real probes (Plan #10)
The 4 indicators (Idle/STT/LLM/TTS) at top-left now run real 5-second polling probes against each service. The old code hardcoded "TTS=green" forever.
**Insert:** minor — could be a sidebar on slide 25 (Inspect running system) — example of "honest dots" vs "lying dots". Probably skip; it's plumbing.

### 10. Auto-fix script `tools/avatar-fix.sh`
Headless GLB rehab pipeline — Meshopt decompression, Armature wrapper injection, VRC viseme rename, Mixamo prefix strip. 2.8 seconds per file.
**Insert:** not workshop-relevant for attendees; skip from deck. Mention in repo docs only.

---

## List B — In deck but not built / overstated (decisions)

| Slide | Claim | Recommendation | Why |
|---|---|---|---|
| 11 | Numbered harness scripts `00-...10-` | **Reword** to reference shipped scripts (`./install.sh`, `scripts/demos/test-*.sh`, browser). | Don't fake a harness we don't have. |
| 12 | "Whisper on 8178" | **Edit** → 8080. | Wrong port. |
| 12 | "llama.cpp on 8080" | **Edit** → 8181 (when opt-in) or remove. | llama.cpp is opt-in alternate via installer Step 4. |
| 13 | Terminal: "Backend: llama.cpp" | **Edit** → "Backend: Ollama (default)" with qwen3:4b-instruct. | Default backend changed in Plan #7. |
| 14 | `--swap-voice calm` flag | **Cut** the flag example. | We don't have a CLI voice swap with `--swap-voice`. Voice swap is dashboard or `/v1/swap`. |
| 15 | `samples/what-is-nodeava.wav` | **Keep** but verify the sample exists in the repo. | Need to grep for it. |
| 16 | `--show-vad` flag | **Cut**. | Not a real flag. The VAD config is in `frontend/src/app/config.js`. |
| 17 | `--show-prompt` flag | **Cut**. | Not implemented. |
| 19 | `--cold` / `--compare streaming,no-stream` flags | **Cut or reword as concept-only.** | The browser shows live latency; toggle between thinking-model vs instruct-model brains for the comparison. |
| 21 | `--no-stream` flag | **Cut or reword.** | Streaming is the default; non-stream is a benchmark internal-only path. |
| 22 | `--voice calm` / `--avatar ava2.glb` flags on avatar-say | **Cut**. | Dashboard handles avatar/voice swap; no CLI flag. |
| 23 | `--show-events` / `--preset tutor` flags | **Reword** as "in-browser equivalents (EventLog + personality selector)". | These flags don't exist. |
| 27 | wiki flat file list (`index.md, architecture.md, ...`) | **Edit** to show `wiki/concepts/*.md`, `wiki/entities/*.md`, `wiki/faqs/*.md` (the actual Plan #6 structure). | Drift between described and actual layout. |

---

## Quick wins to add to the deck

1. **Installer-wizard slide** (post-overnight: `./install.sh` is the workshop kit's first-contact surface).
2. **Walkthrough overlay screenshot** on the full-digital-human slide (23).
3. **FlowDiagram chips screenshot** on the latency slide (19).
4. **Benchmark comparison-table screenshot** replacing the abstract metric grid on slide 34.
5. **Personality modal screenshot** on slide 33.
6. **"The prompt is the program" slide** as 32½.

## Summary counts

- **List A (built, not in deck):** 10 items — 6 high-priority for v11.
- **List B (in deck, drift):** 12 items — script names, ports, backend defaults, fake CLI flags.
- **Slides matching reality without changes:** 1-10 (concept), 24-26 (orchestrator concept), 31 (provider swap concept), 35-38 (production/close). About 20 of 38 slides are evergreen.

---

## Next: patches

The next pass applies the inline patches to produce v11. Structural changes (new slides) get flagged for your approval before insertion; content patches and screenshot inserts go in directly.
