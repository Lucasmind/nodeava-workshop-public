# Plan #10 — Workshop Polish: Design

**Date:** 2026-05-17
**Status:** Approved for implementation
**Owner:** Lucasmind

## Context

Plan #10 is the closing layer of NodeAva's 3-day push to become a conference workshop kit. Plans #1-#9 built the substrate: orchestrator, agentic loop, frontend state machine, wiki RAG, command center backend, dashboard frontend, installer wizard. What remains is the polish that makes the workshop *workshop-able* — visible timings, A/B-able benchmarks, a guided first-run tour, customizable personality + avatar, and verbal cues so attendees can *hear* the pipeline working.

The forcing function is the workshop format from the original MVP spec — six 30-minute blocks: install → tour → wiki → swap → benchmark → make-it-yours. The substrate covers all six, but several blocks lack the artifact attendees should see/touch.

## Goals

- Make the pipeline measurable: attendees can benchmark Brain A vs Brain B and see the delta in a comparison table.
- Make the pipeline audible: when the avatar uses a tool, it says a phrase that maps cleanly to the tool fired.
- Make the pipeline tangible: per-stage timing chips on the existing FlowDiagram make round-trip costs visible per turn.
- Make the experience guided: a cold-start attendee gets a 7-step spotlight tour that lights up every demoable surface in order.
- Make it personal: attendees can edit the personality system prompt and see the new behavior live; they can swap among 4 prebuilt avatars; they get docs for cloning a Kokoro voice after the workshop.
- Make the deck honest: every demo in the slide deck reflects shipped reality at workshop start.

## Non-goals

- **Avatar drag-and-drop upload.** Research showed the post-RPM supply of TalkingHead-compatible avatars (52 ARKit + 15 Oculus visemes) is too thin for attendees to find their own in workshop time. Curated gallery sidesteps this.
- **Voice cloning UI.** Cloning a Kokoro voice requires audio capture + tensor manipulation outside what fits in Day 3. Ship docs only.
- **Multi-language UI.** Deferred.
- **Hot voice/avatar swap mid-utterance.** Swap takes effect on the next turn.
- **Persistent benchmark history across sessions.** Comparison table lives in browser memory; lost on reload. Acceptable for a workshop demo.

## Architecture overview

Plan #10 is mostly frontend work, with one new orchestrator endpoint and one TTS-event hook in the existing pipeline. No new services. No schema changes to the wire protocol.

### Components touched

```
frontend/src/
  pipeline/
    Orchestrator.js          ← add onToolCallStart → synthesizeFiller hook
  avatar/
    AvatarManager.js         ← add reload(url) for live GLB swap
  dashboard/
    Dashboard.js             ← mount BenchmarkPanel, PersonalityEditor
    components/
      FlowDiagram.js         ← add per-stage timing chips
      BenchmarkPanel.js      ← NEW
      PersonalityEditor.js   ← NEW
      Walkthrough.js         ← NEW (overlay + step list)
      WalkthroughTrigger.js  ← NEW (the "?" button)
  api/
    benchmark.js             ← NEW (runs 3 fixed prompts via existing /v1/chat/completions)
configs/
  catalog.yml                ← expand avatars: 1 → 4
services/orchestrator/app/
  api.py                     ← POST /v1/personality/custom
state/
  custom-personality.json    ← NEW runtime artifact
scripts/demos/
  personality-set.sh         ← NEW CLI parity script
docs/
  cloning-a-voice.md         ← NEW
frontend/public/avatars/
  README.md                  ← rewrite (correct VRoid+Avaturn claims)
  LICENSES.md                ← NEW per-avatar attribution
```

### Build order (lowest-risk first)

1. FlowDiagram timing chips — reuses existing `onStageTiming` events
2. Benchmark widget — builds on the same timing substrate
3. Avatar gallery — files already on disk; catalog + AvatarManager.reload
4. Personality editor — new endpoint + simple textarea + state file
5. Voice clone docs — pure markdown
6. Tool-call verbal fillers — small Orchestrator hook
7. Walkthrough overlay — built last so it can point at all the surfaces above
8. Deck reconciliation pass — two-direction audit; built reality is the source of truth

---

## Deliverable 1 — FlowDiagram timing chips

**What it is:** Per-stage duration chips overlaid on the existing FlowDiagram boxes. After each turn, each stage box displays its measured wall-time as a small chip: "STT 0.3s · LLM 1.2s · TTS 0.4s".

**Data source:** `Orchestrator.js` already emits `onStageTiming` events for each pipeline stage. `frontend/src/dashboard/state.js` already subscribes. Add `state.lastTurnTimings` keyed by stage name.

**UI:** FlowDiagram boxes currently show stage name + activity indicator. Add a small chip in the bottom-right of each box showing the most recent stage duration. Chip clears when a new turn starts; populates as each stage completes.

**Acceptance:** After speaking "what is the capital of France?", four chips appear in sequence (STT, LLM, TTS, AvatarSpeak) with reasonable durations. Speaking a second time replaces the chips. Chips are zero-effort to read at a glance during a live demo.

**Estimate:** 2 hr.

---

## Deliverable 2 — Benchmark widget

**What it is:** A "Benchmark this brain" button in the dashboard that runs 3 fixed prompts against the currently-active brain and records timings to a comparison table.

**Fixed prompts:**

1. **Short turn-around:** `Say hi in one sentence.` — measures cold-path baseline (TTFT, tokens/sec, e2e).
2. **Wiki-tool-using:** `What ports does NodeAva use?` — measures e2e including tool round-trip.
3. **Long-generation:** `Explain how the NodeAva pipeline works in detail.` — measures sustained tokens/sec.

**Metrics per row:**

| Brain | Prompt | TTFT (s) | Tokens/sec | E2E (s) | Notes |
|---|---|---|---|---|---|

Five columns; one row per prompt per benchmark run. Brain swaps append new rows. Rows persist in browser memory across swaps; clear button resets the table. No localStorage — table is session-scoped.

**Implementation:**

- New `frontend/src/api/benchmark.js` exports `runBenchmark(brainId, onProgress)` returning `{rows: BenchmarkRow[]}`.
- Calls `/v1/chat/completions` (non-streaming) for each prompt, captures token-count from response usage metadata, divides by elapsed wall-time.
- TTFT measured by separate streaming call: time from request-send to first `data: {...}` SSE event.
- `BenchmarkPanel.js` renders the button + table; progress shown as "Prompt 2 of 3..." while running.

**Acceptance:** Click "Benchmark this brain" with qwen3-4b-instruct active → table grows by 3 rows in ~30s. Swap to smollm2-360m, click again → 3 more rows, visibly faster TTFT. Visible delta between brains.

**Estimate:** 4 hr.

---

## Deliverable 3 — Avatar gallery

**What it is:** Expand the avatar selector from 1 option to 4. All 4 GLBs are already on disk in `frontend/public/avatars/` (downloaded 2026-05-17 from `met4citizen/TalkingHead`):

| ID | File | Style | Size |
|---|---|---|---|
| `default` | `default-avatar.glb` | RPM photoreal F | 4.6 MB |
| `mpfb` | `mpfb.glb` | MakeHuman, CC0 | 36 MB |
| `vroid` | `vroid.glb` | Anime | 2.3 MB |
| `avaturn` | `avaturn.glb` | Avaturn photoreal | 14 MB |

All 4 verified to contain the 52 ARKit blendshapes + 15 Oculus visemes (mpfb is missing the harmless `viseme_sil`).

**Implementation:**

- Update `configs/catalog.yml` — expand `avatars:` list from 1 entry to 4. Default stays at `default`.
- Add `AvatarManager.reload(url, body = 'F')` — re-loads the GLB in the existing TalkingHead instance. Avoid full re-init.
- Existing `Selector` component + `/v1/swap` flow already handle the kind=avatar case; no new dashboard wiring needed.
- Rewrite `frontend/public/avatars/README.md` to correct the standing VRoid claim (VRoid VRMs ship with 5 visemes, not 52 ARKit; the `vroid.glb` we ship has been HANA-Tool-processed by met4citizen).
- Add `frontend/public/avatars/LICENSES.md` documenting per-file attribution (CC0 for mpfb; non-commercial for the other three; workshop-distribution posture noted).

**Acceptance:** Open the drawer → Avatar section shows 4 chips. Click each → avatar reloads to that GLB without page refresh. Switching during a conversation is OK; next turn uses the new model.

**Estimate:** 2 hr.

---

## Deliverable 4 — Personality editor

**What it is:** A textarea in the dashboard with the active personality's `system_prompt` pre-filled. Attendee edits it, clicks "Save as My Personality" — saves to a `custom` personality slot and immediately becomes active.

**Implementation:**

- New endpoint `POST /v1/personality/custom` in `services/orchestrator/app/api.py` — accepts `{system_prompt: str}`, writes to `state/custom-personality.json`, updates `state.personality` to `custom`.
- On orchestrator startup, if `state/custom-personality.json` exists, register a synthetic `custom` personality entry with that prompt.
- Frontend: `PersonalityEditor.js` mounts under the existing personality selector. Shows the textarea + Save button + a Reset-to-original link. Saves trigger the POST, then refresh `/v1/state` so the selector shows `custom` as active.
- CLI parity: `scripts/demos/personality-set.sh path/to/prompt.txt` — curl POST with the file contents. Workshop CLI track can use this to set personalities from the shell.

**Acceptance:** Edit the prompt to something obvious ("You are a pirate"). Save. Ask the avatar a question. Response uses pirate persona. Click Reset → back to default personality. The CLI script does the same end-to-end.

**Estimate:** 3 hr.

---

## Deliverable 5 — Voice clone docs

**What it is:** A standalone markdown doc at `docs/cloning-a-voice.md` explaining how to clone a Kokoro voice + add it to NodeAva's catalog.

**Content:**

1. Kokoro voice-tensor format (`.pt` files, conditioning embeddings)
2. How to record a reference audio sample
3. The Kokoro voice-clone script (link to upstream; we don't host it)
4. Where to save the resulting `.pt` file
5. How to add a `voices:` entry to `configs/catalog.yml`
6. How to verify the new voice appears in `/v1/catalog`

**Acceptance:** A workshop attendee with no prior context follows the doc and ends up with a custom voice in their dropdown. Doc is honest about the 5-10 minute audio sample requirement and the GPU/CPU time cost.

**Estimate:** 1 hr.

---

## Deliverable 6 — Tool-call verbal fillers

**What it is:** When a tool fires mid-turn, the avatar speaks a phrase mapped to the tool family. Replaces the awkward 1-3 second silence during tool round-trips.

**Mapping:**

| Tool name pattern | Phrase pool (random pick) |
|---|---|
| `wiki.*` | "Let me look that up." / "One second, checking my notes." / "Pulling that up now." |
| `browser.*` | "Let me search the web for that." / "One sec, looking that up online." / "Checking the web." |

**Implementation:**

- In `Orchestrator.js`, hook `onToolCallStart(toolName)` to call `TTSManager.synthesizeFiller(pickPhrase(toolName))`.
- `pickPhrase` is a tiny utility — match prefix, pick random from pool.
- The personality system prompt already forbids the *model* from narrating tool use. This deliverable provides the verbal cue at the system layer instead — deterministically tied to the actual tool fired. Cleaner contract: model says nothing about tools, system says exactly the right thing exactly when the tool fires.

**Acceptance:** Ask "what ports does NodeAva use?" — avatar says "Let me look that up" before the wiki result comes back. Ask "what's recent in open-source LLMs?" with Web Search on — avatar says "Let me search the web for that". Each phrase picks randomly from its pool over repeated runs.

**Estimate:** 1 hr.

---

## Deliverable 7 — Walkthrough overlay

**What it is:** A 7-step spotlight tour that dims the page, highlights one UI element at a time, and shows a tooltip explaining what to try. Auto-triggered on first page load (localStorage flag `nodeava.walkthrough.completed`); re-triggerable from a "?" button in the top-right.

**Steps:**

1. **The avatar.** "This is Ava. She runs entirely on your machine — no cloud APIs."
2. **The mic / send box.** "Hold the mic to speak, or type and press send."
3. **The drawer toggle.** "Open the control drawer with this button (or press `]`)."
4. **The brain selector.** "Swap her brain mid-conversation. Try smollm2 for fast-but-dumb, qwen3 for smart."
5. **Web search + wiki toggles.** "Give her tools. With Web Search on, she can answer current-event questions."
6. **The flow diagram.** "Every turn shows you which stages ran and how long each took."
7. **Benchmark + 'make it yours'.** "Compare brains side-by-side here. Edit her personality below."

**Implementation:**

- `Walkthrough.js` — renders an overlay div with cutout-style spotlight + tooltip. Step config is a constant array `[{selector, title, body, position}]`.
- Spotlight implemented via SVG mask: full-page rect minus the target's bounding box. Tooltip positioned relative to the target.
- Auto-mount in `Dashboard.js`. On first load (no localStorage flag), trigger step 0. On click outside or Skip, set the flag.
- `WalkthroughTrigger.js` — small `?` button in the header. Clicking it clears the flag and re-runs the tour.

**Acceptance:** Fresh install + first page load → tour auto-starts on step 1. Click Next 6 times → tour ends. Refresh → no tour. Click the `?` → tour starts again.

**Estimate:** 5 hr.

---

## Deliverable 8 — Deck reconciliation pass

**What it is:** A two-direction audit of the workshop slide deck against shipped reality. **Built reality is the source of truth, not the deck.** The audit produces two lists; Lucasmind decides what to do with each.

**Process:**

1. Inventory what shipped (from `git log` + this spec + Plan #1-#9 specs).
2. Read every slide / demo / script in the deck.
3. Produce two lists:

   **A. Built but not in deck** — shipped features not mentioned in any slide. For each, propose where to insert in the deck (which block, before/after which existing slide). Default action: add to deck.

   **B. In deck but not built** — slides reference features that don't exist. For each, recommend: **(a) build it** — small enough to fit before workshop day, **(b) cut from deck** — feature isn't needed, or **(c) reword** — deck overstated something we can express more honestly.

4. Deliver as `docs/deck-reconciliation-2026-05-17.md` with the two lists clearly separated. Lucasmind triages list B and decides build / cut / reword per item.

**Acceptance:** Reconciliation doc exists with both lists. Each item in list A has a proposed deck-insertion location. Each item in list B has a recommendation (build/cut/reword) with a one-line rationale. Lucasmind can act on the doc without re-deriving what's where.

**Estimate:** 1 hr for the audit. Any actual build-it items from list B become follow-up tasks scoped against remaining time.

---

## Total estimate

19 hr dev + 1 hr deck reconciliation = **~20 hr**. Fits comfortably in the remaining 1.5 days (Day 2 afternoon + Day 3).

## Risks

- **Walkthrough overlay positioning.** Tooltip placement against arbitrary DOM elements can be fiddly when the drawer opens/closes mid-tour. Mitigation: steps 1-3 happen before the drawer opens; steps 4-7 happen with the drawer open and stay anchored to drawer-internal elements.
- **Benchmark variance.** Tokens/sec varies 5-15% turn-to-turn even on the same brain. Mitigation: prompts are fixed; users get a feel for the noise floor by clicking benchmark twice on the same brain. Workshop-honest "this is real-world variance, not a perfect lab measurement."
- **Personality reload edge case.** A custom personality saved while a request is in-flight could cause the request to mid-flight switch system prompts. Mitigation: orchestrator reads personality state at request start; switches take effect on the next request.

## Cuts if we run short

In priority order of what to cut first:

1. **Voice clone docs** — ship as post-workshop docs instead.
2. **Benchmark's 3rd prompt (long-generation)** — cut to 2 prompts.
3. **Walkthrough step 7 (benchmark + make-it-yours)** — cut to 6 steps, with a "More in the drawer →" hint.

## Open questions

None — all design choices locked in during brainstorming on 2026-05-17.
