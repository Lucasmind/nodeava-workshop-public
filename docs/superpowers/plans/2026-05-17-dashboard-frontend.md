# Dashboard Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the workshop dashboard — a right-side drawer over the avatar that surfaces Plan #7's swap endpoints with a live spatial flow diagram + event log.

**Architecture:** Vanilla JS matching the existing frontend pattern. New `frontend/src/dashboard/` directory containing `Dashboard.js` (drawer container), `api.js` (fetch wrappers), `state.js` (local cache + EventTarget for pipeline events), and four components (`ControlsPanel`, `FlowDiagram`, `EventLog`, `Selector`). Existing `Orchestrator.js`, `STTManager.js`, `TTSManager.js`, `AvatarManager.js` extend their handler patterns to also emit events to the dashboard.

**Tech Stack:** Vanilla JavaScript (no framework). DOM + EventTarget API. Vite dev server. CSS classes prefixed `.nv-dash-` to avoid collision with existing styles.

**Security note:** All DOM building uses `createElement` + `textContent` / `append`. Never `innerHTML`. Content from `/v1/catalog` could in principle include attacker-controlled strings (e.g., a personality label edited by a malicious actor with file-system access), so the dashboard treats all server-returned strings as untrusted.

**Spec:** `docs/superpowers/specs/2026-05-17-dashboard-frontend-design.md`

---

## File structure

### New files

| Path | Purpose |
|------|---------|
| `frontend/src/dashboard/Dashboard.js` | Top-level drawer container; mounts components; handles open/close |
| `frontend/src/dashboard/api.js` | Fetch wrappers: `getCatalog()`, `getState()`, `swap(kind, id, value)` |
| `frontend/src/dashboard/state.js` | `DashboardState` class — local mirror + EventTarget for pipeline events |
| `frontend/src/dashboard/components/Selector.js` | Reusable dropdown with optional residency chip slot |
| `frontend/src/dashboard/components/ControlsPanel.js` | Brain/voice/avatar/personality selectors + 2 tool toggles |
| `frontend/src/dashboard/components/FlowDiagram.js` | Spatial pipeline lanes; updates from pipeline events |
| `frontend/src/dashboard/components/EventLog.js` | Scrolling text log; rolling 100-line cap |
| `frontend/src/dashboard/dashboard.css` | Drawer + panel styling |

### Modified files

| Path | Change |
|------|--------|
| `frontend/index.html` | Add floating toggle button + drawer container `<div>` |
| `frontend/src/main.js` | Instantiate `Dashboard`; pass DashboardState to existing managers |
| `frontend/src/pipeline/Orchestrator.js` | Each existing event handler also emits to DashboardState |
| `frontend/src/stt/STTManager.js` | Emit `vad.started` / `vad.stopped` |
| `frontend/src/tts/TTSManager.js` | Emit `tts.playing` / `tts.done` |
| `frontend/src/avatar/AvatarManager.js` | Emit `avatar.speaking` / `avatar.idle` |
| `frontend/src/ui/components/ControlPanel.js` | Remove wiki/web_search toggles (migrate to dashboard) |
| `frontend/src/style.css` | Import dashboard.css |

---

## Task 1: Drawer shell + floating toggle button

**Files:**
- Modify: `frontend/index.html`
- Create: `frontend/src/dashboard/dashboard.css`
- Modify: `frontend/src/style.css` (import dashboard.css)

Pure HTML/CSS skeleton. No JS yet. After this task, opening `localhost:5173` shows the avatar + a floating button top-right. The drawer exists in the DOM but stays off-screen (Task 2 wires the toggle behavior).

- [ ] **Step 1: Read existing `frontend/index.html`**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
cat frontend/index.html
```

Note where the existing `<body>` content lives (avatar canvas div, ControlPanel mount point, etc.).

- [ ] **Step 2: Add the floating button + drawer markup to `frontend/index.html`**

Right BEFORE the closing `</body>` tag (or at the very end of body content, AFTER existing UI mounts), add:

```html
<!-- Plan #8: dashboard drawer + floating toggle -->
<button id="nv-dash-toggle" class="nv-dash-toggle" type="button" aria-label="Toggle dashboard" aria-expanded="false">
  <span class="nv-dash-toggle-icon">⏵</span>
</button>

<aside id="nv-dash-drawer" class="nv-dash-drawer" role="complementary" aria-label="NodeAva controls" aria-hidden="true">
  <header class="nv-dash-header">
    <h2>NodeAva</h2>
    <span class="nv-dash-hint">press <kbd>]</kbd> to toggle</span>
  </header>
  <section class="nv-dash-controls" id="nv-dash-controls"></section>
  <section class="nv-dash-flow-events">
    <div class="nv-dash-flow" id="nv-dash-flow"></div>
    <div class="nv-dash-events" id="nv-dash-events"></div>
  </section>
</aside>
```

- [ ] **Step 3: Create `frontend/src/dashboard/dashboard.css`**

```css
/* Plan #8 dashboard — drawer + panels.
 * All classes prefixed with .nv-dash- to avoid collision with existing
 * frontend/src/style.css.
 */

/* Floating toggle button (top-right) */
.nv-dash-toggle {
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 1000;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: rgba(30, 41, 59, 0.85);
  color: #e2e8f0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: background 150ms;
  backdrop-filter: blur(6px);
}
.nv-dash-toggle:hover {
  background: rgba(51, 65, 85, 0.95);
}
.nv-dash-toggle-icon {
  display: inline-block;
  transition: transform 250ms ease-out;
}
.nv-dash-toggle[aria-expanded="true"] .nv-dash-toggle-icon {
  transform: rotate(180deg);
}

/* Drawer (slides in from right) */
.nv-dash-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 380px;
  height: 100vh;
  z-index: 999;
  background: #0d1117;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #334155;
  transform: translateX(100%);
  transition: transform 250ms ease-out;
  font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
}
.nv-dash-drawer[aria-hidden="false"] {
  transform: translateX(0);
}

@media (max-width: 768px) {
  .nv-dash-drawer { width: 100vw; }
}

/* Drawer header */
.nv-dash-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 12px 16px;
  border-bottom: 1px solid #334155;
  background: #161b22;
}
.nv-dash-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.nv-dash-hint {
  font-size: 11px;
  opacity: 0.55;
}
.nv-dash-hint kbd {
  background: #1e293b;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
}

/* Controls panel (top ~40%) */
.nv-dash-controls {
  flex: 0 0 auto;
  padding: 12px 16px;
  border-bottom: 2px solid #1e3a5f;
  background: #0f1626;
  max-height: 40vh;
  overflow-y: auto;
}

/* Flow + Events panel (bottom ~60%) */
.nv-dash-flow-events {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.nv-dash-flow {
  flex: 0 0 auto;
  padding: 12px 16px;
  background: #0a0f1a;
  border-bottom: 1px solid #1e293b;
}
.nv-dash-events {
  flex: 1 1 auto;
  padding: 8px 12px;
  background: #000;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11px;
  line-height: 1.5;
  overflow-y: auto;
  color: #94a3b8;
}
```

- [ ] **Step 4: Wire `dashboard.css` into the existing stylesheet pipeline**

Read `frontend/src/style.css`:

```bash
head -5 frontend/src/style.css
```

At the very top, ADD:

```css
@import './dashboard/dashboard.css';
```

If `frontend/src/style.css` is imported from `main.js` or `index.html`, this `@import` will pull in the dashboard styles. Confirm:

```bash
grep -rn "style.css" frontend/src/ frontend/index.html
```

If `style.css` isn't imported from anywhere visible, search for the import path used in the app. Add the @import at the top of whichever .css file is the root of the chain.

- [ ] **Step 5: Smoke test with the Vite dev server**

Vite should auto-reload after the changes. Confirm:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
```

Expected: 200. If Vite is not running, start it:

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/frontend
npm run dev -- --port 5173 --host &
```

Open `http://localhost:5173/` in a browser. Verify:
- The avatar canvas still renders
- A floating button (small dark square with ⏵) appears top-right
- The drawer is OFF-SCREEN (translated 100% right). It's in the DOM but invisible — clicking the button does nothing yet (Task 2 wires the JS toggle).

Inspect the DOM (devtools Elements): the `<aside id="nv-dash-drawer">` should be present with `aria-hidden="true"`.

- [ ] **Step 6: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/index.html frontend/src/dashboard/dashboard.css frontend/src/style.css
git commit -m "feat(frontend): dashboard drawer shell + floating toggle button"
```

---

## Task 2: Dashboard scaffolding (api + state + container)

**Files:**
- Create: `frontend/src/dashboard/api.js`
- Create: `frontend/src/dashboard/state.js`
- Create: `frontend/src/dashboard/Dashboard.js`
- Modify: `frontend/src/main.js`

Wires the toggle button, fetches catalog + state on init, renders a placeholder summary in the Controls section (e.g., "brain: qwen3-4b ...") to prove the data flow. No selectors yet.

- [ ] **Step 1: Create `frontend/src/dashboard/api.js`**

```javascript
/**
 * Plan #8 dashboard — fetch wrappers for /v1/catalog, /v1/state, /v1/swap.
 *
 * All requests go through the Vite proxy at /api/orch (configured in
 * vite.config.js to forward to localhost:8082).
 */

const BASE = '/api/orch';

export async function getCatalog() {
  const resp = await fetch(`${BASE}/v1/catalog`);
  if (!resp.ok) throw new Error(`getCatalog: HTTP ${resp.status}`);
  return await resp.json();
}

export async function getState() {
  const resp = await fetch(`${BASE}/v1/state`);
  if (!resp.ok) throw new Error(`getState: HTTP ${resp.status}`);
  return await resp.json();
}

/**
 * @param {string} kind one of "brain", "voice", "avatar", "personality", "tools"
 * @param {string} id catalog entry id, or tool name when kind=="tools"
 * @param {boolean|undefined} value required when kind=="tools"
 * @returns {Promise<object>} the new full state response (same shape as getState)
 */
export async function swap(kind, id, value) {
  const body = { kind, id };
  if (value !== undefined) body.value = value;
  const resp = await fetch(`${BASE}/v1/swap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
    throw new Error(err.error || `swap failed: HTTP ${resp.status}`);
  }
  return await resp.json();
}
```

- [ ] **Step 2: Create `frontend/src/dashboard/state.js`**

```javascript
/**
 * Plan #8 dashboard — local mirror of server-side state + event channel
 * for pipeline events.
 *
 * Pipeline events come from Orchestrator.js, STTManager.js, TTSManager.js,
 * AvatarManager.js. Components subscribe via addEventListener('pipeline', ...).
 *
 * Server state (catalog + active selections) is fetched at mount time
 * via api.js and stored in `this.catalog` and `this.serverState`. After
 * each swap, the response updates this mirror.
 */

export class DashboardState extends EventTarget {
  constructor() {
    super();
    /** @type {object|null} the full /v1/catalog response */
    this.catalog = null;
    /** @type {object|null} the full /v1/state response */
    this.serverState = null;
  }

  /**
   * Emit a pipeline event to subscribers.
   * @param {string} type one of: stt.started, stt.transcript, llm.first_token,
   *   tool_call_start, tool_call_end, stage_timing, tts.playing, tts.done,
   *   avatar.speaking, avatar.idle, vad.started, vad.stopped, *.error
   * @param {object} payload event-specific data
   */
  emit(type, payload = {}) {
    this.dispatchEvent(new CustomEvent('pipeline', { detail: { type, payload, ts: Date.now() } }));
  }

  /**
   * Update the cached server state (called after fetch or swap).
   */
  setServerState(state) {
    this.serverState = state;
    this.dispatchEvent(new CustomEvent('state', { detail: state }));
  }

  /**
   * Lookup helpers for the catalog.
   */
  getBrain(id) {
    return this.catalog?.brains?.find((b) => b.id === id) || null;
  }
  getVoice(id) {
    return this.catalog?.voices?.find((v) => v.id === id) || null;
  }
  getAvatar(id) {
    return this.catalog?.avatars?.find((a) => a.id === id) || null;
  }
  getPersonality(id) {
    return this.catalog?.personalities?.find((p) => p.id === id) || null;
  }
}
```

- [ ] **Step 3: Create `frontend/src/dashboard/Dashboard.js`**

```javascript
/**
 * Plan #8 dashboard — top-level drawer container.
 *
 * Owns the drawer open/close state, mounts child components, listens for
 * keyboard shortcut. Children (ControlsPanel, FlowDiagram, EventLog) are
 * added in later tasks.
 *
 * Security: all server-returned strings (catalog labels, brain ids, etc.)
 * are placed in the DOM via textContent, never innerHTML.
 */

import * as api from './api.js';

export class Dashboard {
  /**
   * @param {DashboardState} state the shared dashboard state + event channel
   */
  constructor(state) {
    this.state = state;
    this.drawerEl = document.getElementById('nv-dash-drawer');
    this.toggleEl = document.getElementById('nv-dash-toggle');
    this.controlsEl = document.getElementById('nv-dash-controls');
    if (!this.drawerEl || !this.toggleEl) {
      throw new Error('Dashboard: drawer or toggle element missing from DOM');
    }
    this._wireToggle();
    this._wireKeyboard();
    this._loadInitial();
  }

  _wireToggle() {
    this.toggleEl.addEventListener('click', () => this.toggle());
  }

  _wireKeyboard() {
    document.addEventListener('keydown', (e) => {
      // Only trigger if not typing in a text input
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.key === ']') {
        e.preventDefault();
        this.toggle();
      }
    });
  }

  toggle() {
    const open = this.drawerEl.getAttribute('aria-hidden') === 'false';
    this.setOpen(!open);
  }

  setOpen(open) {
    this.drawerEl.setAttribute('aria-hidden', open ? 'false' : 'true');
    this.toggleEl.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  async _loadInitial() {
    try {
      const [catalog, state] = await Promise.all([api.getCatalog(), api.getState()]);
      this.state.catalog = catalog;
      this.state.setServerState(state);
      this._renderPlaceholder();
    } catch (err) {
      console.error('[Dashboard] init failed:', err);
      this.controlsEl.replaceChildren();
      this.controlsEl.appendChild(this._textNode('Dashboard offline (orchestrator unreachable)'));
    }
  }

  _textNode(text) {
    return document.createTextNode(text);
  }

  // Placeholder render — replaced by ControlsPanel in Task 4.
  _renderPlaceholder() {
    const active = this.state.serverState?.active;
    if (!active) return;
    this.controlsEl.replaceChildren();
    const wrap = document.createElement('div');
    wrap.className = 'nv-dash-placeholder';
    for (const [label, value] of [
      ['brain', active.brain],
      ['voice', active.voice],
      ['avatar', active.avatar],
      ['personality', active.personality],
    ]) {
      const row = document.createElement('div');
      row.append(label + ': ');
      const strong = document.createElement('strong');
      strong.textContent = String(value);
      row.appendChild(strong);
      wrap.appendChild(row);
    }
    const tools = document.createElement('div');
    tools.textContent = `wiki: ${active.tools?.wiki ? '✓' : '☐'} · web: ${active.tools?.web_search ? '✓' : '☐'}`;
    wrap.appendChild(tools);
    this.controlsEl.appendChild(wrap);
  }
}
```

- [ ] **Step 4: Modify `frontend/src/main.js` — instantiate Dashboard**

Read the current file:

```bash
grep -n "import\|new\|window\.\|main" frontend/src/main.js | head -20
```

At the top with other imports, ADD:

```javascript
import { Dashboard } from './dashboard/Dashboard.js';
import { DashboardState } from './dashboard/state.js';
```

In the main initialization block (wherever other managers like `AvatarManager`, `Orchestrator` are constructed), ADD:

```javascript
// Plan #8: dashboard
const dashboardState = new DashboardState();
const dashboard = new Dashboard(dashboardState);
```

The instantiation should happen AFTER the DOM is ready (after document `DOMContentLoaded` if the existing managers use that pattern, otherwise inline at the top-level module — Vite handles module-defer semantics).

- [ ] **Step 5: Smoke test**

Vite auto-reloads. Open `http://localhost:5173/` in the browser.

Expected behavior:
- Clicking the floating button OPENS the drawer (slides in from right)
- The drawer shows a placeholder with "brain: qwen3-4b", "voice: bella", etc. (the active state from the orchestrator)
- Pressing `]` toggles the drawer
- No console errors

If the drawer shows "Dashboard offline" — the orchestrator isn't reachable. Verify:

```bash
curl -s http://localhost:8082/v1/state | head -c 200
```

Should return JSON. If not, the orchestrator container needs to be up.

If the Vite proxy fails on `/api/orch`, verify `frontend/vite.config.js` has the entry (added in Plan #7 Task 9):

```bash
grep -A 4 "/api/orch" frontend/vite.config.js
```

- [ ] **Step 6: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/dashboard/ frontend/src/main.js
git commit -m "feat(frontend): dashboard scaffolding (api + state + Dashboard container)"
```

---

## Task 3: Selector component (reusable dropdown)

**Files:**
- Create: `frontend/src/dashboard/components/Selector.js`

A reusable component that renders a labeled `<select>` with an optional right-side chip slot (for the residency indicator). Used by ControlsPanel in Task 4.

- [ ] **Step 1: Create `frontend/src/dashboard/components/Selector.js`**

```javascript
/**
 * Plan #8 — reusable selector component.
 *
 * Usage:
 *   const sel = new Selector({
 *     label: 'Brain',
 *     options: [
 *       {value:'qwen3-4b', label:'Qwen3 4B', available:true, reason:null},
 *       {value:'claude-sonnet', label:'Claude Sonnet', available:false, reason:'set ANTHROPIC_API_KEY'},
 *     ],
 *     value: 'qwen3-4b',
 *     onChange: async (newValue) => { ... },
 *     showChip: true, // optional residency chip slot
 *   });
 *   parent.appendChild(sel.el);
 *   sel.setChip({label:'gpu', color:'green'}); // optional
 *
 * All option labels are inserted via textContent (no HTML injection).
 */

export class Selector {
  constructor({ label, options, value, onChange, showChip = false }) {
    this.onChange = onChange;
    this.el = document.createElement('div');
    this.el.className = 'nv-dash-row';

    const labelEl = document.createElement('div');
    labelEl.className = 'nv-dash-row-label';
    labelEl.textContent = label;
    this.el.appendChild(labelEl);

    const controlRow = document.createElement('div');
    controlRow.className = 'nv-dash-row-control';
    this.el.appendChild(controlRow);

    this.selectEl = document.createElement('select');
    this.selectEl.className = 'nv-dash-select';
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label + (opt.available === false ? ' (unavailable)' : '');
      if (opt.available === false) {
        o.disabled = true;
        if (opt.reason) o.title = opt.reason;
      }
      this.selectEl.appendChild(o);
    }
    this.selectEl.value = value;
    this.selectEl.addEventListener('change', () => this._handleChange());
    controlRow.appendChild(this.selectEl);

    if (showChip) {
      this.chipEl = document.createElement('span');
      this.chipEl.className = 'nv-dash-chip nv-dash-chip-empty';
      controlRow.appendChild(this.chipEl);
    }

    this.errorEl = document.createElement('div');
    this.errorEl.className = 'nv-dash-row-error';
    this.el.appendChild(this.errorEl);
  }

  async _handleChange() {
    const newValue = this.selectEl.value;
    this.errorEl.textContent = '';
    try {
      await this.onChange(newValue);
    } catch (err) {
      // Show error inline; selector value stays at user's choice (no auto-revert).
      this.errorEl.textContent = err.message || String(err);
    }
  }

  setValue(value) {
    this.selectEl.value = value;
  }

  /**
   * Update the chip (residency or status indicator).
   * @param {{label:string, color:'green'|'yellow'|'red'|'gray'|'blue'}|null} chip
   *   pass null to clear.
   */
  setChip(chip) {
    if (!this.chipEl) return;
    if (!chip) {
      this.chipEl.textContent = '';
      this.chipEl.className = 'nv-dash-chip nv-dash-chip-empty';
      return;
    }
    this.chipEl.textContent = chip.label;
    this.chipEl.className = `nv-dash-chip nv-dash-chip-${chip.color}`;
  }
}
```

- [ ] **Step 2: Add selector styles to `frontend/src/dashboard/dashboard.css`**

Append to `frontend/src/dashboard/dashboard.css`:

```css
/* Row layout (used by ControlsPanel) */
.nv-dash-row {
  margin-bottom: 10px;
}
.nv-dash-row-label {
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #64748b;
  margin-bottom: 3px;
}
.nv-dash-row-control {
  display: flex;
  align-items: center;
  gap: 6px;
}
.nv-dash-row-error {
  min-height: 14px;
  margin-top: 3px;
  font-size: 11px;
  color: #f87171;
  opacity: 0;
  transition: opacity 200ms;
}
.nv-dash-row-error:not(:empty) {
  opacity: 1;
}

/* Select dropdown */
.nv-dash-select {
  flex: 1 1 auto;
  background: #1e293b;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 13px;
  font-family: inherit;
}
.nv-dash-select:focus {
  outline: none;
  border-color: #3b82f6;
}
.nv-dash-select option:disabled {
  color: #475569;
}

/* Chip (residency etc.) */
.nv-dash-chip {
  flex: 0 0 auto;
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.nv-dash-chip::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.9;
}
.nv-dash-chip-green { background: rgba(16, 185, 129, 0.18); color: #10b981; }
.nv-dash-chip-yellow { background: rgba(234, 179, 8, 0.18); color: #eab308; }
.nv-dash-chip-red { background: rgba(239, 68, 68, 0.18); color: #ef4444; }
.nv-dash-chip-gray { background: rgba(100, 116, 139, 0.18); color: #94a3b8; }
.nv-dash-chip-blue { background: rgba(59, 130, 246, 0.18); color: #3b82f6; }
.nv-dash-chip-empty { display: none; }

/* Tool toggle row */
.nv-dash-tool-row {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.nv-dash-tool-row label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  cursor: pointer;
}
.nv-dash-tool-row input[type="checkbox"] {
  margin: 0;
}
```

- [ ] **Step 3: Smoke test (no UI change visible yet)**

The component isn't mounted anywhere yet — Task 4 uses it. Just verify the file parses by reloading the dev server:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
```

Expected: 200. Check the browser console at `localhost:5173` for any syntax errors.

- [ ] **Step 4: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/dashboard/components/Selector.js frontend/src/dashboard/dashboard.css
git commit -m "feat(frontend): reusable Selector component with chip slot"
```

---

## Task 4: ControlsPanel (4 selectors + 2 tool toggles)

**Files:**
- Create: `frontend/src/dashboard/components/ControlsPanel.js`
- Modify: `frontend/src/dashboard/Dashboard.js` (replace placeholder with ControlsPanel)

After this task, the drawer shows fully functional selectors. Changing any selector POSTs to /v1/swap and updates the local state.

- [ ] **Step 1: Create `frontend/src/dashboard/components/ControlsPanel.js`**

```javascript
/**
 * Plan #8 — Controls panel inside the drawer.
 *
 * Renders brain/voice/avatar/personality selectors + web_search/wiki toggles.
 * Each change POSTs to /v1/swap via api.js. Brain selector shows a residency
 * chip pulled from state.system.ollama.loaded.
 *
 * All option labels reach the DOM via Selector.js which uses textContent.
 */

import * as api from '../api.js';
import { Selector } from './Selector.js';

export class ControlsPanel {
  /**
   * @param {HTMLElement} mountEl where to mount
   * @param {DashboardState} state the shared dashboard state
   */
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this._build();
    // Re-render on server-state updates (after swaps)
    this.state.addEventListener('state', () => this._refresh());
  }

  _build() {
    this.mountEl.replaceChildren();

    const cat = this.state.catalog;
    const active = this.state.serverState?.active;
    if (!cat || !active) {
      this.mountEl.appendChild(document.createTextNode('Dashboard initializing…'));
      return;
    }

    this.brainSel = new Selector({
      label: 'Brain',
      options: cat.brains.map((b) => ({
        value: b.id,
        label: b.label,
        available: b.available,
        reason: b.reason,
      })),
      value: active.brain,
      showChip: true,
      onChange: async (newId) => {
        const resp = await api.swap('brain', newId);
        this.state.setServerState(resp);
      },
    });
    this.mountEl.appendChild(this.brainSel.el);

    this.voiceSel = new Selector({
      label: 'Voice',
      options: cat.voices.map((v) => ({ value: v.id, label: v.label, available: v.available })),
      value: active.voice,
      onChange: async (newId) => {
        const resp = await api.swap('voice', newId);
        this.state.setServerState(resp);
        if (window.__ttsManager?.refreshVoiceFromState) {
          await window.__ttsManager.refreshVoiceFromState();
        }
      },
    });
    this.mountEl.appendChild(this.voiceSel.el);

    this.avatarSel = new Selector({
      label: 'Avatar',
      options: cat.avatars.map((a) => ({ value: a.id, label: a.label, available: a.available })),
      value: active.avatar,
      onChange: async (newId) => {
        const resp = await api.swap('avatar', newId);
        this.state.setServerState(resp);
        const newGlb = cat.avatars.find((a) => a.id === newId)?.glb_path;
        if (newGlb && window.__avatarManager) {
          window.__avatarManager.loadAvatar(newGlb);
        }
      },
    });
    this.mountEl.appendChild(this.avatarSel.el);

    this.personalitySel = new Selector({
      label: 'Personality',
      options: cat.personalities.map((p) => ({ value: p.id, label: p.label, available: p.available })),
      value: active.personality,
      onChange: async (newId) => {
        const resp = await api.swap('personality', newId);
        this.state.setServerState(resp);
      },
    });
    this.mountEl.appendChild(this.personalitySel.el);

    // Tool toggles
    const toolRow = document.createElement('div');
    toolRow.className = 'nv-dash-tool-row';

    this.wikiLabel = this._buildToggle({
      name: 'wiki',
      label: '📚 Wiki',
      checked: !!active.tools?.wiki,
    });
    toolRow.appendChild(this.wikiLabel);

    this.webLabel = this._buildToggle({
      name: 'web_search',
      label: '🔍 Web search',
      checked: !!active.tools?.web_search,
    });
    toolRow.appendChild(this.webLabel);

    this.mountEl.appendChild(toolRow);

    this._updateChip();
  }

  _buildToggle({ name, label, checked }) {
    const wrap = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = checked;
    cb.dataset.tool = name;
    cb.addEventListener('change', async () => {
      try {
        const resp = await api.swap('tools', name, cb.checked);
        this.state.setServerState(resp);
      } catch (err) {
        console.error('[ControlsPanel] tool swap failed:', err);
        cb.checked = !cb.checked; // revert UI
      }
    });
    wrap.appendChild(cb);
    wrap.append(' ' + label);
    return wrap;
  }

  _refresh() {
    const active = this.state.serverState?.active;
    if (!active) return;
    if (this.brainSel) this.brainSel.setValue(active.brain);
    if (this.voiceSel) this.voiceSel.setValue(active.voice);
    if (this.avatarSel) this.avatarSel.setValue(active.avatar);
    if (this.personalitySel) this.personalitySel.setValue(active.personality);
    if (this.wikiLabel) this.wikiLabel.querySelector('input').checked = !!active.tools?.wiki;
    if (this.webLabel) this.webLabel.querySelector('input').checked = !!active.tools?.web_search;
    this._updateChip();
  }

  _updateChip() {
    if (!this.brainSel) return;
    const active = this.state.serverState?.active;
    const ollama = this.state.serverState?.system?.ollama;
    if (!active || !ollama) return;

    const brainEntry = this.state.getBrain(active.brain);
    if (!brainEntry) {
      this.brainSel.setChip(null);
      return;
    }

    if (brainEntry.kind === 'cloud-litellm') {
      this.brainSel.setChip({ label: 'cloud', color: 'blue' });
      return;
    }
    if (brainEntry.kind === 'openai-compatible') {
      this.brainSel.setChip({ label: 'external', color: 'gray' });
      return;
    }
    // kind: ollama — look up in loaded list
    const loaded = (ollama.loaded || []).find((m) => m.model === brainEntry.model);
    if (!loaded) {
      this.brainSel.setChip({ label: 'unloaded', color: 'gray' });
      return;
    }
    const colorMap = { gpu: 'green', split: 'yellow', cpu: 'red' };
    this.brainSel.setChip({
      label: loaded.residency,
      color: colorMap[loaded.residency] || 'gray',
    });
  }
}
```

- [ ] **Step 2: Modify `Dashboard.js` to mount ControlsPanel**

Find this import line at the top of `Dashboard.js`:

```javascript
import * as api from './api.js';
```

ADD below it:

```javascript
import { ControlsPanel } from './components/ControlsPanel.js';
```

Find the `_renderPlaceholder()` method and REPLACE it (and its call site) with `_mountControls()`. Specifically:

Replace `_renderPlaceholder()` (the whole method body, including the function declaration) with:

```javascript
  _mountControls() {
    this.controlsPanel = new ControlsPanel(this.controlsEl, this.state);
  }
```

Inside `_loadInitial()`, find `this._renderPlaceholder();` and change it to `this._mountControls();`.

- [ ] **Step 3: Smoke test**

Reload `http://localhost:5173/` after Vite auto-reloads:

1. Open the drawer (toggle button or `]`)
2. Verify 4 dropdowns + 2 checkboxes render
3. Each dropdown shows the catalog options; current state selected
4. Brain selector has a chip on the right showing the residency (gpu/split/cpu/unloaded)
5. Open Network tab → change a selector → see POST `/api/orch/v1/swap` with the right body
6. Refresh page → drawer reopens with the previously-selected values (because server state persists)

Test 5 specifically:
- Change Brain dropdown → POST body `{"kind":"brain","id":"smollm2-360m"}`
- Toggle Wiki → POST body `{"kind":"tools","id":"wiki","value":false}` (or true)

If anything fails, check the browser console for errors.

- [ ] **Step 4: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/dashboard/
git commit -m "feat(frontend): ControlsPanel with brain/voice/avatar/personality/tools"
```

---

## Task 5: Wire AvatarManager + TTSManager + manager globals

**Files:**
- Modify: `frontend/src/main.js`
- Modify: `frontend/src/tts/TTSManager.js`

`ControlsPanel.js` (Task 4) calls `window.__avatarManager.loadAvatar(newGlb)` and `window.__ttsManager.refreshVoiceFromState()` after avatar/voice swaps. This task adds those handles and exposes the existing manager instances on `window` for the dashboard's reach-in calls. We also add `refreshVoiceFromState()` to TTSManager if it doesn't exist.

- [ ] **Step 1: Expose manager handles on `window` in `frontend/src/main.js`**

Check the existing manager variable names:

```bash
grep -nE "new (AvatarManager|TTSManager|STTManager|Orchestrator)" frontend/src/main.js
```

After the line that constructs each manager (e.g., `const avatarManager = new AvatarManager(...)`), ADD an assignment to `window`. Place all four together as a block right after the last manager is built:

```javascript
// Plan #8: expose handles for the dashboard to reach into existing managers
// after a swap (e.g., avatar swap → reload .glb, voice swap → refresh
// TTSManager._voice). Vanilla JS reach-in is simpler than a more elaborate
// event subscription for these one-direction calls.
window.__avatarManager = avatarManager;
window.__ttsManager = ttsManager;
window.__sttManager = sttManager;
window.__orchestrator = orchestrator;
window.__dashboardState = dashboardState;
```

Replace `avatarManager` / `ttsManager` / etc. with whatever names main.js uses.

- [ ] **Step 2: Add `refreshVoiceFromState()` to `frontend/src/tts/TTSManager.js`**

Read the existing setVoice + state-load methods:

```bash
grep -n "setVoice\|_loadVoiceFromState\|_voice" frontend/src/tts/TTSManager.js
```

There should already be `_loadVoiceFromState()` (added in Plan #7 Task 9) and `setVoice(voiceName)`. ADD a new public method that re-runs the state-load:

```javascript
  /**
   * Plan #8: re-fetch state and apply the new active voice.
   * Called by the dashboard after a voice swap so the next utterance
   * uses the new voice immediately.
   */
  async refreshVoiceFromState() {
    await this._loadVoiceFromState();
  }
```

Place it next to `_loadVoiceFromState()` for proximity.

- [ ] **Step 3: Smoke test**

Reload `http://localhost:5173/`:

1. Open drawer
2. In browser console, verify the globals: type `window.__avatarManager` — should be a non-null object.
3. Talk into mic, ask "say hello in 5 words" — note the voice.
4. Change Voice dropdown to a different voice (e.g., "Nova")
5. Verify POST /v1/swap fires (Network tab)
6. Talk into mic again, ask same question
7. Verify the avatar speaks in the NEW voice

For avatar:
1. (If only one avatar in catalog this is skippable.) If multiple: change Avatar dropdown → verify the 3D model swaps in the canvas.

- [ ] **Step 4: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/
git commit -m "feat(frontend): expose manager globals + refreshVoiceFromState for dashboard swaps"
```

---

## Task 6: Pipeline event emitter wiring

**Files:**
- Modify: `frontend/src/main.js`
- Modify: `frontend/src/pipeline/Orchestrator.js`
- Modify: `frontend/src/stt/STTManager.js`
- Modify: `frontend/src/tts/TTSManager.js`
- Modify: `frontend/src/avatar/AvatarManager.js`

Wire the DashboardState's `emit()` method into the existing event flow. After this task, the dashboard state receives a stream of typed pipeline events. No new UI yet — Tasks 7+8 render from this stream.

- [ ] **Step 1: Pass DashboardState into the Orchestrator + managers**

Modify `frontend/src/main.js`. Find where managers are constructed.

Pass `dashboardState` to each:

```javascript
const orchestrator = new Orchestrator({ ..., dashboardState });
const sttManager = new STTManager({ ..., dashboardState });
const ttsManager = new TTSManager({ ..., dashboardState });
const avatarManager = new AvatarManager({ ..., dashboardState });
```

(Adapt syntax to however the existing constructors take args. If a constructor takes positional args rather than an options object, add `dashboardState` as a new optional last arg.)

For each manager's constructor, accept `dashboardState` (default `null`) and store as `this._dashboardState`:

```javascript
  constructor({ /* existing args */, dashboardState = null } = {}) {
    // existing assignments
    this._dashboardState = dashboardState;
  }
```

Do this for all four managers.

- [ ] **Step 2: Add event emissions in Orchestrator.js**

Read the existing handler patterns:

```bash
grep -n "onToken\|onToolCallStart\|onToolCallEnd\|onStageTiming\|onThinkingToken\|onDone\|onError" frontend/src/pipeline/Orchestrator.js | head
```

Find each named handler being passed to `chatCompletion`. For each one, ADD an emit call at the top of the body, BEFORE the existing logic. Examples:

`onToolCallStart`:

```javascript
        onToolCallStart: ({ id, name, arguments: args }) => {
          this._dashboardState?.emit('tool_call_start', { id, name, arguments: args });
          // existing body
          this._activeToolName = name;
          this._scheduleFiller();
          this.state.transition(this._toolKindFromName(name));
          if (this.onToolCallStart) this.onToolCallStart({ id, name, arguments: args });
        },
```

`onToolCallEnd`:

```javascript
        onToolCallEnd: ({ id, result_preview, duration_ms, error: toolErr }) => {
          this._dashboardState?.emit('tool_call_end', { id, name: this._activeToolName, result_preview, duration_ms, error: toolErr });
          // existing body...
        },
```

`onStageTiming`:

```javascript
        onStageTiming: (timing) => {
          this._dashboardState?.emit('stage_timing', timing);
          if (this.onStageTiming) this.onStageTiming(timing);
        },
```

`onThinkingToken`:

```javascript
        onThinkingToken: ({ delta }) => {
          this._dashboardState?.emit('thinking_token', { delta });
          // existing body...
        },
```

`onError`:

```javascript
        onError: ({ message }) => {
          this._dashboardState?.emit('error', { message });
          // existing body...
        },
```

`onDone`:

```javascript
        onDone: () => {
          this._dashboardState?.emit('done', {});
          // existing body...
        },
```

For `onToken` (the default-stream token chunks), emit `llm.first_token` only on the FIRST token of each round. Track a per-round flag. Find where rounds reset (likely in `onStageTiming` when `stage === 'round_start'`):

Add a field to the Orchestrator constructor:

```javascript
    this._tokensEmittedThisRound = false;
```

In `onStageTiming`, when `stage === 'round_start'`:

```javascript
        onStageTiming: (timing) => {
          this._dashboardState?.emit('stage_timing', timing);
          if (timing.stage === 'round_start') {
            this._tokensEmittedThisRound = false;
          }
          if (this.onStageTiming) this.onStageTiming(timing);
        },
```

In `onToken`:

```javascript
        onToken: ({ delta }) => {
          if (!this._tokensEmittedThisRound) {
            this._dashboardState?.emit('llm.first_token', { round: this._currentRound || 1 });
            this._tokensEmittedThisRound = true;
          }
          // existing body...
        },
```

If `_currentRound` isn't tracked, you can omit the `round` field or use the last seen `stage_timing` round_num.

- [ ] **Step 3: Add VAD events in STTManager.js**

Read VAD callbacks:

```bash
grep -n "vad\|onSpeechStart\|speech_start\|VAD\|SpeechProbabilityListener" frontend/src/stt/STTManager.js | head -10
```

Find the spot where speech-detection is reported. ADD:

```javascript
this._dashboardState?.emit('vad.started', {});
```

And for end-of-speech:

```javascript
this._dashboardState?.emit('vad.stopped', {});
```

When the actual transcript is dispatched (after Whisper returns the JSON):

```javascript
this._dashboardState?.emit('stt.transcript', { text: transcript, duration_ms: durationMs });
```

If there isn't a `durationMs` already tracked, time the STT call with `performance.now()` brackets and pass the result.

- [ ] **Step 4: Add TTS events in TTSManager.js**

Find where the first audio chunk plays:

```bash
grep -n "playback\|first_audio\|enqueue\|audio.play\|_play" frontend/src/tts/TTSManager.js | head
```

When audio playback begins for the first chunk of a turn:

```javascript
this._dashboardState?.emit('tts.playing', { text: textBeingSynthesized, voice: this._voice });
```

When playback finishes (queue empty):

```javascript
this._dashboardState?.emit('tts.done', {});
```

- [ ] **Step 5: Add avatar speech events in AvatarManager.js**

Find where TalkingHead starts/finishes lipsync:

```bash
grep -n "speak\|lipsync\|_speaking\|talkinghead\|onSpeechStart\|onSpeechEnd" frontend/src/avatar/AvatarManager.js | head
```

When speech begins:

```javascript
this._dashboardState?.emit('avatar.speaking', {});
```

When idle (speech finished):

```javascript
this._dashboardState?.emit('avatar.idle', {});
```

- [ ] **Step 6: Smoke test via browser console**

Reload `http://localhost:5173/`. Open browser devtools Console. Paste:

```javascript
window.__dashboardState.addEventListener('pipeline', (e) => {
  console.log('[pipe]', e.detail.type, e.detail.payload);
});
```

Then talk into the mic and complete a turn. Console should log a sequence like:

```
[pipe] vad.started {}
[pipe] vad.stopped {}
[pipe] stt.transcript {text: "...", duration_ms: 480}
[pipe] stage_timing {stage: "round_start", duration_ms: 0, round_num: 1}
[pipe] llm.first_token {round: 1}
[pipe] tool_call_start {name: "wiki.search", arguments: {...}}
[pipe] tool_call_end {...}
[pipe] stage_timing {stage: "round_end", duration_ms: 263, round_num: 1}
[pipe] tts.playing {text: "...", voice: "af_bella"}
[pipe] avatar.speaking {}
[pipe] avatar.idle {}
[pipe] tts.done {}
[pipe] done {}
```

If you don't see ALL of these, check each manager's emit call. Missing events are usually one of:
- The manager's constructor didn't accept `dashboardState`
- The emit call is in the wrong code path (e.g., wrong branch of an if)
- The handler is named differently than what I assumed

- [ ] **Step 7: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/
git commit -m "feat(frontend): pipeline events emit to DashboardState"
```

---

## Task 7: EventLog component (scrolling text log)

**Files:**
- Create: `frontend/src/dashboard/components/EventLog.js`
- Modify: `frontend/src/dashboard/Dashboard.js`
- Modify: `frontend/src/dashboard/dashboard.css`

After this task, the bottom of the drawer shows a live scrolling log of every pipeline event with timestamps + payload previews. Capped at 100 lines.

- [ ] **Step 1: Create `frontend/src/dashboard/components/EventLog.js`**

```javascript
/**
 * Plan #8 — Event log.
 *
 * Subscribes to DashboardState's `pipeline` event channel. Each event
 * appears as a single line: HH:MM:SS  type  payload-preview. Newest at top.
 * Capped at 100 visible lines; older lines are removed from the DOM.
 *
 * Security: all event payload strings are placed via textContent.
 */

const MAX_LINES = 100;

const COLOR_MAP = {
  'vad.started': '#10b981',
  'vad.stopped': '#10b981',
  'stt.transcript': '#10b981',
  'stt.error': '#ef4444',
  'llm.first_token': '#60a5fa',
  'stage_timing': '#64748b',
  'thinking_token': '#60a5fa',
  'tool_call_start': '#c084fc',
  'tool_call_end': '#c084fc',
  'tts.playing': '#eab308',
  'tts.done': '#eab308',
  'tts.error': '#ef4444',
  'avatar.speaking': '#60a5fa',
  'avatar.idle': '#64748b',
  'done': '#475569',
  'error': '#ef4444',
};

export class EventLog {
  /**
   * @param {HTMLElement} mountEl
   * @param {DashboardState} state
   */
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this._build();
    this.state.addEventListener('pipeline', (e) => {
      this._append(e.detail);
    });
  }

  _build() {
    this.mountEl.replaceChildren();
    const header = document.createElement('div');
    header.className = 'nv-dash-events-header';
    const h = document.createElement('span');
    h.textContent = 'EVENT LOG';
    header.appendChild(h);
    const clearBtn = document.createElement('button');
    clearBtn.textContent = 'clear';
    clearBtn.className = 'nv-dash-events-clear';
    clearBtn.type = 'button';
    clearBtn.addEventListener('click', () => this.clear());
    header.appendChild(clearBtn);
    this.mountEl.appendChild(header);

    this.listEl = document.createElement('div');
    this.listEl.className = 'nv-dash-events-list';
    this.mountEl.appendChild(this.listEl);
  }

  _append({ type, payload, ts }) {
    const line = document.createElement('div');
    line.className = 'nv-dash-event';
    const color = COLOR_MAP[type] || '#94a3b8';

    const time = document.createElement('span');
    time.className = 'nv-dash-event-time';
    time.style.color = color;
    time.textContent = new Date(ts).toTimeString().slice(0, 8);

    const name = document.createElement('span');
    name.className = 'nv-dash-event-name';
    name.textContent = ' ' + type;

    const preview = document.createElement('span');
    preview.className = 'nv-dash-event-preview';
    preview.textContent = ' ' + this._preview(type, payload);

    line.appendChild(time);
    line.appendChild(name);
    line.appendChild(preview);

    // Insert at top
    this.listEl.insertBefore(line, this.listEl.firstChild);

    // Trim to MAX_LINES
    while (this.listEl.children.length > MAX_LINES) {
      this.listEl.removeChild(this.listEl.lastChild);
    }
  }

  _preview(type, p) {
    if (!p) return '';
    if (type === 'stt.transcript' && p.text) return `"${p.text}"`;
    if (type === 'tool_call_start') {
      const args = p.arguments ? JSON.stringify(p.arguments) : '';
      return `${p.name || ''}${args ? ' · ' + args : ''}`;
    }
    if (type === 'tool_call_end') {
      const dur = p.duration_ms != null ? ` · ${p.duration_ms.toFixed(0)}ms` : '';
      const ok = p.error ? ' ✗' : ' ✓';
      return `${p.name || ''}${dur}${ok}`;
    }
    if (type === 'stage_timing') return `${p.stage || ''} · ${(p.duration_ms || 0).toFixed(0)}ms`;
    if (type === 'llm.first_token') return `round ${p.round || '?'}`;
    if (type === 'tts.playing' && p.voice) return `voice=${p.voice}`;
    if (type === 'error' && p.message) return p.message;
    return '';
  }

  clear() {
    this.listEl.replaceChildren();
  }
}
```

- [ ] **Step 2: Add EventLog styles to `dashboard.css`**

Append:

```css
.nv-dash-events-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: #475569;
  margin-bottom: 4px;
}
.nv-dash-events-clear {
  background: none;
  border: 1px solid #334155;
  color: #94a3b8;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  cursor: pointer;
}
.nv-dash-events-clear:hover {
  background: #1e293b;
}
.nv-dash-event {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nv-dash-event-time {
  font-weight: 600;
}
.nv-dash-event-name {
  color: #e2e8f0;
}
.nv-dash-event-preview {
  color: #64748b;
}
```

- [ ] **Step 3: Mount EventLog from Dashboard.js**

In `Dashboard.js`, add the import at the top:

```javascript
import { EventLog } from './components/EventLog.js';
```

Add a field in the constructor (alongside `this.controlsEl`):

```javascript
    this.eventsEl = document.getElementById('nv-dash-events');
```

Inside `_mountControls` (the method from Task 4), after the ControlsPanel construction, ADD:

```javascript
    this.eventLog = new EventLog(this.eventsEl, this.state);
```

- [ ] **Step 4: Smoke test**

Reload `http://localhost:5173/`. Open the drawer.

1. The bottom of the drawer shows an empty "EVENT LOG" header with a "clear" button
2. Talk into mic, ask a question
3. As events fire, log lines appear at the top of the events list with timestamps and color-coded event types
4. Older lines push down; the most recent appears at the top
5. Click "clear" — log empties

If lines don't appear, verify the pipeline events are firing via the console snippet from Task 6.

- [ ] **Step 5: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/dashboard/
git commit -m "feat(frontend): EventLog component renders pipeline events"
```

---

## Task 8: FlowDiagram component (spatial pipeline lanes)

**Files:**
- Create: `frontend/src/dashboard/components/FlowDiagram.js`
- Modify: `frontend/src/dashboard/Dashboard.js`
- Modify: `frontend/src/dashboard/dashboard.css`

The headline visual. Renders the pipeline as labeled lanes (mic → stt → transcript → llm → [tool branch] → tts → 🔊 avatar speech) that change color and show inline data based on pipeline events.

- [ ] **Step 1: Create `frontend/src/dashboard/components/FlowDiagram.js`**

```javascript
/**
 * Plan #8 — Flow diagram (spatial pipeline lanes).
 *
 * Each lane is a row with: glyph, label, inline status string, and a colored
 * left edge stripe indicating state (gray/green/blue/purple/red).
 *
 * Subscribes to DashboardState's `pipeline` channel. On each event, updates
 * the relevant lane's class + status text. On `vad.started`, resets all
 * lanes to idle for the new turn.
 *
 * Security: all dynamic strings go through textContent.
 */

const LANE_DEFS = [
  { id: 'mic',        glyph: '🎤', label: 'mic / vad' },
  { id: 'stt',        glyph: '↓',  label: 'stt · whisper' },
  { id: 'transcript', glyph: '',   label: '', isSub: true },
  { id: 'llm',        glyph: '↓',  label: 'llm' },
  { id: 'tool',       glyph: '↳',  label: '', isBranch: true, hidden: true },
  { id: 'tts',        glyph: '↓',  label: 'tts · kokoro' },
  { id: 'avatar',     glyph: '🔊', label: 'avatar speech' },
];

const STATE_CLASSES = {
  idle:   'nv-dash-lane-idle',
  active: 'nv-dash-lane-active',
  done:   'nv-dash-lane-done',
  tool:   'nv-dash-lane-tool',
  error:  'nv-dash-lane-error',
};

export class FlowDiagram {
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this._build();
    this.state.addEventListener('pipeline', (e) => this._handle(e.detail));
    this.state.addEventListener('state', () => this._refreshLabels());
  }

  _build() {
    this.mountEl.replaceChildren();
    const header = document.createElement('div');
    header.className = 'nv-dash-flow-header';
    header.textContent = 'FLOW';
    this.mountEl.appendChild(header);

    this.lanes = {};
    for (const def of LANE_DEFS) {
      const lane = document.createElement('div');
      const cls = ['nv-dash-lane', STATE_CLASSES.idle];
      if (def.isSub) cls.push('nv-dash-lane-sub');
      if (def.isBranch) cls.push('nv-dash-lane-branch');
      lane.className = cls.join(' ');
      if (def.hidden) lane.style.display = 'none';

      const glyph = document.createElement('span');
      glyph.className = 'nv-dash-lane-glyph';
      glyph.textContent = def.glyph;

      const label = document.createElement('span');
      label.className = 'nv-dash-lane-label';
      label.textContent = def.label;

      const status = document.createElement('span');
      status.className = 'nv-dash-lane-status';
      status.textContent = def.isSub ? '' : 'idle';

      lane.appendChild(glyph);
      lane.appendChild(label);
      lane.appendChild(status);
      this.mountEl.appendChild(lane);

      this.lanes[def.id] = { lane, label, status };
    }
    this._refreshLabels();
  }

  _refreshLabels() {
    const active = this.state.serverState?.active;
    if (!active) return;
    const brain = this.state.getBrain(active.brain);
    const voice = this.state.getVoice(active.voice);
    if (this.lanes.llm && brain) {
      this.lanes.llm.label.textContent = `llm · ${brain.model || brain.id}`;
    }
    if (this.lanes.tts && voice) {
      this.lanes.tts.label.textContent = `tts · kokoro / ${voice.id}`;
    }
  }

  _set(laneId, stateClass, statusText) {
    const lane = this.lanes[laneId];
    if (!lane) return;
    for (const cls of Object.values(STATE_CLASSES)) lane.lane.classList.remove(cls);
    lane.lane.classList.add(STATE_CLASSES[stateClass] || STATE_CLASSES.idle);
    if (statusText !== undefined) lane.status.textContent = statusText;
    lane.lane.style.display = '';
  }

  _resetTurn() {
    for (const id of Object.keys(this.lanes)) {
      this._set(id, 'idle', '');
    }
    if (this.lanes.mic) this.lanes.mic.status.textContent = 'idle';
    if (this.lanes.stt) this.lanes.stt.status.textContent = 'idle';
    if (this.lanes.llm) this.lanes.llm.status.textContent = 'idle';
    if (this.lanes.tts) this.lanes.tts.status.textContent = 'idle';
    if (this.lanes.avatar) this.lanes.avatar.status.textContent = 'idle';
    if (this.lanes.tool) this.lanes.tool.lane.style.display = 'none';
    if (this.lanes.transcript) this.lanes.transcript.status.textContent = '';
  }

  _handle({ type, payload }) {
    switch (type) {
      case 'vad.started':
        this._resetTurn();
        this._set('mic', 'active', 'listening...');
        break;
      case 'vad.stopped':
        this._set('mic', 'done', '');
        this._set('stt', 'active', 'transcribing...');
        break;
      case 'stt.transcript':
        this._set('stt', 'done', `${(payload.duration_ms || 0).toFixed(0)}ms`);
        if (this.lanes.transcript) {
          this.lanes.transcript.status.textContent = `"${payload.text || ''}"`;
        }
        this._set('llm', 'active', 'thinking...');
        break;
      case 'llm.first_token':
        this._set('llm', 'active', `round ${payload.round || 1}`);
        break;
      case 'tool_call_start': {
        const lane = this.lanes.tool;
        if (lane) {
          lane.label.textContent = `🔧 ${payload.name || 'tool'}`;
          const argPreview = payload.arguments
            ? Object.values(payload.arguments)[0]
            : '';
          lane.status.textContent = argPreview
            ? `"${String(argPreview).slice(0, 40)}"`
            : '';
        }
        this._set('tool', 'tool');
        break;
      }
      case 'tool_call_end': {
        const dur = payload.duration_ms != null
          ? `${payload.duration_ms.toFixed(0)}ms ✓`
          : '✓';
        if (this.lanes.tool) {
          this.lanes.tool.status.textContent = dur;
        }
        break;
      }
      case 'tts.playing':
        this._set('tts', 'done', '');
        this._set('avatar', 'active', 'speaking...');
        break;
      case 'avatar.idle':
        this._set('avatar', 'done', '');
        break;
      case 'error':
        for (const id of ['avatar', 'tts', 'llm', 'stt']) {
          if (this.lanes[id].lane.classList.contains(STATE_CLASSES.active)) {
            this._set(id, 'error', payload.message || 'error');
            break;
          }
        }
        break;
      // stage_timing, thinking_token, done are in the event log only — they fire
      // too often or are too granular for spatial visualization without jitter.
    }
  }
}
```

- [ ] **Step 2: Add FlowDiagram styles to `dashboard.css`**

Append:

```css
.nv-dash-flow-header {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: #475569;
  margin-bottom: 6px;
}
.nv-dash-lane {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  margin-bottom: 3px;
  border-radius: 0 3px 3px 0;
  border-left: 3px solid #475569;
  background: #1e293b;
  font-size: 12px;
  transition: background 200ms, border-color 200ms;
}
.nv-dash-lane-glyph {
  flex: 0 0 18px;
  text-align: center;
  font-size: 11px;
  opacity: 0.7;
}
.nv-dash-lane-label {
  flex: 1 1 auto;
}
.nv-dash-lane-status {
  flex: 0 0 auto;
  font-size: 11px;
  opacity: 0.85;
}
.nv-dash-lane-sub {
  background: transparent;
  border-left-color: #1e293b;
  font-style: italic;
  font-size: 11px;
  opacity: 0.85;
  padding-top: 2px;
  padding-bottom: 2px;
}
.nv-dash-lane-branch {
  margin-left: 16px;
}

/* State color variants */
.nv-dash-lane-idle   { border-left-color: #475569; }
.nv-dash-lane-active { border-left-color: #3b82f6; background: #1e2b48; }
.nv-dash-lane-done   { border-left-color: #10b981; background: #1e3a2e; }
.nv-dash-lane-tool   { border-left-color: #c084fc; background: #2d1b3d; }
.nv-dash-lane-error  { border-left-color: #ef4444; background: #3d1818; }
```

- [ ] **Step 3: Mount FlowDiagram from Dashboard.js**

Add the import:

```javascript
import { FlowDiagram } from './components/FlowDiagram.js';
```

Add a constructor field:

```javascript
    this.flowEl = document.getElementById('nv-dash-flow');
```

Inside `_mountControls()`, between ControlsPanel and EventLog, ADD:

```javascript
    this.flowDiagram = new FlowDiagram(this.flowEl, this.state);
```

Final order in `_mountControls()`: ControlsPanel, FlowDiagram, EventLog.

- [ ] **Step 4: Smoke test**

Reload `http://localhost:5173/`. Open the drawer.

1. The Flow section above the EventLog shows 7 lanes (mic, stt, transcript, llm, tool [hidden], tts, avatar), all gray with "idle" status
2. The LLM lane shows the active brain (e.g., "llm · qwen3:4b")
3. The TTS lane shows the active voice (e.g., "tts · kokoro / bella")
4. Talk into mic, ask "What ports does NodeAva use?"
5. Watch the lanes light up in sequence:
   - mic → blue "listening..."
   - mic → green; stt → blue "transcribing..."
   - stt → green "480ms"; transcript shows the text; llm → blue "thinking..."
   - tool branch appears (purple): "🔧 wiki.search ..."
   - tool branch → "263ms ✓"
   - tts → green; avatar → blue "speaking..."
   - avatar → green; (lanes settle)

Try a non-tool question (e.g., "hello") — no tool branch should appear.

Try changing the brain (swap to smollm2-360m) and verify the LLM lane label updates to "llm · smollm2:360m".

- [ ] **Step 5: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/dashboard/
git commit -m "feat(frontend): FlowDiagram with spatial pipeline lanes"
```

---

## Task 9: Migrate tool toggles out of legacy ControlPanel

**Files:**
- Modify: `frontend/src/ui/components/ControlPanel.js`
- Modify: `frontend/src/ui/UIManager.js` (if it wires the toggles)

Plan #5 originally put the wiki/web_search toggles in the bottom-of-page ControlPanel. Plan #8's dashboard has them now. This task removes the duplicate UI.

- [ ] **Step 1: Read the existing ControlPanel.js**

```bash
grep -n "toggle\|wiki\|web_search\|_buildToggle\|onWikiChange\|onWebSearchChange" frontend/src/ui/components/ControlPanel.js
```

You should see code that builds two toggle checkboxes (the Plan #5 toggles).

- [ ] **Step 2: Remove the toggles**

Delete:
1. The `_buildToggle` calls for `webSearchCheckbox` and `wikiCheckbox`
2. The `toggleRow` div creation and its `appendChild`s of those checkboxes
3. The `onWebSearchChange` and `onWikiChange` callbacks definition (if they're class properties)
4. The `_buildToggle` method itself, IF it's not used elsewhere in this file

Keep the mic button + text input + voice selector if those existed.

After the changes, verify:

```bash
grep -n "toggle\|wiki\|web_search" frontend/src/ui/components/ControlPanel.js
```

Expected: zero references to wiki/web_search outside of comments.

- [ ] **Step 3: Remove the now-orphan wirings in UIManager.js**

```bash
grep -n "onWebSearchChange\|onWikiChange\|setWebSearch\|setWiki" frontend/src/ui/UIManager.js
```

If UIManager wires the legacy ControlPanel callbacks (`controlPanel.onWebSearchChange = ...` etc.), delete those wirings. Don't delete `orchestrator.setWebSearch / setWiki` methods themselves — those might still be called for backwards compat; just don't wire them from the legacy ControlPanel.

If there's a "load initial toggles from localStorage" block (Plan #5 era), delete it — server state is canonical now.

- [ ] **Step 4: Smoke test**

Reload `http://localhost:5173/`. Verify:

1. The bottom-of-page ControlPanel no longer shows Wiki/Web checkboxes
2. Open the drawer — Wiki/Web checkboxes are in the dashboard's Controls panel
3. Toggling them in the drawer still POSTs /v1/swap
4. Talking to the avatar still works
5. No console errors

- [ ] **Step 5: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add frontend/src/
git commit -m "feat(frontend): remove legacy ControlPanel tool toggles (moved to dashboard)"
```

---

## Task 10: End-to-end smoke checklist

**Files:** none modified — manual verification.

Final pass. Walk through the user flows and confirm the dashboard works the way the spec described.

- [ ] **Step 1: Ensure the stack is up**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
docker compose ps 2>&1 | head -8
```

Expected: orchestrator, tts, stt, searxng all healthy. No `llm` container (Ollama is on the host).

```bash
curl -fsS http://localhost:11434/api/tags >/dev/null && echo "Ollama: OK" || echo "Ollama: DOWN"
curl -fsS http://localhost:8082/v1/state | python3 -c 'import json,sys;d=json.load(sys.stdin);print("State:", d["active"]["brain"], "ollama_reachable:", d["system"]["ollama"]["reachable"])'
```

Expected: Ollama OK + state JSON with `ollama_reachable: True`.

Start the dev server if not running:

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec/frontend
npm run dev -- --port 5173 --host &
```

Then `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/` should return 200.

- [ ] **Step 2: Walk through the smoke checklist (manual, in browser)**

Open `http://localhost:5173/` and verify each:

1. Avatar canvas renders, no console errors
2. Floating toggle button visible top-right
3. Drawer is closed on first load
4. Click toggle → drawer slides in from right
5. Drawer shows 4 selectors (Brain/Voice/Avatar/Personality) + 2 toggles (Web search/Wiki)
6. Brain selector shows residency chip (probably `unloaded` until Ollama loads qwen3:4b on first request)
7. Press `]` → drawer toggles
8. Change Brain to smollm2-360m → POST /v1/swap fires (Network tab) → selector updates
9. Talk into mic, ask "hello" → flow lanes light up (vad/mic → stt → llm → tts → avatar) → event log appends each event with color coding
10. Change Brain back to qwen3-4b, ask "What ports does NodeAva use?" → tool branch appears (purple) showing wiki.search → response includes specific NodeAva facts → after the round, residency chip should show "gpu" (qwen3:4b now loaded)
11. Toggle Wiki off, repeat the same question → no tool branch; response is generic ("I don't have specific information…")
12. Toggle Wiki on, change Personality to "Improv Comic" → ask same question → wiki tool fires AND the response style differs from default
13. Refresh page → drawer state defaults to closed; selectors restore to last server-side values

If any step fails, note which and the symptom.

- [ ] **Step 3: Report and commit any fixes**

If you fixed bugs found during the smoke test, commit them with a clear message. If no fixes were needed, no commit for this task.

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git log --oneline | head -12
```

Expected: Plan #8's 9 feature/fix commits visible.

- [ ] **Step 4: Final report**

Tell the controller:
- Smoke checklist: all 13 steps passed (or list which failed + what was observed)
- Plan #8 commit count
- Any concerns

---

## Self-Review (already run; documenting for clarity)

**Spec coverage:**
- Goal 1 (drawer surfacing swap controls): Tasks 1 + 4
- Goal 2 (spatial flow diagram): Task 8
- Goal 3 (live event log): Task 7
- Goal 4 (residency chips): Tasks 3 + 4 (ControlsPanel._updateChip)
- Goal 5 (vanilla JS): all tasks
- Goal 6 (events from Orchestrator.js): Task 6
- Drawer behavior (closed default, `]` shortcut, 380px width, mobile full-screen): Tasks 1 + 2 + dashboard.css
- Avatar swap mid-speech (interrupts via loadAvatar): Task 4 calls AvatarManager.loadAvatar() directly
- Migration of legacy tool toggles: Task 9

**Type consistency:**
- `DashboardState` API (`emit`, `setServerState`, `getBrain`/`getVoice`/`getAvatar`/`getPersonality`) used consistently across Tasks 2, 4, 6, 7, 8
- `api.swap(kind, id, value?)` signature consistent in Tasks 2, 4
- Event types in Task 6 (emit) match those handled in Task 7 (EventLog) and Task 8 (FlowDiagram)
- CSS class prefix `.nv-dash-` consistent across Tasks 1, 3, 4, 7, 8

**Security:**
- All DOM building uses `createElement` + `textContent` / `append`. `innerHTML` is not used.
- `replaceChildren()` clears containers safely (no parsed HTML).
- Server-returned strings (catalog labels, transcripts, tool args) are treated as untrusted text.

**No placeholders:** every step has actual code, commands, and expected output.

---

## What comes next

Plan #9 wraps the installer (preflight + `bash scripts/install.sh` + bundle handling). Plan #10 polishes everything — benchmark panel, walkthrough overlay, dry-run feedback, any spec gaps surfaced during workshop trials.
