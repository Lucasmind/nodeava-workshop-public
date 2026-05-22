# Workshop Polish (Plan #10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the closing polish layer for NodeAva's workshop kit — visible per-stage timings, A/B-able benchmarks across brains, curated avatar gallery, in-app personality editor, voice-clone docs, deterministic tool-call verbal fillers, and a first-run spotlight walkthrough — so the pipeline becomes *measurable, audible, tangible, guided, and personal* in the workshop's six blocks.

**Architecture:** Frontend-heavy: one new endpoint (`/v1/personality/custom`) on the orchestrator; one new state file (`state/custom-personality.json`); 4 new frontend components in `frontend/src/dashboard/components/` (BenchmarkPanel, PersonalityEditor, Walkthrough, WalkthroughTrigger); 1 new helper module (`frontend/src/api/benchmark.js`); avatar gallery expansion via `configs/catalog.yml` + new `AvatarManager.reload()` method; small hook in `Orchestrator.js` for verbal fillers; markdown deliverables (`docs/cloning-a-voice.md`, `docs/deck-reconciliation-2026-05-17.md`). No new services, no wire-protocol changes.

**Tech Stack:** Vanilla JS ES modules + Vite + Three.js + TalkingHead (frontend); FastAPI + Python 3.12 + pytest (orchestrator); YAML for catalog; existing dashboard event bus (`DashboardState` extends EventTarget) for cross-component communication.

**Spec:** `docs/superpowers/specs/2026-05-17-workshop-polish-design.md`

**Testing posture:** The orchestrator has a pytest suite (`services/orchestrator/tests/`); backend tasks include pytest tests. The frontend has no test framework — frontend tasks use manual acceptance steps the implementer runs in a browser. Pure utility functions in frontend land (e.g., `pickPhrase`) get inline asserts in module-level `if (import.meta.env.DEV)` blocks where natural.

---

## File map

**Create:**
- `frontend/src/api/benchmark.js` — `runBenchmark(brainId, onProgress)` runs 3 fixed prompts via `/v1/chat/completions`, measures TTFT + tokens/sec + e2e
- `frontend/src/dashboard/components/BenchmarkPanel.js` — button + comparison table
- `frontend/src/dashboard/components/PersonalityEditor.js` — textarea + Save/Reset
- `frontend/src/dashboard/components/Walkthrough.js` — SVG-mask spotlight overlay + tooltip
- `frontend/src/dashboard/components/WalkthroughTrigger.js` — "?" button + localStorage flag
- `frontend/src/utils/pickPhrase.js` — pure prefix-match → random phrase utility
- `frontend/public/avatars/LICENSES.md` — per-avatar attribution
- `services/orchestrator/orchestrator/routes/personality.py` — POST `/v1/personality/custom`
- `services/orchestrator/tests/test_routes_personality.py` — pytest coverage
- `scripts/demos/personality-set.sh` — CLI parity script
- `docs/cloning-a-voice.md` — Kokoro voice cloning walkthrough
- `docs/deck-reconciliation-2026-05-17.md` — two-direction audit (created in Task 13)

**Modify:**
- `frontend/src/dashboard/components/FlowDiagram.js` — add per-lane duration chips
- `frontend/src/dashboard/Dashboard.js` — mount BenchmarkPanel, PersonalityEditor, Walkthrough, WalkthroughTrigger
- `frontend/src/avatar/AvatarManager.js` — add `reload(url, body)` method
- `frontend/src/pipeline/Orchestrator.js` — hook `onToolCallStart` → `TTSManager.synthesizeFiller(pickPhrase(name))`
- `configs/catalog.yml` — expand `avatars:` from 1 to 4 entries
- `frontend/public/avatars/README.md` — rewrite (correct VRoid/Avaturn claims)
- `services/orchestrator/orchestrator/main.py` — wire new personality router
- `services/orchestrator/orchestrator/catalog.py` — register `custom` personality at startup if `state/custom-personality.json` exists

---

## Task 1: FlowDiagram per-stage timing chips

Wires `stage_timing` pipeline events into the FlowDiagram so each lane shows its most-recent wall-time as a small inline chip. Resets chips at the start of each turn.

**Files:**
- Modify: `frontend/src/dashboard/components/FlowDiagram.js`
- Modify: `frontend/src/dashboard/dashboard.css` (add `.nv-dash-lane-chip` styles)

- [ ] **Step 1: Add `_chip` element to each lane in the existing `_build()` loop**

In `frontend/src/dashboard/components/FlowDiagram.js`, inside the `for (const def of LANE_DEFS)` loop, append one more child to each lane (after `status`):

```javascript
const chip = document.createElement('span');
chip.className = 'nv-dash-lane-chip';
chip.textContent = '';
lane.appendChild(chip);
this.lanes[def.id] = { lane, label, status, chip };
```

- [ ] **Step 2: Map pipeline stage names → lane ids**

Below `STATE_CLASSES` near the top of the file, add:

```javascript
// Pipeline stage_timing event names → FlowDiagram lane ids.
// Stages not listed (e.g. STT-internal substages) are ignored.
const STAGE_TO_LANE = {
  stt: 'stt',
  llm: 'llm',
  tool: 'tool',
  tts: 'tts',
  avatar_speak: 'avatar',
};
```

- [ ] **Step 3: Handle `stage_timing` events in `_handle()`**

Find the existing `_handle({type, payload})` method (it switches on `type`). Add a case (alphabetize among siblings):

```javascript
case 'stage_timing': {
  const laneId = STAGE_TO_LANE[payload.stage];
  if (!laneId) break;
  const lane = this.lanes[laneId];
  if (!lane) break;
  const seconds = (payload.duration_ms / 1000).toFixed(2);
  lane.chip.textContent = `${seconds}s`;
  break;
}
```

- [ ] **Step 4: Clear all chips on new turn (`vad.started`)**

Find the existing `vad.started` case (which already resets lanes to idle). Inside that case, after the existing reset loop, add:

```javascript
for (const id in this.lanes) {
  this.lanes[id].chip.textContent = '';
}
```

- [ ] **Step 5: Add chip styles in dashboard.css**

Append to `frontend/src/dashboard/dashboard.css`:

```css
.nv-dash-lane-chip {
  margin-left: 0.5em;
  padding: 0 0.4em;
  font-size: 0.78em;
  font-variant-numeric: tabular-nums;
  color: var(--nv-dash-muted, #888);
  background: var(--nv-dash-chip-bg, rgba(0,0,0,0.08));
  border-radius: 0.4em;
  min-width: 2.6em;
  text-align: center;
  display: inline-block;
}
.nv-dash-lane-chip:empty {
  display: none;
}
```

- [ ] **Step 6: Manual acceptance**

Run `cd frontend && npm run dev`. Open `http://localhost:5173`. Open the drawer (`]` key). Speak: "what is the capital of France?". Expected: chips appear sequentially on `stt`, `llm`, `tts`, `avatar` lanes with values like `0.34s`, `1.21s`, `0.41s`, `2.10s`. Speak a second prompt. Expected: chips clear at turn start, then re-populate with the new turn's values.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/dashboard/components/FlowDiagram.js frontend/src/dashboard/dashboard.css
git commit -m "feat(dashboard): per-stage timing chips on FlowDiagram"
```

---

## Task 2: Benchmark API helper

Pure-JS helper that runs 3 fixed prompts against the orchestrator's `/v1/chat/completions` endpoint and returns rows with TTFT, tokens/sec, and e2e timings. No UI in this task — that's Task 3.

**Files:**
- Create: `frontend/src/api/benchmark.js`

- [ ] **Step 1: Write the prompts + the BenchmarkRow shape**

Create `frontend/src/api/benchmark.js` with this header:

```javascript
/**
 * Benchmark runner — fires 3 fixed prompts against /v1/chat/completions
 * and returns rows for the dashboard's comparison table.
 *
 * Each prompt runs twice: once streaming (to measure TTFT) and once
 * non-streaming (to capture token usage cleanly). E2E is wall-clock for
 * the streaming run from request-send to last token.
 */

const BENCH_PROMPTS = [
  { id: 'short',     label: 'Short',     prompt: 'Say hi in one sentence.' },
  { id: 'wiki_tool', label: 'Wiki tool', prompt: 'What ports does NodeAva use?' },
  { id: 'long_gen',  label: 'Long gen',  prompt: 'Explain how the NodeAva pipeline works in detail.' },
];

/**
 * @typedef {Object} BenchmarkRow
 * @property {string} brainId
 * @property {string} brainLabel
 * @property {string} promptId
 * @property {string} promptLabel
 * @property {number} ttftMs       // time from request to first SSE chunk
 * @property {number} e2eMs        // wall-clock for the full streamed response
 * @property {number} outputTokens // from usage.completion_tokens (non-streaming run)
 * @property {number} tokensPerSec // outputTokens / (e2eMs/1000); 0 if e2eMs is 0
 * @property {string} timestamp    // ISO string of when this row was recorded
 */
```

- [ ] **Step 2: Implement the streaming TTFT measurement**

Append to `frontend/src/api/benchmark.js`:

```javascript
async function _measureTTFTAndE2E(prompt) {
  const t0 = performance.now();
  let ttftMs = 0;
  let e2eMs = 0;

  const res = await fetch('/api/orch/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: [{ role: 'user', content: prompt }],
      stream: true,
    }),
  });
  if (!res.ok) throw new Error(`bench stream: ${res.status} ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (ttftMs === 0) ttftMs = performance.now() - t0;
    decoder.decode(value, { stream: true });  // drain
  }
  e2eMs = performance.now() - t0;
  return { ttftMs, e2eMs };
}
```

- [ ] **Step 3: Implement the non-streaming token-count call**

Append to `frontend/src/api/benchmark.js`:

```javascript
async function _measureOutputTokens(prompt) {
  const res = await fetch('/api/orch/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: [{ role: 'user', content: prompt }],
      stream: false,
    }),
  });
  if (!res.ok) throw new Error(`bench nonstream: ${res.status} ${res.statusText}`);
  const data = await res.json();
  return data?.usage?.completion_tokens ?? 0;
}
```

- [ ] **Step 4: Export `runBenchmark`**

Append to `frontend/src/api/benchmark.js`:

```javascript
/**
 * Run all 3 fixed prompts against the currently-active brain and return
 * one BenchmarkRow per prompt.
 *
 * @param {object} brain                {id, label} of the currently-active brain
 * @param {(progress:{promptIdx:number, promptLabel:string, total:number}) => void} onProgress
 * @returns {Promise<BenchmarkRow[]>}
 */
export async function runBenchmark(brain, onProgress = () => {}) {
  const rows = [];
  for (let i = 0; i < BENCH_PROMPTS.length; i++) {
    const p = BENCH_PROMPTS[i];
    onProgress({ promptIdx: i + 1, promptLabel: p.label, total: BENCH_PROMPTS.length });

    const { ttftMs, e2eMs } = await _measureTTFTAndE2E(p.prompt);
    const outputTokens = await _measureOutputTokens(p.prompt);
    const tokensPerSec = e2eMs > 0 ? (outputTokens / (e2eMs / 1000)) : 0;

    rows.push({
      brainId: brain.id,
      brainLabel: brain.label,
      promptId: p.id,
      promptLabel: p.label,
      ttftMs: Math.round(ttftMs),
      e2eMs: Math.round(e2eMs),
      outputTokens,
      tokensPerSec: Math.round(tokensPerSec * 10) / 10,
      timestamp: new Date().toISOString(),
    });
  }
  return rows;
}

export { BENCH_PROMPTS };
```

- [ ] **Step 5: Smoke-test from the browser console**

Run `cd frontend && npm run dev` (if not running). Open `http://localhost:5173`. Open browser DevTools console:

```javascript
const { runBenchmark } = await import('/src/api/benchmark.js');
const rows = await runBenchmark(
  { id: 'qwen3-4b-instruct', label: 'Qwen3 4B Instruct' },
  (p) => console.log('progress', p)
);
console.table(rows);
```

Expected: 3 rows printed; TTFT in 100-400ms range; tokensPerSec in 10-50 range for `qwen3:4b-instruct`. No exceptions.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/benchmark.js
git commit -m "feat(dashboard): benchmark runner with TTFT + tokens/sec + e2e"
```

---

## Task 3: Benchmark Panel UI

Mounts a "Benchmark this brain" button + a persistent comparison table in the dashboard drawer.

**Files:**
- Create: `frontend/src/dashboard/components/BenchmarkPanel.js`
- Modify: `frontend/src/dashboard/Dashboard.js`
- Modify: `frontend/index.html` — add `<div id="nv-dash-bench"></div>` mount point inside the drawer
- Modify: `frontend/src/dashboard/dashboard.css` — table styles

- [ ] **Step 1: Add the mount point in index.html**

In `frontend/index.html`, inside the existing drawer container (search for `id="nv-dash-controls"`), add **after** the controls panel:

```html
<div id="nv-dash-bench"></div>
```

- [ ] **Step 2: Create the BenchmarkPanel skeleton**

Create `frontend/src/dashboard/components/BenchmarkPanel.js`:

```javascript
/**
 * Plan #10 — Benchmark widget.
 *
 * Renders a "Benchmark this brain" button + a comparison table. Each click
 * runs 3 fixed prompts against the currently-active brain (via api/benchmark.js)
 * and appends 3 rows to the table. Rows persist in memory until "Clear" is
 * clicked or the page reloads.
 */

import { runBenchmark } from '../../api/benchmark.js';
import { log } from '../../utils/logger.js';

export class BenchmarkPanel {
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this.rows = [];
    this.running = false;
    this._build();
    this.state.addEventListener('state', () => this._refreshButtonLabel());
  }
```

- [ ] **Step 3: Implement `_build()` — header, button, status line, table**

Append to `frontend/src/dashboard/components/BenchmarkPanel.js`:

```javascript
  _build() {
    this.mountEl.replaceChildren();

    const header = document.createElement('div');
    header.className = 'nv-dash-bench-header';
    header.textContent = 'BENCHMARK';
    this.mountEl.appendChild(header);

    this.btnEl = document.createElement('button');
    this.btnEl.className = 'nv-dash-bench-btn';
    this.btnEl.addEventListener('click', () => this._run());
    this.mountEl.appendChild(this.btnEl);

    this.statusEl = document.createElement('div');
    this.statusEl.className = 'nv-dash-bench-status';
    this.statusEl.textContent = '';
    this.mountEl.appendChild(this.statusEl);

    this.tableEl = document.createElement('table');
    this.tableEl.className = 'nv-dash-bench-table';
    this.mountEl.appendChild(this.tableEl);

    this.clearBtn = document.createElement('button');
    this.clearBtn.className = 'nv-dash-bench-clear';
    this.clearBtn.textContent = 'Clear table';
    this.clearBtn.addEventListener('click', () => {
      this.rows = [];
      this._renderTable();
    });
    this.mountEl.appendChild(this.clearBtn);

    this._refreshButtonLabel();
    this._renderTable();
  }

  _refreshButtonLabel() {
    const brain = this._activeBrain();
    if (!brain) {
      this.btnEl.textContent = 'Benchmark (loading brain…)';
      this.btnEl.disabled = true;
      return;
    }
    this.btnEl.textContent = this.running
      ? 'Running…'
      : `Benchmark ${brain.label}`;
    this.btnEl.disabled = this.running;
  }

  _activeBrain() {
    const id = this.state.serverState?.active?.brain;
    return id ? this.state.getBrain(id) : null;
  }
```

- [ ] **Step 4: Implement `_run()` and `_renderTable()`**

Append to `frontend/src/dashboard/components/BenchmarkPanel.js`:

```javascript
  async _run() {
    const brain = this._activeBrain();
    if (!brain || this.running) return;
    this.running = true;
    this._refreshButtonLabel();
    this.statusEl.textContent = 'Starting…';
    try {
      const rows = await runBenchmark(brain, ({ promptIdx, promptLabel, total }) => {
        this.statusEl.textContent = `Running ${promptIdx} of ${total}: ${promptLabel}`;
      });
      this.rows.push(...rows);
      this.statusEl.textContent = `Done (${rows.length} rows added).`;
      this._renderTable();
    } catch (err) {
      log('Benchmark failed', err);
      this.statusEl.textContent = `Failed: ${err.message}`;
    } finally {
      this.running = false;
      this._refreshButtonLabel();
    }
  }

  _renderTable() {
    this.tableEl.replaceChildren();
    if (this.rows.length === 0) {
      const empty = document.createElement('caption');
      empty.textContent = 'No runs yet. Click the button above to start.';
      this.tableEl.appendChild(empty);
      this.clearBtn.style.display = 'none';
      return;
    }
    this.clearBtn.style.display = '';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const h of ['Brain', 'Prompt', 'TTFT', 'Tok/s', 'E2E', 'Tokens']) {
      const th = document.createElement('th');
      th.textContent = h;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    this.tableEl.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const r of this.rows) {
      const tr = document.createElement('tr');
      const cells = [
        r.brainLabel,
        r.promptLabel,
        `${(r.ttftMs / 1000).toFixed(2)}s`,
        r.tokensPerSec.toFixed(1),
        `${(r.e2eMs / 1000).toFixed(2)}s`,
        String(r.outputTokens),
      ];
      for (const c of cells) {
        const td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    this.tableEl.appendChild(tbody);
  }
}
```

- [ ] **Step 5: Mount in Dashboard.js**

In `frontend/src/dashboard/Dashboard.js`, add the import near the others:

```javascript
import { BenchmarkPanel } from './components/BenchmarkPanel.js';
```

In the constructor, after the existing element lookups, add:

```javascript
this.benchEl = document.getElementById('nv-dash-bench');
if (!this.benchEl) throw new Error('Dashboard: bench mount missing');
```

Find the existing `_loadInitial()` (or wherever child components are constructed; in current code they're built in the constructor or `_loadInitial`). After the line that constructs `FlowDiagram`, add:

```javascript
this.benchPanel = new BenchmarkPanel(this.benchEl, this.state);
```

- [ ] **Step 6: Add table styles**

Append to `frontend/src/dashboard/dashboard.css`:

```css
.nv-dash-bench-header { font-weight: 600; margin: 1em 0 0.4em; font-size: 0.85em; opacity: 0.7; letter-spacing: 0.05em; }
.nv-dash-bench-btn { width: 100%; padding: 0.5em; margin-bottom: 0.5em; cursor: pointer; }
.nv-dash-bench-btn:disabled { cursor: wait; opacity: 0.6; }
.nv-dash-bench-status { font-size: 0.85em; opacity: 0.7; min-height: 1.2em; margin-bottom: 0.5em; }
.nv-dash-bench-table { width: 100%; border-collapse: collapse; font-size: 0.78em; font-variant-numeric: tabular-nums; }
.nv-dash-bench-table th, .nv-dash-bench-table td { padding: 0.2em 0.4em; border-bottom: 1px solid rgba(0,0,0,0.1); text-align: right; }
.nv-dash-bench-table th:first-child, .nv-dash-bench-table td:first-child,
.nv-dash-bench-table th:nth-child(2), .nv-dash-bench-table td:nth-child(2) { text-align: left; }
.nv-dash-bench-table caption { caption-side: top; text-align: left; font-size: 0.85em; opacity: 0.6; padding: 0.5em 0; }
.nv-dash-bench-clear { margin-top: 0.5em; padding: 0.3em 0.6em; font-size: 0.85em; cursor: pointer; }
```

- [ ] **Step 7: Manual acceptance**

Reload `http://localhost:5173`, open the drawer. Expected:
1. BENCHMARK section visible with "Benchmark Qwen3 4B Instruct" button + "No runs yet" caption.
2. Click the button → status changes to "Running 1 of 3: Short" → 3 rows appear after ~20s.
3. Open Controls → swap brain to "SmolLM2 360M" → click benchmark → 3 more rows appear with visibly different timings.
4. Click "Clear table" → all rows disappear, caption returns.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/dashboard/components/BenchmarkPanel.js frontend/src/dashboard/Dashboard.js frontend/index.html frontend/src/dashboard/dashboard.css
git commit -m "feat(dashboard): benchmark panel with persistent comparison table"
```

---

## Task 4: Avatar gallery — catalog expansion + live reload

Expands the avatar catalog from 1 to 4 entries (the GLBs already exist in `frontend/public/avatars/`) and adds `AvatarManager.reload(url, body)` so swap takes effect without page reload.

**Files:**
- Modify: `configs/catalog.yml`
- Modify: `frontend/src/avatar/AvatarManager.js`
- Modify: `frontend/src/dashboard/components/ControlsPanel.js` (verify avatar selector wires through `/v1/swap`; if it doesn't already trigger an avatar reload, add that hook)

- [ ] **Step 1: Expand `configs/catalog.yml` avatars section**

Find the existing `avatars:` block in `configs/catalog.yml`. Replace it with:

```yaml
avatars:
  - id: default
    label: "Ava (default, photoreal)"
    glb_path: /avatars/default-avatar.glb
    body: F
    default: true
  - id: mpfb
    label: "Aria (MakeHuman, CC0)"
    glb_path: /avatars/mpfb.glb
    body: F
  - id: vroid
    label: "Yui (anime, VRoid)"
    glb_path: /avatars/vroid.glb
    body: F
  - id: avaturn
    label: "Maya (photoreal, Avaturn)"
    glb_path: /avatars/avaturn.glb
    body: F
```

- [ ] **Step 2: Verify catalog parses + endpoint returns 4 avatars**

Restart the orchestrator: `docker restart nodeava-orch` (or `docker compose up -d orchestrator`). Then:

```bash
curl -s http://localhost:8082/v1/catalog | python3 -c "import json,sys; d=json.load(sys.stdin); print([a['id'] for a in d['avatars']])"
```

Expected: `['default', 'mpfb', 'vroid', 'avaturn']`.

- [ ] **Step 3: Add `AvatarManager.reload()`**

In `frontend/src/avatar/AvatarManager.js`, after the existing `loadAvatar()` method, add:

```javascript
  /**
   * Plan #10 — live avatar swap. Re-shows the avatar at a new URL using the
   * already-initialized TalkingHead instance. The previous body parameter
   * applies unless a new one is passed.
   *
   * @param {string} url  glb_path from the catalog entry (e.g. /avatars/vroid.glb)
   * @param {string} [body] 'F' or 'M' — defaults to the current body
   */
  async reload(url, body) {
    if (!this.head) throw new Error('AvatarManager not initialized');
    log(`Reloading avatar: ${url}`);
    await this.head.showAvatar({
      url,
      body: body || config.avatarBody,
      avatarMood: config.initialMood,
      lipsyncLang: 'en',
    });
    this.loaded = true;
    log('Avatar reloaded');
  }
```

- [ ] **Step 4: Wire avatar-swap → reload**

In `frontend/src/main.js` (or wherever `window.avatarManager` / `window.refresh*FromState` helpers are defined — search for the existing `refreshVoiceFromState` pattern), add a sibling helper:

```javascript
window.refreshAvatarFromState = async function (serverState, catalog) {
  const activeId = serverState?.active?.avatar;
  if (!activeId) return;
  const entry = catalog?.avatars?.find((a) => a.id === activeId);
  if (!entry) return;
  if (window.avatarManager && entry.glb_path) {
    try {
      await window.avatarManager.reload(entry.glb_path, entry.body);
    } catch (e) {
      console.warn('Avatar reload failed:', e);
    }
  }
};
```

Then in `frontend/src/dashboard/Dashboard.js`, in the existing swap-response handling (search for `swap` calls; usually the response calls `setServerState`), after `this.state.setServerState(...)`, add:

```javascript
if (window.refreshAvatarFromState) {
  await window.refreshAvatarFromState(this.state.serverState, this.state.catalog);
}
```

- [ ] **Step 5: Manual acceptance**

Reload `http://localhost:5173`. Open drawer → Controls → Avatar section. Expected:
1. 4 chips visible: `Ava (default, photoreal)`, `Aria (MakeHuman, CC0)`, `Yui (anime, VRoid)`, `Maya (photoreal, Avaturn)`.
2. Click `Yui (anime, VRoid)` → avatar in the canvas swaps to the anime model **without page refresh**. Wait 1-2s for the GLB to load.
3. Speak a sentence → lip sync works on the new model.
4. Swap back to `Ava (default)` → original avatar restored.

- [ ] **Step 6: Commit**

```bash
git add configs/catalog.yml frontend/src/avatar/AvatarManager.js frontend/src/main.js frontend/src/dashboard/Dashboard.js
git commit -m "feat(catalog): avatar gallery — 4 entries + live reload via AvatarManager.reload()"
```

---

## Task 5: Avatar gallery docs + LICENSES

Rewrites `frontend/public/avatars/README.md` to correct misleading VRoid/Avaturn claims, and adds a per-file `LICENSES.md`.

**Files:**
- Modify: `frontend/public/avatars/README.md` (full rewrite)
- Create: `frontend/public/avatars/LICENSES.md`

- [ ] **Step 1: Rewrite the README**

Replace the entire contents of `frontend/public/avatars/README.md` with:

```markdown
# Avatar Models

NodeAva ships with four pre-rigged avatars in `configs/catalog.yml`.
Workshop attendees swap among them from the dashboard's avatar selector.

| File | Style | Source | Notes |
|------|-------|--------|-------|
| `default-avatar.glb` | Photoreal F (Ready Player Me) | met4citizen/TalkingHead | 4.6 MB, ARKit + Oculus visemes |
| `mpfb.glb` | MakeHuman base | met4citizen/TalkingHead | 36 MB, CC0 (fully unrestricted) |
| `vroid.glb` | Anime F | met4citizen/TalkingHead | 2.3 MB, HANA-Tool-processed VRoid |
| `avaturn.glb` | Photoreal F (Avaturn) | met4citizen/TalkingHead | 14 MB, ARKit + Oculus visemes |

See `LICENSES.md` for per-file attribution.

## Adding your own avatar

TalkingHead requires GLB or VRM files with **all** of these blendshapes:

- **52 ARKit blendshapes** (facial expression — `jawOpen`, `mouthSmileLeft`, etc.)
- **15 Oculus visemes** (`viseme_aa`, `viseme_PP`, …)
- Standard humanoid skeleton

This combination is **rare** in the post-2026 avatar landscape:

- **Ready Player Me** was discontinued January 2026 (Netflix acquisition).
- **VRoid Studio** is free and easy to use but its exported VRMs ship with
  only 5 basic visemes — the 52 ARKit shapes require Unity + HANA Tool
  post-processing (multi-hour workflow).
- **Avaturn** (hub.avaturn.me) is the only viable web-based generator in 2026
  that produces both blendshape sets out of the box. Free Basic tier,
  requires signup. Pick the **T2 body type** when downloading.
- **Microsoft Rocketbox** (115 MIT-licensed avatars) can be converted via
  met4citizen's `blender/rename-rocketbox-shapekeys.py` plus a Mixamo
  auto-rigging pass — fully commercial-safe but ~30 min of Blender work per
  avatar.

## How NodeAva loads avatars

Place your `.glb` in this directory, then add an entry to `configs/catalog.yml`:

```yaml
avatars:
  - id: yourname
    label: "Your Display Name"
    glb_path: /avatars/your-file.glb
    body: F   # or M
```

Restart the orchestrator (`docker restart nodeava-orch`) — the new avatar
appears in the dashboard's avatar selector automatically.

## Verifying a GLB has the required shapes

Run from the repo root:

```bash
python3 - <<'PY'
import struct, json, sys
path = "frontend/public/avatars/your-file.glb"
with open(path, 'rb') as f:
    f.read(12)
    jl, _ = struct.unpack('<II', f.read(8))
    j = json.loads(f.read(jl).rstrip(b'\x00').rstrip())
names = set()
for m in j.get('meshes', []):
    for n in m.get('extras', {}).get('targetNames', []):
        names.add(n)
ARKIT = {'jawOpen','mouthSmileLeft','eyeBlinkLeft','browInnerUp','cheekPuff','noseSneerLeft','tongueOut'}
OCULUS = {'viseme_sil','viseme_PP','viseme_aa','viseme_O','viseme_U','viseme_I','viseme_E'}
print(f"total morphs: {len(names)}")
print(f"ARKit sample: {len(ARKIT & names)}/{len(ARKIT)}")
print(f"Oculus sample: {len(OCULUS & names)}/{len(OCULUS)}")
PY
```

All sample counts should be at maximum (7/7).
```

- [ ] **Step 2: Create LICENSES.md**

Create `frontend/public/avatars/LICENSES.md`:

```markdown
# Avatar License Attribution

All four bundled avatars are sourced from
[met4citizen/TalkingHead](https://github.com/met4citizen/TalkingHead/tree/main/avatars).
Per-file terms:

| File | License | Source / Attribution |
|------|---------|----------------------|
| `default-avatar.glb` | CC BY-NC 4.0 | Originally a [Ready Player Me](https://readyplayer.me) avatar (RPM discontinued Jan 2026). |
| `mpfb.glb` | **CC0** | Created with [MPFB2](https://static.makehumancommunity.org/mpfb.html) (MakeHuman Plugin For Blender). Public domain. |
| `vroid.glb` | VRoid Studio license, non-commercial | Created with [VRoid Studio](https://vroid.com/en/studio), HANA-Tool-processed for 52 ARKit blendshapes. |
| `avaturn.glb` | Avaturn non-commercial | Created with [Avaturn](https://hub.avaturn.me), free tier. |

**Workshop posture (2026-05-17):** The workshop kit is currently distributed
without charge. The non-commercial avatars are bundled under educational use.
If the kit moves to a paid distribution, the non-CC0 avatars must be replaced
with commercially-clean alternatives (the Microsoft Rocketbox library via
met4citizen's rename script is the planned path).
```

- [ ] **Step 3: Commit**

```bash
git add frontend/public/avatars/README.md frontend/public/avatars/LICENSES.md
git commit -m "docs(avatars): rewrite README + add per-file LICENSES.md"
```

---

## Task 6: Personality custom — backend endpoint

Adds `POST /v1/personality/custom` to the orchestrator, persists the custom prompt to `state/custom-personality.json`, and registers a synthetic `custom` personality entry at startup if the file exists.

**Files:**
- Create: `services/orchestrator/orchestrator/routes/personality.py`
- Create: `services/orchestrator/tests/test_routes_personality.py`
- Modify: `services/orchestrator/orchestrator/main.py` (mount router)
- Modify: `services/orchestrator/orchestrator/catalog.py` (load custom personality at init)

- [ ] **Step 1: Write the failing test**

Create `services/orchestrator/tests/test_routes_personality.py`:

```python
"""Tests for POST /v1/personality/custom."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrator.main import build_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NODEAVA_STATE_DIR", str(tmp_path))
    app = build_app()
    return TestClient(app)


def test_post_custom_persists_to_disk_and_activates(client: TestClient, tmp_path: Path):
    resp = client.post(
        "/v1/personality/custom",
        json={"system_prompt": "You are a pirate. Arr."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"]["personality"] == "custom"

    saved = json.loads((tmp_path / "custom-personality.json").read_text())
    assert saved["system_prompt"] == "You are a pirate. Arr."


def test_get_catalog_after_post_includes_custom_personality(client: TestClient):
    client.post(
        "/v1/personality/custom",
        json={"system_prompt": "You are a pirate. Arr."},
    )
    catalog = client.get("/v1/catalog").json()
    ids = [p["id"] for p in catalog["personalities"]]
    assert "custom" in ids


def test_post_rejects_empty_prompt(client: TestClient):
    resp = client.post("/v1/personality/custom", json={"system_prompt": "   "})
    assert resp.status_code == 422


def test_post_rejects_missing_field(client: TestClient):
    resp = client.post("/v1/personality/custom", json={})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd services/orchestrator
.venv/bin/pytest tests/test_routes_personality.py -v
```

Expected: 4 failures (the endpoint doesn't exist yet).

- [ ] **Step 3: Create the personality router**

Create `services/orchestrator/orchestrator/routes/personality.py`:

```python
"""POST /v1/personality/custom — set a custom personality system prompt."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("orchestrator.routes.personality")
router = APIRouter()


class CustomPersonalityIn(BaseModel):
    system_prompt: str = Field(..., min_length=1)

    @field_validator("system_prompt")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("system_prompt must not be blank")
        return v


def _state_dir() -> Path:
    return Path(os.environ.get("NODEAVA_STATE_DIR", "state"))


def _custom_path() -> Path:
    return _state_dir() / "custom-personality.json"


def write_custom_personality(prompt: str) -> None:
    """Persist the custom prompt atomically (tempfile + rename)."""
    target = _custom_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"system_prompt": prompt}
    with tempfile.NamedTemporaryFile(
        "w", dir=target.parent, delete=False, encoding="utf-8"
    ) as tf:
        json.dump(payload, tf)
        tmp_path = Path(tf.name)
    tmp_path.replace(target)
    log.info("custom personality written (%d chars)", len(prompt))


def read_custom_personality() -> str | None:
    """Return the saved custom prompt, or None if no file exists."""
    p = _custom_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("system_prompt")
    except (OSError, json.JSONDecodeError) as e:
        log.warning("custom-personality.json unreadable: %s", e)
        return None


@router.post("/v1/personality/custom")
async def post_custom(payload: CustomPersonalityIn, request: Request) -> dict:
    write_custom_personality(payload.system_prompt)

    catalog = request.app.state.catalog
    catalog.register_custom_personality(payload.system_prompt)

    store = request.app.state.state_store
    store.set_state("personality", "custom")
    return store.get_state()
```

- [ ] **Step 4: Add `Catalog.register_custom_personality`**

In `services/orchestrator/orchestrator/catalog.py`, find the `Catalog` dataclass (its fields include `personalities: list[PersonalityEntry]`). Add this method after the existing `default_personality` method:

```python
    def register_custom_personality(self, system_prompt: str) -> None:
        """Plan #10 — register or overwrite the 'custom' personality entry."""
        entry = PersonalityEntry(
            id="custom",
            label="My Personality (custom)",
            system_prompt=system_prompt,
            default=False,
        )
        for i, p in enumerate(self.personalities):
            if p.id == "custom":
                self.personalities[i] = entry
                return
        self.personalities.append(entry)
```

- [ ] **Step 5: Load custom personality at startup (inside `load_catalog`)**

In the same `catalog.py`, find the module-level `load_catalog(path)` function. Just before its `return cat` line — after the default-checks (`cat.default_brain()` etc.) — append:

```python
    # Plan #10 — restore custom personality from disk if present
    from orchestrator.routes.personality import read_custom_personality
    custom = read_custom_personality()
    if custom:
        cat.register_custom_personality(custom)
```

- [ ] **Step 6: Mount the router in main.py**

In `services/orchestrator/orchestrator/main.py`, find the existing `app.include_router(...)` calls. Add:

```python
from orchestrator.routes import personality as personality_routes
app.include_router(personality_routes.router)
```

- [ ] **Step 7: Expose `system_prompt` in `/v1/catalog`**

The frontend's Personality Editor (Task 7) needs to read the active personality's `system_prompt` to pre-fill its textarea. Extend the catalog response so the prompt is available client-side.

In `services/orchestrator/orchestrator/routes/catalog.py`, find the `personalities_out` list comprehension. Replace it with:

```python
    personalities_out = [
        {"id": p.id, "label": p.label, "system_prompt": p.system_prompt,
         "default": p.default, "available": True}
        for p in catalog.personalities
    ]
```

- [ ] **Step 8: Add a `system_prompt`-in-catalog assertion test**

Append to `services/orchestrator/tests/test_routes_personality.py` (the file you created in Step 1) — it reuses the same `client` fixture:

```python
def test_catalog_personalities_include_system_prompt(client: TestClient):
    """Plan #10 — system_prompt must be in /v1/catalog so the
    Personality Editor (Task 7) can pre-fill its textarea."""
    resp = client.get("/v1/catalog")
    assert resp.status_code == 200
    personalities = resp.json()["personalities"]
    assert personalities, "catalog has no personalities"
    for p in personalities:
        assert "system_prompt" in p, f"personality {p['id']} missing system_prompt"
        assert p["system_prompt"], f"personality {p['id']} has empty system_prompt"
```

- [ ] **Step 9: Run the tests — confirm pass**

```bash
cd services/orchestrator
.venv/bin/pytest tests/test_routes_personality.py -v
```

Expected: all 5 pass (4 personality tests + 1 system_prompt-in-catalog test).

- [ ] **Step 10: Run the full orchestrator test suite — confirm no regressions**

```bash
cd services/orchestrator
.venv/bin/pytest -q
```

Expected: all green.

- [ ] **Step 11: Manual smoke test via curl**

Rebuild + restart the orchestrator container:

```bash
docker compose up -d --build orchestrator
sleep 5
curl -s -X POST http://localhost:8082/v1/personality/custom \
  -H 'Content-Type: application/json' \
  -d '{"system_prompt":"You are a pirate. Arr."}' | python3 -m json.tool
```

Expected: response includes `"active": {"personality": "custom", ...}`.

```bash
curl -s http://localhost:8082/v1/catalog | python3 -c "import json,sys; d=json.load(sys.stdin); print([p['id'] for p in d['personalities']])"
```

Expected: list includes `'custom'`.

- [ ] **Step 12: Commit**

```bash
git add services/orchestrator/orchestrator/routes/personality.py services/orchestrator/orchestrator/catalog.py services/orchestrator/orchestrator/main.py services/orchestrator/orchestrator/routes/catalog.py services/orchestrator/tests/test_routes_personality.py
git commit -m "feat(orch): POST /v1/personality/custom + expose system_prompt in /v1/catalog"
```

---

## Task 7: Personality Editor UI

Adds a textarea + Save/Reset to the dashboard. Save POSTs to `/v1/personality/custom`; Reset POSTs `/v1/swap` to switch back to the previous personality.

**Files:**
- Create: `frontend/src/dashboard/components/PersonalityEditor.js`
- Modify: `frontend/src/dashboard/Dashboard.js`
- Modify: `frontend/index.html` (add `<div id="nv-dash-personality"></div>` mount point)
- Modify: `frontend/src/dashboard/api.js` (add `postCustomPersonality()`)
- Modify: `frontend/src/dashboard/dashboard.css`

- [ ] **Step 1: Add the API helper**

In `frontend/src/dashboard/api.js`, append:

```javascript
/**
 * Plan #10 — POST a custom personality prompt. Returns the new server state.
 */
export async function postCustomPersonality(systemPrompt) {
  const res = await fetch('/api/orch/v1/personality/custom', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ system_prompt: systemPrompt }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST /v1/personality/custom: ${res.status} ${text}`);
  }
  return res.json();
}
```

- [ ] **Step 2: Add the mount point**

In `frontend/index.html`, inside the drawer (after `<div id="nv-dash-bench"></div>`), add:

```html
<div id="nv-dash-personality"></div>
```

- [ ] **Step 3: Create PersonalityEditor.js**

Create `frontend/src/dashboard/components/PersonalityEditor.js`:

```javascript
/**
 * Plan #10 — Personality editor.
 *
 * Textarea pre-filled with the active personality's system_prompt.
 * "Save as My Personality" POSTs /v1/personality/custom and switches to it.
 * "Reset" swaps back to the default personality.
 */

import { postCustomPersonality, swap } from '../api.js';

export class PersonalityEditor {
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this._build();
    this.state.addEventListener('state', () => this._reseed());
  }

  _build() {
    this.mountEl.replaceChildren();

    const header = document.createElement('div');
    header.className = 'nv-dash-personality-header';
    header.textContent = 'PERSONALITY EDITOR';
    this.mountEl.appendChild(header);

    this.textareaEl = document.createElement('textarea');
    this.textareaEl.className = 'nv-dash-personality-textarea';
    this.textareaEl.rows = 8;
    this.textareaEl.placeholder = 'Write the system prompt that defines how Ava behaves…';
    this.mountEl.appendChild(this.textareaEl);

    const btnRow = document.createElement('div');
    btnRow.className = 'nv-dash-personality-btnrow';
    this.saveBtn = document.createElement('button');
    this.saveBtn.textContent = 'Save as My Personality';
    this.saveBtn.addEventListener('click', () => this._save());
    btnRow.appendChild(this.saveBtn);

    this.resetBtn = document.createElement('button');
    this.resetBtn.textContent = 'Reset';
    this.resetBtn.addEventListener('click', () => this._reset());
    btnRow.appendChild(this.resetBtn);
    this.mountEl.appendChild(btnRow);

    this.statusEl = document.createElement('div');
    this.statusEl.className = 'nv-dash-personality-status';
    this.mountEl.appendChild(this.statusEl);

    this._reseed();
  }

  _reseed() {
    const activeId = this.state.serverState?.active?.personality;
    const p = activeId ? this.state.getPersonality(activeId) : null;
    if (p?.system_prompt && !this._dirty) {
      this.textareaEl.value = p.system_prompt;
    }
  }

  async _save() {
    const prompt = this.textareaEl.value.trim();
    if (!prompt) {
      this.statusEl.textContent = 'Cannot save an empty prompt.';
      return;
    }
    this.saveBtn.disabled = true;
    this.statusEl.textContent = 'Saving…';
    try {
      const newState = await postCustomPersonality(prompt);
      this.state.setServerState(newState);
      this._dirty = false;
      this.statusEl.textContent = 'Saved. Next turn will use this personality.';
    } catch (err) {
      this.statusEl.textContent = `Failed: ${err.message}`;
    } finally {
      this.saveBtn.disabled = false;
    }
  }

  async _reset() {
    const defaultPersonality = (this.state.catalog?.personalities || []).find(
      (p) => p.id !== 'custom'
    );
    if (!defaultPersonality) return;
    try {
      const newState = await swap('personality', defaultPersonality.id);
      this.state.setServerState(newState);
      this._dirty = false;
      this.statusEl.textContent = `Reset to "${defaultPersonality.label}".`;
    } catch (err) {
      this.statusEl.textContent = `Reset failed: ${err.message}`;
    }
  }
}
```

- [ ] **Step 4: Mark textarea dirty on user input**

Inside `PersonalityEditor._build()`, after creating `this.textareaEl`, also wire:

```javascript
    this.textareaEl.addEventListener('input', () => {
      this._dirty = true;
    });
```

- [ ] **Step 5: Mount in Dashboard.js**

In `frontend/src/dashboard/Dashboard.js`, add the import:

```javascript
import { PersonalityEditor } from './components/PersonalityEditor.js';
```

In the constructor, add the element lookup:

```javascript
this.personalityEl = document.getElementById('nv-dash-personality');
if (!this.personalityEl) throw new Error('Dashboard: personality mount missing');
```

Construct alongside BenchmarkPanel:

```javascript
this.personalityEditor = new PersonalityEditor(this.personalityEl, this.state);
```

- [ ] **Step 6: Add styles**

Append to `frontend/src/dashboard/dashboard.css`:

```css
.nv-dash-personality-header { font-weight: 600; margin: 1em 0 0.4em; font-size: 0.85em; opacity: 0.7; letter-spacing: 0.05em; }
.nv-dash-personality-textarea { width: 100%; box-sizing: border-box; font: 0.85em/1.4 ui-monospace, "SF Mono", Menlo, monospace; padding: 0.5em; resize: vertical; }
.nv-dash-personality-btnrow { display: flex; gap: 0.4em; margin-top: 0.4em; }
.nv-dash-personality-btnrow button { flex: 1; padding: 0.4em; cursor: pointer; }
.nv-dash-personality-status { font-size: 0.85em; opacity: 0.7; min-height: 1.2em; margin-top: 0.4em; }
```

- [ ] **Step 7: Manual acceptance**

Reload the page. Open drawer → scroll to PERSONALITY EDITOR. Expected:
1. Textarea is pre-filled with the current personality's system_prompt.
2. Edit it to `You are a pirate. Always end sentences with 'Arr!' Begin with [happy].`
3. Click "Save as My Personality" → status: "Saved." Selector chip shows "My Personality (custom)" active.
4. Speak "Hello there" → response uses pirate persona, ends with "Arr!".
5. Click "Reset" → returns to default personality. Textarea re-seeds with the default prompt.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/dashboard/components/PersonalityEditor.js frontend/src/dashboard/Dashboard.js frontend/index.html frontend/src/dashboard/api.js frontend/src/dashboard/dashboard.css
git commit -m "feat(dashboard): personality editor — textarea + Save/Reset"
```

---

## Task 8: Personality CLI parity script

Shell script that POSTs a system prompt from a file to the orchestrator. Mirrors the dashboard editor for the workshop's CLI track.

**Files:**
- Create: `scripts/demos/personality-set.sh`

- [ ] **Step 1: Write the script**

Create `scripts/demos/personality-set.sh`:

```bash
#!/usr/bin/env bash
# Set a custom personality system prompt from a file.
# Usage: scripts/demos/personality-set.sh <prompt-file.txt>
#
# Mirrors what the dashboard's Personality Editor does — POSTs the file
# contents to /v1/personality/custom and switches NodeAva to use it.
set -euo pipefail

ORCH_URL="${NODEAVA_ORCH_URL:-http://localhost:8082}"

if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") <prompt-file.txt>" >&2
  exit 1
fi

PROMPT_FILE="$1"
if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "error: $PROMPT_FILE not found" >&2
  exit 1
fi

PROMPT=$(cat "$PROMPT_FILE")
if [[ -z "${PROMPT//[[:space:]]/}" ]]; then
  echo "error: $PROMPT_FILE is empty" >&2
  exit 1
fi

# Build the JSON body with a here-doc + python for safe escaping
JSON=$(python3 -c '
import json, sys
print(json.dumps({"system_prompt": sys.stdin.read()}))
' <<< "$PROMPT")

echo "POST $ORCH_URL/v1/personality/custom  ($(wc -c <<< "$PROMPT") chars)"
curl -fsS -X POST "$ORCH_URL/v1/personality/custom" \
  -H 'Content-Type: application/json' \
  -d "$JSON" | python3 -m json.tool
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/demos/personality-set.sh
```

- [ ] **Step 3: End-to-end test**

```bash
cat > /tmp/pirate-prompt.txt <<'EOF'
You are Ava with a pirate persona. End every sentence with "Arr!".
Begin every reply with the emotion tag [happy].
EOF
scripts/demos/personality-set.sh /tmp/pirate-prompt.txt
```

Expected: prints the new state JSON, with `"active": {..., "personality": "custom"}`. Reload the browser and speak — pirate persona is active.

- [ ] **Step 4: Commit**

```bash
git add scripts/demos/personality-set.sh
git commit -m "feat(scripts): CLI parity for personality editor"
```

---

## Task 9: Voice clone docs

Standalone markdown explaining how to clone a Kokoro voice + register it in NodeAva's catalog.

**Files:**
- Create: `docs/cloning-a-voice.md`

- [ ] **Step 1: Write the doc**

Create `docs/cloning-a-voice.md`:

```markdown
# Cloning a voice for NodeAva

NodeAva uses [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) for
text-to-speech. Voices are `.pt` tensor files (PyTorch state dicts holding
the conditioning embeddings the synthesizer uses to shape speech). Cloning a
voice means producing one of those tensors from a reference audio clip.

## What you need

- **A reference audio sample.** 5–10 seconds of clean, single-speaker speech.
  No music, no background noise, no clipping. WAV or FLAC, mono, 24 kHz.
- **A machine with a GPU.** Kokoro's voice-cloning script runs on CPU but
  takes 10–20× longer than a CUDA / Metal / ROCm GPU.
- **Disk space.** ~5 GB for the Kokoro base model + a few hundred KB per
  cloned voice.

## Step-by-step

### 1. Record a reference clip

Use Audacity or any recorder. Speak naturally for ~8 seconds. Avoid breaths
at the start and end. Save as `myvoice.wav` (mono, 24000 Hz, 16-bit PCM).

Quick check from a terminal:

```bash
ffprobe -hide_banner myvoice.wav 2>&1 | grep -E 'Duration|Stream'
```

You want something like `Duration: 00:00:08.50`, `Stream #0:0: Audio: pcm_s16le, 24000 Hz, mono`.

### 2. Run Kokoro's voice-clone script

The script lives in the upstream Kokoro repository (not bundled here).
Clone it once:

```bash
git clone https://github.com/hexgrad/kokoro.git ~/.nodeava/kokoro-tools
cd ~/.nodeava/kokoro-tools
pip install -r requirements.txt
```

Then clone:

```bash
python scripts/clone_voice.py \
  --input  /path/to/myvoice.wav \
  --output /path/to/myvoice.pt \
  --device cuda   # or mps for Apple Silicon, cpu as a last resort
```

This produces a `.pt` file (~200 KB).

### 3. Drop the voice into NodeAva's Kokoro container

NodeAva's Kokoro-FastAPI container mounts a voices directory. Find it:

```bash
docker inspect nodeava-tts | python3 -c "
import json, sys
m = json.load(sys.stdin)[0]['Mounts']
for x in m:
    if 'voices' in x.get('Destination', ''):
        print(x['Source'], '->', x['Destination'])
"
```

Copy your file to the source path:

```bash
cp myvoice.pt /path/from/inspect/myvoice.pt
docker restart nodeava-tts
```

### 4. Register the voice in NodeAva's catalog

Edit `configs/catalog.yml`. Add an entry under `voices:`:

```yaml
voices:
  # ...existing entries...
  - id: myvoice
    label: "My Cloned Voice"
    kokoro_voice: myvoice    # matches the filename without .pt
```

Restart the orchestrator so it re-reads the catalog:

```bash
docker restart nodeava-orch
```

### 5. Verify

```bash
curl -s http://localhost:8082/v1/catalog | python3 -c "
import json, sys
print([v['id'] for v in json.load(sys.stdin)['voices']])
"
```

You should see `myvoice` in the list. Open the dashboard, open the drawer,
and your voice appears in the Voice selector. Click it; the next thing Ava
says will use it.

## Troubleshooting

- **"Voice not found" from Kokoro.** The filename inside the container must
  match `kokoro_voice` exactly (no `.pt` suffix). The container path is
  typically `/app/voices/<name>.pt`.
- **Robotic / mechanical output.** Reference clip was too short, too noisy,
  or had multiple speakers. Re-record with a single clean sample.
- **Mouth doesn't match.** Word timestamps depend on the language model, not
  the voice; verify Kokoro's `language` is set correctly.

## A note on practicality for workshops

Cloning a voice is a 5-minute task once you've done it once. For a workshop
context, attendees usually find it more fun to **pick** a voice from the
preset gallery (Bella, Nova, Fenrir, Emma, George) than to fight a microphone
during a 3-hour session. Keep this doc as a take-home — try it the evening
after the workshop.
```

- [ ] **Step 2: Commit**

```bash
git add docs/cloning-a-voice.md
git commit -m "docs: cloning-a-voice walkthrough"
```

---

## Task 10: Tool-call verbal fillers

When a tool fires mid-turn, the avatar speaks a deterministic phrase mapped to the tool family. Replaces awkward silence; pedagogy-friendly because each phrase = one tool.

**Files:**
- Create: `frontend/src/utils/pickPhrase.js`
- Modify: `frontend/src/pipeline/Orchestrator.js`

- [ ] **Step 1: Create the pure utility**

Create `frontend/src/utils/pickPhrase.js`:

```javascript
/**
 * Plan #10 — pick a verbal-filler phrase keyed to a tool family.
 *
 * Pure function. Maps a tool name to a random phrase from its pool.
 * Returns null if no pool matches — caller skips the filler entirely.
 */

const POOLS = {
  'wiki': [
    'Let me look that up.',
    'One second, checking my notes.',
    'Pulling that up now.',
  ],
  'browser': [
    'Let me search the web for that.',
    'One sec, looking that up online.',
    'Checking the web.',
  ],
};

/**
 * @param {string} toolName e.g. "wiki.search", "browser.search", "wiki.open"
 * @param {() => number} [rand=Math.random] dependency-inject for tests
 * @returns {string|null}
 */
export function pickPhrase(toolName, rand = Math.random) {
  if (!toolName || typeof toolName !== 'string') return null;
  const family = toolName.split('.')[0];
  const pool = POOLS[family];
  if (!pool || pool.length === 0) return null;
  return pool[Math.floor(rand() * pool.length)];
}

// Inline self-test for the dev-build only.
if (import.meta?.env?.DEV) {
  console.assert(pickPhrase('wiki.search', () => 0) === 'Let me look that up.', 'pickPhrase wiki[0]');
  console.assert(pickPhrase('browser.search', () => 0.99) === 'Checking the web.', 'pickPhrase browser[last]');
  console.assert(pickPhrase('unknown.tool') === null, 'pickPhrase unknown family');
  console.assert(pickPhrase(null) === null, 'pickPhrase null toolName');
  console.assert(pickPhrase('wiki.open', () => 0.5) === 'One second, checking my notes.', 'pickPhrase wiki middle');
}
```

- [ ] **Step 2: Wire into Orchestrator.js**

In `frontend/src/pipeline/Orchestrator.js`, add the import near the others:

```javascript
import { pickPhrase } from '../utils/pickPhrase.js';
```

Find the existing `onToolCallStart` handler in the LLM-client handler bag (around line 221 in the current file). Inside that handler, **before** the existing `if (this.onToolCallStart) this.onToolCallStart(...)` line, add:

```javascript
            // Plan #10 — deterministic verbal filler tied to the tool family.
            // Replaces the timer-based "let me think" with a phrase that signals
            // *which* tool is firing. The model is forbidden (via personality
            // system prompt) from narrating tool use; this fills that gap.
            const phrase = pickPhrase(name);
            if (phrase && this.tts) {
              this.tts.synthesizeFiller(phrase);
            }
```

- [ ] **Step 3: Suppress the old timer-based filler when a phrase plays**

Still in the same `onToolCallStart` handler, the existing line `this._armFillerTimer();` arms the "let me think about that" timer. Wrap it so it only arms when no specific phrase fired:

Replace:

```javascript
            this._armFillerTimer();
```

with:

```javascript
            if (!phrase) {
              this._armFillerTimer();
            }
```

- [ ] **Step 4: Manual acceptance — wiki phrase**

Reload `http://localhost:5173`. Open drawer → enable "Wiki" toggle. Type or speak: `What ports does NodeAva use?`. Expected:
1. Within ~200ms of pressing send, you hear "Let me look that up." (or a sibling from the pool).
2. After ~1-2s the answer comes back referencing the ports.
3. FlowDiagram shows `tool` lane activating.

Run the same prompt 4-5 times. Expected: the phrase varies among the 3 wiki pool entries — not always the same one.

- [ ] **Step 5: Manual acceptance — browser phrase**

Open drawer → enable "Web search" toggle. Type: `What's recent in open-source LLMs?`. Expected:
1. Hear "Let me search the web for that." (or a sibling).
2. After 2-5s, response includes a recent fact about open-source LLMs.

- [ ] **Step 6: Manual acceptance — no narration from the model**

Inspect the LLM's text output (visible in the EventLog or the avatar's spoken response). Expected: no "I'll look that up" or "Let me search" coming from the *model*; only the system-injected filler is heard. The model jumps directly into tool_call without narration.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/utils/pickPhrase.js frontend/src/pipeline/Orchestrator.js
git commit -m "feat(pipeline): tool-call verbal fillers (wiki / browser)"
```

---

## Task 11: Walkthrough overlay component

The spotlight + step-bubble overlay. This task builds the component; Task 12 wires up the first-load trigger + the "?" button.

**Files:**
- Create: `frontend/src/dashboard/components/Walkthrough.js`
- Modify: `frontend/src/dashboard/dashboard.css`

- [ ] **Step 1: Write the step config + skeleton**

Create `frontend/src/dashboard/components/Walkthrough.js`:

```javascript
/**
 * Plan #10 — Spotlight walkthrough.
 *
 * Renders a full-page overlay with an SVG mask that cuts out the bounding
 * box of the current target element ("spotlight"), and positions a tooltip
 * adjacent to it. Steps advance via Next / Back / Skip buttons.
 *
 * Element selectors target dashboard surfaces. If a selector can't be
 * resolved, that step's spotlight falls back to a centered tooltip with no
 * cutout.
 */

const STEPS = [
  {
    target: '#nv-avatar-canvas',
    title: 'Meet Ava',
    body: 'This is Ava. She runs entirely on your machine — no cloud APIs. Speech-to-text, the language model, text-to-speech, and her face are all local.',
  },
  {
    target: '#nv-mic-btn, #nv-send-btn',
    title: 'Talk or type',
    body: 'Hold the microphone to speak, or type a message and press send. Either works.',
  },
  {
    target: '#nv-dash-toggle',
    title: 'Open the control drawer',
    body: 'Click this button (or press the "]" key) to open the dashboard. Everything you can swap or measure lives in there.',
    onAdvance: () => {
      // Open the drawer for the next steps
      document.getElementById('nv-dash-drawer')?.setAttribute('aria-hidden', 'false');
      document.getElementById('nv-dash-toggle')?.setAttribute('aria-expanded', 'true');
    },
  },
  {
    target: '#nv-dash-controls',
    title: 'Swap her brain',
    body: 'These chips let you swap her language model mid-conversation. Try the tiny SmolLM2 for fast-but-dumb, then Qwen3 4B for smart.',
  },
  {
    target: '#nv-dash-controls',
    title: 'Give her tools',
    body: 'Toggle Web Search to let her answer current-event questions. Toggle Wiki to let her look up project knowledge. The toggles change behavior on the next turn.',
  },
  {
    target: '#nv-dash-flow',
    title: 'See the pipeline',
    body: 'This flow diagram lights up as each stage runs. The small chips show stage durations — you can watch where time goes per turn.',
  },
  {
    target: '#nv-dash-bench, #nv-dash-personality',
    title: 'Benchmark + make it yours',
    body: 'Click Benchmark to compare brains side-by-side. Edit the personality below to change how Ava speaks. Have fun.',
  },
];

export class Walkthrough {
  constructor() {
    this.idx = 0;
    this.overlayEl = null;
    this.maskRectEl = null;
    this.tooltipEl = null;
    this._resizeListener = null;
  }

  start() {
    this.idx = 0;
    this._mount();
    this._render();
  }

  end() {
    this._unmount();
  }

  isActive() {
    return this.overlayEl !== null && this.overlayEl.isConnected;
  }
```

- [ ] **Step 2: Implement `_mount()` (overlay + SVG mask + tooltip)**

Append to `frontend/src/dashboard/components/Walkthrough.js`:

```javascript
  _mount() {
    if (this.overlayEl) return;

    this.overlayEl = document.createElement('div');
    this.overlayEl.className = 'nv-walk-overlay';
    this.overlayEl.setAttribute('role', 'dialog');
    this.overlayEl.setAttribute('aria-label', 'NodeAva walkthrough');

    // SVG mask: full-screen black rect minus a transparent hole over the target.
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.classList.add('nv-walk-svg');
    svg.setAttribute('xmlns', svgNS);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');

    const defs = document.createElementNS(svgNS, 'defs');
    const mask = document.createElementNS(svgNS, 'mask');
    mask.id = 'nv-walk-mask';
    const bg = document.createElementNS(svgNS, 'rect');
    bg.setAttribute('x', '0'); bg.setAttribute('y', '0');
    bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%');
    bg.setAttribute('fill', 'white');
    const hole = document.createElementNS(svgNS, 'rect');
    hole.setAttribute('fill', 'black');
    hole.setAttribute('rx', '6'); hole.setAttribute('ry', '6');
    mask.appendChild(bg);
    mask.appendChild(hole);
    defs.appendChild(mask);
    svg.appendChild(defs);

    const dim = document.createElementNS(svgNS, 'rect');
    dim.setAttribute('x', '0'); dim.setAttribute('y', '0');
    dim.setAttribute('width', '100%'); dim.setAttribute('height', '100%');
    dim.setAttribute('fill', 'rgba(0,0,0,0.55)');
    dim.setAttribute('mask', 'url(#nv-walk-mask)');
    svg.appendChild(dim);

    this.maskRectEl = hole;
    this.overlayEl.appendChild(svg);

    // Tooltip
    this.tooltipEl = document.createElement('div');
    this.tooltipEl.className = 'nv-walk-tooltip';
    this.overlayEl.appendChild(this.tooltipEl);

    document.body.appendChild(this.overlayEl);

    this._resizeListener = () => this._render();
    window.addEventListener('resize', this._resizeListener);
  }

  _unmount() {
    if (this._resizeListener) {
      window.removeEventListener('resize', this._resizeListener);
      this._resizeListener = null;
    }
    if (this.overlayEl) {
      this.overlayEl.remove();
      this.overlayEl = null;
      this.maskRectEl = null;
      this.tooltipEl = null;
    }
  }
```

- [ ] **Step 3: Implement `_render()` (positioning + tooltip content + buttons)**

Append to `frontend/src/dashboard/components/Walkthrough.js`:

```javascript
  _render() {
    const step = STEPS[this.idx];
    if (!step) {
      this.end();
      return;
    }

    // Resolve target (first match across the selector list)
    let targetEl = null;
    for (const sel of step.target.split(/\s*,\s*/)) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) {  // visible
        targetEl = el;
        break;
      }
    }

    if (targetEl) {
      const r = targetEl.getBoundingClientRect();
      const pad = 8;
      this.maskRectEl.setAttribute('x', String(Math.max(0, r.left - pad)));
      this.maskRectEl.setAttribute('y', String(Math.max(0, r.top - pad)));
      this.maskRectEl.setAttribute('width', String(r.width + pad * 2));
      this.maskRectEl.setAttribute('height', String(r.height + pad * 2));
      this._positionTooltip(r);
    } else {
      // Fallback: center the tooltip, no cutout
      this.maskRectEl.setAttribute('width', '0');
      this.maskRectEl.setAttribute('height', '0');
      this.tooltipEl.style.left = '50%';
      this.tooltipEl.style.top = '50%';
      this.tooltipEl.style.transform = 'translate(-50%, -50%)';
    }

    // Tooltip content
    this.tooltipEl.replaceChildren();
    const title = document.createElement('div');
    title.className = 'nv-walk-tooltip-title';
    title.textContent = step.title;
    const body = document.createElement('div');
    body.className = 'nv-walk-tooltip-body';
    body.textContent = step.body;
    const counter = document.createElement('div');
    counter.className = 'nv-walk-tooltip-counter';
    counter.textContent = `Step ${this.idx + 1} of ${STEPS.length}`;
    const btns = document.createElement('div');
    btns.className = 'nv-walk-tooltip-btns';

    const skip = document.createElement('button');
    skip.textContent = 'Skip';
    skip.className = 'nv-walk-btn-skip';
    skip.addEventListener('click', () => this.end());
    const back = document.createElement('button');
    back.textContent = 'Back';
    back.disabled = this.idx === 0;
    back.addEventListener('click', () => { this.idx--; this._render(); });
    const next = document.createElement('button');
    next.textContent = this.idx === STEPS.length - 1 ? 'Done' : 'Next';
    next.addEventListener('click', () => {
      if (step.onAdvance) step.onAdvance();
      this.idx++;
      if (this.idx >= STEPS.length) this.end();
      else this._render();
    });

    btns.appendChild(skip);
    btns.appendChild(back);
    btns.appendChild(next);

    this.tooltipEl.appendChild(counter);
    this.tooltipEl.appendChild(title);
    this.tooltipEl.appendChild(body);
    this.tooltipEl.appendChild(btns);
  }

  _positionTooltip(targetRect) {
    // Prefer below if there's room; otherwise above; otherwise centered.
    const t = this.tooltipEl;
    t.style.transform = '';
    const margin = 14;
    const tw = 320;  // matches CSS max-width
    const th = 180;  // rough estimate; CSS bounds it tightly
    let top = targetRect.bottom + margin;
    if (top + th > window.innerHeight - margin) {
      top = targetRect.top - th - margin;
    }
    if (top < margin) top = margin;
    let left = targetRect.left + (targetRect.width - tw) / 2;
    left = Math.max(margin, Math.min(window.innerWidth - tw - margin, left));
    t.style.left = `${left}px`;
    t.style.top = `${top}px`;
  }
}
```

- [ ] **Step 4: Add styles**

Append to `frontend/src/dashboard/dashboard.css`:

```css
.nv-walk-overlay {
  position: fixed; inset: 0; z-index: 9999;
  pointer-events: auto;
}
.nv-walk-svg {
  position: absolute; inset: 0;
  pointer-events: none;
}
.nv-walk-tooltip {
  position: fixed;
  max-width: 320px;
  background: white; color: #222;
  padding: 1em 1.2em;
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.25);
  font: 0.95em/1.4 -apple-system, system-ui, "Segoe UI", sans-serif;
}
@media (prefers-color-scheme: dark) {
  .nv-walk-tooltip { background: #2a2a2a; color: #eee; }
}
.nv-walk-tooltip-counter { font-size: 0.8em; opacity: 0.6; margin-bottom: 0.3em; }
.nv-walk-tooltip-title { font-weight: 600; font-size: 1.05em; margin-bottom: 0.4em; }
.nv-walk-tooltip-body { margin-bottom: 0.8em; }
.nv-walk-tooltip-btns { display: flex; gap: 0.4em; }
.nv-walk-tooltip-btns button { flex: 1; padding: 0.4em; cursor: pointer; }
.nv-walk-btn-skip { opacity: 0.6; }
```

- [ ] **Step 5: Smoke test from the console**

Run `cd frontend && npm run dev`. Open `http://localhost:5173`. In the browser console:

```javascript
const { Walkthrough } = await import('/src/dashboard/components/Walkthrough.js');
window.__walk = new Walkthrough();
window.__walk.start();
```

Expected: page dims, spotlight appears around the avatar canvas, tooltip says "Meet Ava". Clicking Next advances through 7 steps; the drawer opens between steps 3 and 4. Clicking Done or Skip closes the overlay.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/dashboard/components/Walkthrough.js frontend/src/dashboard/dashboard.css
git commit -m "feat(dashboard): walkthrough overlay component (spotlight + step bubbles)"
```

---

## Task 12: Walkthrough trigger + first-load persistence

Auto-triggers the walkthrough on first page load (localStorage flag), and adds a `?` button that re-runs it on demand.

**Files:**
- Create: `frontend/src/dashboard/components/WalkthroughTrigger.js`
- Modify: `frontend/src/dashboard/Dashboard.js`
- Modify: `frontend/index.html` (add `<button id="nv-walk-trigger">?</button>` near the drawer toggle)
- Modify: `frontend/src/dashboard/dashboard.css`

- [ ] **Step 1: Add the trigger button to the HTML**

In `frontend/index.html`, find the existing `<button id="nv-dash-toggle">…</button>` (the drawer toggle). Insert immediately before it:

```html
<button id="nv-walk-trigger" type="button" aria-label="Start walkthrough" title="Walkthrough">?</button>
```

- [ ] **Step 2: Create WalkthroughTrigger.js**

Create `frontend/src/dashboard/components/WalkthroughTrigger.js`:

```javascript
/**
 * Plan #10 — Walkthrough trigger + first-load persistence.
 *
 * On page load: if localStorage flag `nodeava.walkthrough.completed` is
 * unset, auto-start the walkthrough after a short delay (lets the dashboard
 * finish its initial fetch).
 *
 * Clicking the "?" button always re-starts the walkthrough.
 */

import { Walkthrough } from './Walkthrough.js';

const LS_KEY = 'nodeava.walkthrough.completed';

export class WalkthroughTrigger {
  constructor(btnEl) {
    if (!btnEl) throw new Error('WalkthroughTrigger: button element required');
    this.btnEl = btnEl;
    this.walk = new Walkthrough();
    this.btnEl.addEventListener('click', () => this._startManual());
  }

  /**
   * Called once at app init. Triggers the auto-tour on first run.
   */
  initAutoStart() {
    if (localStorage.getItem(LS_KEY)) return;
    // Wait a beat for the dashboard to fetch state + render selectors.
    setTimeout(() => {
      if (!this.walk.isActive()) {
        this._startAuto();
      }
    }, 800);
  }

  _startAuto() {
    this._startCommon();
  }

  _startManual() {
    this._startCommon();
  }

  _startCommon() {
    if (this.walk.isActive()) return;
    this.walk.start();
    // Patch the walkthrough's end() so completion marks the flag.
    const origEnd = this.walk.end.bind(this.walk);
    this.walk.end = () => {
      origEnd();
      try { localStorage.setItem(LS_KEY, '1'); } catch (_) { /* private mode */ }
      this.walk.end = origEnd;
    };
  }
}
```

- [ ] **Step 3: Mount in Dashboard.js**

In `frontend/src/dashboard/Dashboard.js`, add the import:

```javascript
import { WalkthroughTrigger } from './components/WalkthroughTrigger.js';
```

In the constructor, add the element lookup:

```javascript
this.walkBtnEl = document.getElementById('nv-walk-trigger');
```

After other component mounts (BenchmarkPanel, PersonalityEditor):

```javascript
if (this.walkBtnEl) {
  this.walkthroughTrigger = new WalkthroughTrigger(this.walkBtnEl);
  this.walkthroughTrigger.initAutoStart();
}
```

- [ ] **Step 4: Add trigger button styles**

Append to `frontend/src/dashboard/dashboard.css`:

```css
#nv-walk-trigger {
  position: fixed;
  top: 0.8em;
  right: 3.5em;  /* sits next to the drawer toggle */
  width: 2em; height: 2em;
  border-radius: 50%;
  border: 1px solid currentColor;
  background: transparent;
  cursor: pointer;
  font: 600 1em/1 sans-serif;
  z-index: 1000;
  opacity: 0.7;
}
#nv-walk-trigger:hover { opacity: 1; }
```

- [ ] **Step 5: First-load acceptance**

Clear the flag from the previous task's smoke test:

```javascript
// In browser console:
localStorage.removeItem('nodeava.walkthrough.completed');
```

Reload `http://localhost:5173`. Expected: after ~800ms the walkthrough auto-starts on Step 1. Click through to Done. Reload again. Expected: no auto-start.

- [ ] **Step 6: Manual re-trigger acceptance**

Click the "?" button in the header. Expected: walkthrough starts again from Step 1 regardless of localStorage flag.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/dashboard/components/WalkthroughTrigger.js frontend/src/dashboard/Dashboard.js frontend/index.html frontend/src/dashboard/dashboard.css
git commit -m "feat(dashboard): walkthrough auto-start on first load + ? re-trigger"
```

---

## Task 13: Deck reconciliation pass

A two-direction audit comparing shipped reality against the existing slide deck. Built reality is the source of truth.

**Files:**
- Create: `docs/deck-reconciliation-2026-05-17.md`

- [ ] **Step 1: Locate the deck**

Run from the repo root:

```bash
find . -maxdepth 4 \( -name '*.pptx' -o -name '*.key' -o -name 'deck*' -o -name 'slides*' -o -path '*workshop*deck*' \) -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/.venv/*' 2>/dev/null
```

If no deck file is found in-repo, ask Lucasmind for its location before continuing. The deck may live outside this repo.

- [ ] **Step 2: Inventory shipped reality**

Build a list of every user-visible feature from Plans #1-#10. Source it from:

- `docs/superpowers/specs/*.md` (one per plan)
- `docs/superpowers/plans/*.md` (acceptance criteria)
- `configs/catalog.yml` (brains / voices / avatars / personalities)
- `services/orchestrator/orchestrator/routes/` (endpoints)
- `scripts/demos/` (CLI parity scripts)
- `frontend/src/dashboard/` (UI surfaces)

Produce a flat list. Don't worry about hierarchy — one line per feature.

- [ ] **Step 3: Map deck → reality**

For each slide / demo / claim in the deck, find the matching shipped feature. Note three categories:

- **MATCH** — deck and reality agree (no action).
- **DECK NOT BUILT** — deck references something missing. Tag with recommendation: `build`, `cut`, or `reword`.
- **BUILT NOT IN DECK** — feature shipped but not surfaced in the deck. Note where it would naturally insert (which block / which neighboring slide).

- [ ] **Step 4: Write the audit doc**

Create `docs/deck-reconciliation-2026-05-17.md`:

```markdown
# Deck Reconciliation — 2026-05-17

**Posture:** Built reality is the source of truth. The deck adapts to what
shipped — either by adding new content, cutting unbuilt references, or
rewording overstated claims. The build / cut / reword decisions in List B
belong to the deck owner.

**Audit run by:** Plan #10 Task 13
**Inventory source:** `git log`, `docs/superpowers/specs/`, `configs/catalog.yml`,
`services/orchestrator/orchestrator/routes/`, `scripts/demos/`,
`frontend/src/dashboard/`

---

## List A — Built but not in deck

For each item: where shipped, suggested deck-insertion location.

| Feature | Shipped in | Suggested deck slot |
|---------|-----------|---------------------|
| _(fill from Step 3)_ | _(plan ref)_ | _(which block / before-after which slide)_ |

---

## List B — In deck but not built

For each item: deck reference, recommendation (build / cut / reword), one-line
rationale.

| Slide ref | Claim | Recommendation | Rationale |
|-----------|-------|----------------|-----------|
| _(fill from Step 3)_ | _(quote)_ | _(build / cut / reword)_ | _(why)_ |

---

## Summary

- **List A count:** _(N)_ items to add to the deck.
- **List B count:** _(N)_ items needing decision — _(X build, Y cut, Z reword)_.
- **Items needing decision before workshop day:** _(itemized)_.
```

Fill in the tables from Step 3.

- [ ] **Step 5: Commit**

```bash
git add docs/deck-reconciliation-2026-05-17.md
git commit -m "docs: deck reconciliation audit (Plan #10 Task 13)"
```

---

## After all tasks complete

- Run `git log --oneline workshop/main..HEAD` to confirm all 13 task commits landed.
- Run the full orchestrator pytest suite from `services/orchestrator/`: `.venv/bin/pytest -q`. Expected: no regressions.
- Manual end-to-end walkthrough in the browser:
  1. Clear `localStorage.removeItem('nodeava.walkthrough.completed')` and reload — confirm auto-tour fires.
  2. Run a benchmark on the default brain, swap brains, benchmark again — confirm comparison table grows.
  3. Speak a wiki-tool question — confirm verbal filler fires before tool returns.
  4. Edit personality to a pirate prompt — confirm next reply uses pirate persona.
  5. Swap avatar through all 4 gallery entries — confirm each reloads cleanly with intact lip sync.
- Push to `workshop/main` once acceptance is clean.
