# Plan #8 — Dashboard Frontend Design

**Status:** Draft (awaiting user review)
**Author:** Rob Lucas + Claude
**Date:** 2026-05-17
**Implements deck slides:** 24, 25, 31, 33 (the visual side that drives them)

## Why this exists

Plan #7 shipped a backend that lets attendees swap brains/voices/avatars/personalities/tools at runtime via three endpoints. Today no UI surfaces those endpoints — the swaps have to be done with `curl` or the demo scripts in `scripts/demos/`.

This plan ships the dashboard the workshop sells: a right-side drawer over the existing avatar page that lets attendees pick their brain, swap a voice, toggle tools, and — most importantly — **watch the pipeline route through the active components in real time**. The deck calls this Demo 12 ("See the brain work") and Demo 16 ("Change voice, avatar, model, and personality").

The avatar stays the primary UX. The drawer is opt-in — the floating button top-right opens it. Workshop instructor opens it during teaching moments; attendees can leave it closed when they're just chatting.

## Goals

1. A drawer over the existing avatar page that surfaces the Plan #7 swap controls (brain / voice / avatar / personality / tools).
2. A spatial **flow diagram** in the drawer that shows the pipeline as labeled lanes (🎤 → stt → llm → [tool branch] → tts → 🔊), with each lane lighting up as it becomes active during a turn.
3. A live **event log** that mirrors the flow diagram's state with full timestamps and payload previews.
4. Reactive **residency chips** beside the brain selector showing what Ollama has resident (gpu/split/cpu).
5. Implementation in **vanilla JS** matching the existing frontend pattern (no new framework).
6. Pipeline events sourced from the existing `Orchestrator.js` (no new SSE endpoint).

## Non-goals

- The wiki content browser (deferred — see memory note `project_wiki_human_side.md`).
- Editing personality system_prompt via the UI. Catalog edits remain a YAML file change for v1.
- Multi-tab state sync. Single user, single browser session.
- The benchmark panel and the walkthrough overlay — those are Plan #10.
- Authoring new avatars in the UI (attendees drop .glb files into `frontend/public/avatars/` and add a catalog entry).
- Mobile-first design. Workshop attendees use laptops. The drawer SHOULD render acceptably on a phone (responsive collapse to full-screen below 768px) but desktop is the design target.

## Architecture overview

```
┌─ Browser (localhost:5173 in dev, :3000 in prod) ────────────────────────┐
│                                                                         │
│  ┌─ Three.js canvas (existing) ────────────┐  ┌─ Drawer (new) ───────┐  │
│  │                                          │  │                      │  │
│  │       [3D avatar — full canvas]          │  │ Controls panel       │  │
│  │                                          │  │   • Brain ▾  ●gpu   │  │
│  │                                          │  │   • Voice ▾         │  │
│  │                                          │  │   • Avatar ▾        │  │
│  │                                          │  │   • Persona ▾       │  │
│  │                                          │  │   • Wiki ☐  Web ☐   │  │
│  │                                          │  ├──────────────────────┤  │
│  │                                          │  │ Flow + Events panel │  │
│  │                                          │  │   🎤 → stt → llm    │  │
│  │                                          │  │   →[wiki]→ tts → 🔊 │  │
│  │                                          │  │  ──────────────────  │  │
│  │                                          │  │   event log scroll   │  │
│  └──────────────────────────────────────────┘  └──────────────────────┘  │
│                                              ⏵ (floating toggle button) │
└─────────────────────────────────────────────────────────────────────────┘

Frontend modules:
  src/main.js (existing) — instantiates Avatar, Orchestrator, Dashboard
  src/dashboard/
    Dashboard.js       — top-level drawer container; toggles open/closed
    api.js             — fetch wrappers for /v1/catalog, /v1/state, /v1/swap
    state.js           — local mirror of server state + event emitter
    components/
      ControlsPanel.js   — 4 selectors + 2 toggles
      FlowDiagram.js     — spatial pipeline lanes
      EventLog.js        — scrolling text log
      Selector.js        — reusable dropdown with optional residency chip
  src/pipeline/Orchestrator.js (modified) — exposes pipeline events to subscribers
  src/ui/components/ControlPanel.js (modified) — tool toggles migrate to drawer
```

Data flow:

1. **Page load** — `Dashboard` constructor fetches `/v1/catalog` and `/v1/state`, populates selectors and chips. Drawer is hidden.
2. **Toggle button clicked** — drawer slides in with current state already populated.
3. **Selector changed** — POST `/v1/swap` with `{kind, id}`; response gives new state; dashboard updates from response. Avatar / TTSManager update via their existing state-load methods (already shipped in Plan #7 Task 9).
4. **Chat turn happens** — `Orchestrator.js` parses pipeline events from SSE and emits them to subscribers. `FlowDiagram` and `EventLog` (subscribers) update lane colors / append log entries.
5. **Tab close / page refresh** — server-side state in `state/current.json` persists; next load restores the same selections.

## Drawer behavior

- **Default state:** closed on first page load (avatar primary, clean first impression).
- **Trigger:** floating button fixed at top-right of the viewport. Icon = "panel" / "control" glyph. Same button closes (icon rotates 180°).
- **Keyboard shortcut:** `]` toggles. Documented in the drawer's title bar.
- **Width:** 380 px on desktop; full-screen below 768 px viewport.
- **Animation:** slide-in / out with 250 ms ease-out transition. Avatar canvas resizes to fill remaining viewport.
- **Persisted across reloads?** No — drawer state itself is ephemeral (the underlying *settings* persist via `state/current.json` server-side; only "is the drawer visible right now" is local UI state, defaulting to closed).

## Controls panel (top of drawer)

Five rows, each with a label and a selector / toggle:

| Row | Control | Source data | On change |
|-----|---------|-------------|-----------|
| Brain | Selector + residency chip | catalog.brains (filtered by `available: true`); state.brain | POST `/v1/swap` `{kind:"brain", id}` |
| Voice | Selector | catalog.voices; state.voice | POST `/v1/swap` `{kind:"voice", id}` |
| Avatar | Selector | catalog.avatars; state.avatar | POST `/v1/swap` `{kind:"avatar", id}`; then call `AvatarManager.loadAvatar()` to swap the .glb |
| Personality | Selector | catalog.personalities; state.personality | POST `/v1/swap` `{kind:"personality", id}` |
| Tools | Two checkboxes (Web search, Wiki) | state.tools.web_search, state.tools.wiki | POST `/v1/swap` `{kind:"tools", id:<name>, value:bool}` |

**Residency chip** rendering (next to brain selector):
- Pulls from `state.system.ollama.loaded`. If the active brain's model is in the loaded list, render a chip with `state.system.ollama.loaded[i].residency`:
  - `gpu` → green dot + "gpu"
  - `split` → yellow dot + "split"
  - `cpu` → red dot + "cpu"
- If the active brain is not currently loaded, render a gray "unloaded" chip (Ollama will load it on the next chat request).
- For cloud-litellm brains, render a "cloud" badge instead.
- For openai-compatible brains, render an "external" badge.

**Selector** rendering:
- Native `<select>` for simplicity (browser styling on dark background). Entries with `available: false` render as `disabled` with the reason in `title=` attribute (hover tooltip).
- The default catalog entry has `(default)` suffix in its label.

**Unavailable brain UX:** if attendee selects an unavailable brain (e.g., `claude-sonnet` without an API key), the POST `/v1/swap` returns 400 with the reason. Show the reason as a brief inline error message below the selector (red text, 5-second auto-fade). Brain stays at the previous selection.

## Flow + Events panel (bottom of drawer)

Two stacked sub-regions: **Flow** (top ~60% of the panel) and **Events** (bottom ~40%).

### Flow sub-region

The spatial pipeline. Each lane is a colored row with:
- A glyph (🎤 / icon / 🔊) or step number
- A label (`mic`, `stt · whisper`, `llm · qwen3:4b`, `tts · kokoro/bella`, `avatar speech`)
- An inline status string (latency, payload preview, or "idle")
- A left-edge color stripe indicating state

Lanes (top to bottom):
1. 🎤 **mic / vad** — gray when idle; blue with "listening..." during VAD-detected speech
2. **stt · whisper** — green when transcript arrives; shows "${duration_ms}ms"
3. **transcript** (italic sub-lane under stt) — the actual transcribed text
4. **llm · {active_brain}** — blue while thinking; status "round N/M · {tok/s} tok/s"
5. **tool branch** (indented under llm, appears only during tool rounds) — purple; shows `🔧 wiki.search "query" · {duration}ms ✓`
6. **tts · kokoro / {active_voice}** — green when first audio ready; shows "{first_audio_ms}ms"
7. 🔊 **avatar speech** — blue while speaking; gray when finished

Color states:
- **Gray** (`#475569`) = idle (no recent event for this lane)
- **Green** (`#10b981`) = completed this turn
- **Blue** (`#3b82f6`) = currently active
- **Purple** (`#c084fc`) = tool call branch
- **Red** (`#ef4444`) = error event for this lane (e.g., `tts.error`)

State transitions are driven by the event subscription (see "Event sourcing" below). When a new turn starts (`stt.started`), all lanes reset to gray except the active one.

### Events sub-region

A scrolling text log, newest at top, monospace font, dark background. Each line is one event:

```
22:14:04  tool_call_end  wiki.search · 263ms ✓ (matched 3 pages)
22:14:04  tool_call_start  wiki.search · args={"query":"ports"}
22:14:03  llm.first_token  312ms · round 1
22:14:03  stt.transcript  "what ports does NodeAva use?"
22:14:02  stt.started  480ms
```

Each event line is colored by its category:
- Green for stt.*
- Blue for llm.*
- Purple for tool_call_*
- Yellow for tts.*
- Red for any *.error event
- Gray for stage_timing

The log is capped at 100 visible lines; older entries scroll off. A "clear" button at the top of the Events region empties the log.

## Event sourcing

The frontend's existing `Orchestrator.js` already parses SSE events from `/api/llm/v1/chat/completions`:
- `event: stage_timing` → `onStageTiming` handler
- `event: tool_call_start` → `onToolCallStart` handler
- `event: tool_call_end` → `onToolCallEnd` handler
- `event: thinking_token` → `onThinkingToken` handler
- Default-stream chunks → `onToken` handler

This plan adds a small **event emitter** layer on top:

```javascript
// src/dashboard/state.js (new)
export class DashboardState extends EventTarget {
  emitPipelineEvent(type, payload) {
    this.dispatchEvent(new CustomEvent('pipeline', {detail: {type, payload}}));
  }
}
```

In `Orchestrator.js`, each existing handler ALSO calls `dashboardState.emitPipelineEvent(name, data)`. The `FlowDiagram` and `EventLog` components subscribe to the `pipeline` event in their constructors:

```javascript
dashboardState.addEventListener('pipeline', (e) => {
  this._handlePipelineEvent(e.detail.type, e.detail.payload);
});
```

Each subscriber updates its DOM imperatively from the event payload. Examples:
- `stt.started` → FlowDiagram sets mic lane to "blue · listening" and stt lane to "blue · transcribing"
- `tool_call_start` (name starts with "wiki.") → FlowDiagram inserts/updates the tool branch under llm
- `tool_call_end` → FlowDiagram updates the tool branch with duration + ✓

There are also non-Orchestrator events the dashboard cares about:
- **VAD events** from `STTManager.js` (speech detected, speech ended) → emit as `vad.started` / `vad.stopped`
- **TTS playback events** from `TTSManager.js` (first audio playing, all done) → emit as `tts.playing` / `tts.done`
- **Avatar speech events** from `AvatarManager.js` (lipsync started, finished) → emit as `avatar.speaking` / `avatar.idle`

All of these become events on the same `pipeline` event channel. Subscribers filter by `event.type`.

## State sync

State changes from the dashboard itself (selector → POST /v1/swap) are handled inline: the response contains the new state; the dashboard's local cache updates directly from the response.

State changes from elsewhere (CLI scripts, an instructor's other tab, an `ollama pull` finishing in the background) are not v1. The dashboard does not poll. Polish item: re-fetch `/v1/state` on `visibilitychange` when the tab regains focus.

The active **avatar** swap needs to trigger `AvatarManager.loadAvatar(newGlbPath)` to actually replace the 3D model in the canvas. Plan #7 Task 9 already added `AvatarManager._resolveAvatarUrl()` which fetches state on init; in this plan we add a post-swap callback so the dashboard can fire `AvatarManager.loadAvatar(catalog.avatars[newId].glb_path)` immediately.

Similarly the active **voice** swap updates `TTSManager._voice` on the next synthesis call (TTSManager reads voice from state on init via Plan #7 Task 9; we extend it with a `setVoice()` method already defined that the dashboard calls).

## File structure

### New files

| File | Purpose | Approx LoC |
|------|---------|-----------|
| `frontend/src/dashboard/Dashboard.js` | Top-level container; manages drawer open/close; instantiates child components | ~80 |
| `frontend/src/dashboard/api.js` | Fetch wrappers: `getCatalog()`, `getState()`, `swap(kind, id, value)` | ~40 |
| `frontend/src/dashboard/state.js` | `DashboardState` class — local mirror + EventTarget for pipeline events | ~60 |
| `frontend/src/dashboard/components/ControlsPanel.js` | Builds 5 selector rows + tool toggles | ~120 |
| `frontend/src/dashboard/components/FlowDiagram.js` | Renders the spatial pipeline lanes; updates from pipeline events | ~150 |
| `frontend/src/dashboard/components/EventLog.js` | Scrolling text log; appendable; cap at 100 | ~50 |
| `frontend/src/dashboard/components/Selector.js` | Reusable `<select>` with optional residency chip slot | ~60 |
| `frontend/src/dashboard/dashboard.css` | Drawer + panel styling | ~150 |

### Modified files

| File | Change |
|------|--------|
| `frontend/src/main.js` | Instantiate `Dashboard`; wire its event emitter to existing Orchestrator handlers |
| `frontend/src/pipeline/Orchestrator.js` | Each event handler also calls `dashboardState.emitPipelineEvent()` |
| `frontend/src/stt/STTManager.js` | Emit `vad.started` / `vad.stopped` |
| `frontend/src/tts/TTSManager.js` | Emit `tts.playing` / `tts.done` |
| `frontend/src/avatar/AvatarManager.js` | Emit `avatar.speaking` / `avatar.idle` from talkinghead state |
| `frontend/src/ui/components/ControlPanel.js` | Remove the wiki / web_search toggles (they live in the dashboard now). Mic + voice selector stay (for the non-dashboard view). |
| `frontend/index.html` | Add the floating toggle button + drawer container `<div>` |
| `frontend/src/style.css` | Import dashboard.css; add styles for the floating button |

## Cross-cutting

### Mobile / small viewport

Below 768 px viewport width, the drawer goes full-screen when open (no avatar visible while drawer is open). The toggle button stays fixed top-right. This is graceful degradation — workshop attendees use laptops, but the dashboard shouldn't be unusable on a phone.

### Accessibility

- Keyboard navigation: `]` toggles the drawer. Tab order within the drawer follows visual top-to-bottom.
- Aria-labels: drawer = `role="complementary"` with `aria-label="NodeAva controls"`. Toggle button = `aria-expanded`.
- Color is not the only signal: lane state has both color AND text status. Tool toggles show ✓/☐ glyph in addition to checkbox.
- Selectors are native `<select>` for screen-reader compatibility.

### Performance

- Event log capped at 100 visible lines; older lines removed from DOM (not just hidden). Prevents long sessions from bogging down.
- Flow diagram updates are direct DOM mutations (className + textContent changes) — no virtual DOM diff. Browser handles this in microseconds.
- Drawer animation uses CSS transform (compositor-only, not layout-thrashing).
- No polling. Subscriber pattern means CPU is idle when no events are firing.

### Tests

The frontend has no test framework today. This plan does NOT introduce one. Validation strategy:
1. Type checking: keep JSDoc annotations rigorous so an attendee's IDE catches errors.
2. Manual smoke test: documented checklist in the plan's E2E task — mirror the Plan #5/#6 test plan style.
3. Plan #10 polish will likely add Vitest + a small set of component tests covering the Dashboard's pure state-transition logic. Out of scope here.

## Out of scope (deferred)

- **Wiki content browser** — render compiled wiki pages as a fourth section of the drawer. See `project_wiki_human_side.md` memory.
- **Custom personality authoring** — text area for editing the system_prompt, saved as a new catalog entry.
- **Benchmark panel** — Plan #10 (the Demo 17 surface; needs the benchmark backend first).
- **Walkthrough overlay** — Plan #10. Shepherd-style guided tour of the workshop's slide path.
- **Cross-tab state sync** — visibilitychange re-fetch is polish, not v1.
- **Drawer position persistence** — remembering open/closed across reloads. Defaulting to closed is fine.
- **Settings export / import** — saving a "preset" (current full state) as a sharable JSON file.
- **Mobile-optimized flow diagram** — at very narrow widths the lanes could collapse into icons-only. Skip for v1.

## Risks & open questions

1. **Catalog vs state drift**: when the catalog is edited (e.g., a brain entry removed) while `state.json` references the removed id, the orchestrator's `state.py` already falls back to the catalog default. The dashboard should refetch /v1/state after a /v1/swap response (which already includes the corrected state) to surface the fallback. The fallback is invisible to the user — could be surprising. Mitigation: log it in the event log as `state.fallback`.

2. **Avatar swap mid-speech**: if an attendee swaps avatars while the current avatar is mid-utterance, `AvatarManager.loadAvatar(newPath)` needs to handle the in-progress audio. Two options: (a) interrupt current speech, swap immediately; (b) queue the swap until the current utterance finishes. Recommend (a) — instant feedback, matches the rest of the swap UX. Document in the plan.

3. **Brain swap mid-turn**: if an attendee swaps the brain while a chat round is in flight, the in-flight request continues with the old brain (the request was constructed before the swap). The next round uses the new brain. This is the expected behavior — `dispatch_for_brain` runs at request construction time per Plan #7 Task 7. The dashboard could surface this with a brief toast: "Active turn will finish on qwen3-4b. Next turn will use smollm2-360m." But likely overkill for v1.

4. **Tool branch visualization with multi-tool rounds**: an agentic round can fire multiple tools in sequence (wiki.list → wiki.open). The branch sub-lane needs to either show each tool sequentially (replace) or accumulate. Recommend "show the active/most-recent tool" — simpler, matches the visual rhythm of the live flow. The full sequence is preserved in the event log.

5. **CSS file conflicts**: the dashboard's drawer styles live in a separate `dashboard.css`. Existing `style.css` already has TalkingHead overrides. Keep the scopes separate by prefixing dashboard classes with `.nv-dash-`. Document the convention.

## Success criteria

Plan #8 is done when:

1. Opening `http://localhost:5173` shows the avatar full-screen with a small toggle button top-right and no other UI (drawer closed).
2. Clicking the toggle button slides in a drawer on the right showing Brain/Voice/Avatar/Personality/Tools controls populated from `/v1/catalog` and `/v1/state`. The current brain has the correct label and residency chip.
3. Selecting a different brain in the dropdown triggers `POST /v1/swap` (visible in Network tab), updates the chip/label, and the next chat turn uses the new brain (verified by the LLM lane in the flow diagram showing the new brain name).
4. Same swap pattern works for voice (next utterance uses the new voice), avatar (the .glb swaps in the canvas), personality (system_prompt prepended differs in the request body to ollama), tools (next turn does or doesn't call wiki/browser).
5. Speaking into the mic triggers the flow diagram lanes to light up in sequence: mic → stt → llm → tts → avatar. Tool rounds insert a purple tool branch under the LLM lane.
6. The event log shows each pipeline event with timestamp + payload preview.
7. Pressing `]` toggles the drawer.
8. The dashboard works on a 1280×800 laptop screen. Drawer overlaps the avatar canvas; canvas resizes when drawer opens.
9. No regressions in existing functionality (talking to the avatar still works with drawer closed; existing voice swap via the ControlPanel dropdown still works if it remains).
10. All Plan #7 tests still pass (146 currently).

## What comes next

Plan #9 will be the installer / preflight (`bash scripts/install.sh`) that brings up the whole workshop stack including pulling Ollama models from the catalog. Plan #10 adds the benchmark panel, walkthrough overlay, and any polish caught during workshop dry-runs.
