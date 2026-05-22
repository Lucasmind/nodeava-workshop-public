# Frontend State Machine + Filler Speech Implementation Plan (Plan #5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the frontend to consume the new SSE event types Plan #4 introduced (`tool_call_start`, `tool_call_end`, `stage_timing`, `thinking_token`), refactor the state machine to acknowledge tool execution (`TOOL_CALLING`, `WIKI_QUERY`), play short filler speech ("Let me look that up...") so the avatar doesn't sit silent during tool rounds, and add minimal UI toggles so attendees can opt into web search / wiki tools without a command center (full command center is Plan #8).

**Architecture:** A proper SSE-frame parser replaces `LLMClient.js`'s current line-by-line `data:` scanner — it reads frame-by-frame (`\n\n`-delimited), distinguishes `event:` lines from `data:` lines per frame, and dispatches to typed callbacks (`onToolCallStart`, `onToolCallEnd`, etc.) for named events while keeping the existing OpenAI-chunk path for default-stream content. The state machine gains two states; the orchestrator transitions to `TOOL_CALLING` (or `WIKI_QUERY` for `wiki.*` tools) on `onToolCallStart` and back to `THINKING` on `onToolCallEnd`. An 800ms timer arms on the first tool call of a turn — if it expires before the round ends, the orchestrator queues a single filler-speech phrase. The toggle UI is two checkboxes in the existing `ControlPanel`, persisted to `localStorage`.

**Tech Stack:**
- No new dependencies — existing Vite + vanilla JS frontend
- No test infrastructure (NodeAva has no frontend test suite). Verification is **manual browser-based** per task.
- Cross-references: the Plan #4 SSE event types are documented in `services/orchestrator/README.md` Streaming SSE event types section

**Working directory:** `/media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec`. All paths repo-relative.

**Branch:** `worktree-workshop-mvp-spec` tracking `workshop/main` (private repo).

**Pre-requisite for manual verification:** the full stack must be runnable (llm + searxng + orchestrator + frontend). Use the `docker-compose.test.yml` override created during prior tests:

```bash
# Stand up before starting verification on each task:
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml up -d
# Frontend on http://localhost:3005 (or :3000 if your Plan #1 dozzle conflict was resolved)
```

After all 6 tasks land, run the **Final acceptance checklist** at the bottom.

---

## Task 1: State machine — add `TOOL_CALLING` and `WIKI_QUERY`

**Files:**
- Modify: `frontend/src/app/state.js`

The existing state machine is a 5-state enum (`IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SPEAKING`). Plan #4's spec calls for two new states with these transitions:

```
THINKING ↔ TOOL_CALLING ↔ WIKI_QUERY
```

`WIKI_QUERY` is a distinct state (not a sub-state of `TOOL_CALLING`) so the StatusBar / future visualizer panel can render a different affordance. Picking which one to enter is the Orchestrator's job (Task 4): tool name starting with `wiki.` → `WIKI_QUERY`, else `TOOL_CALLING`.

- [ ] **Step 1: Read the current state.js** to confirm baseline:

```bash
cat frontend/src/app/state.js
```

You should see exactly the 5-state enum plus a `StateMachine` class with `transition`, `is`, `current`.

- [ ] **Step 2: Replace `frontend/src/app/state.js` entirely with:**

```javascript
import { log } from '../utils/logger.js';

export const States = {
  IDLE: 'idle',
  LISTENING: 'listening',
  TRANSCRIBING: 'transcribing',
  THINKING: 'thinking',
  TOOL_CALLING: 'tool_calling',   // Plan #5: tool execution in progress
  WIKI_QUERY: 'wiki_query',       // Plan #5: wiki tool specifically (distinct UI affordance)
  SPEAKING: 'speaking',
};

export class StateMachine {
  constructor() {
    this.state = States.IDLE;
    this.onChange = null; // callback(newState, oldState)
  }

  transition(newState) {
    if (newState === this.state) return;
    const old = this.state;
    this.state = newState;
    log(`State: ${old} → ${newState}`);
    if (this.onChange) this.onChange(newState, old);
  }

  is(state) {
    return this.state === state;
  }

  /** True for any state where an agentic tool round is active. */
  isToolingActive() {
    return this.state === States.TOOL_CALLING || this.state === States.WIKI_QUERY;
  }

  get current() {
    return this.state;
  }
}
```

- [ ] **Step 3: Manual verification (no behavior change yet — just import sanity)**

```bash
cd frontend
npm install  # confirms no dependency drift
npm run build  # confirms state.js still parses + builds
```

Expected: build succeeds with no errors. The new states are unused for now — they'll be wired in Task 4.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/src/app/state.js
git commit -m "feat(frontend): add TOOL_CALLING + WIKI_QUERY states to state machine"
```

---

## Task 2: `LLMClient.js` — SSE event consumer rewrite

**Files:**
- Modify: `frontend/src/llm/LLMClient.js`

The current `LLMClient.js` is a simple line-by-line `data:` scanner. It only consumes default-stream OpenAI chunks. Plan #4 added five named SSE event types (`thinking_token`, `tool_call_start`, `tool_call_end`, `stage_timing`, `error`) that arrive as multi-line frames:

```
event: tool_call_start
data: {"type":"tool_call_start","id":"call_1","name":"browser.search","arguments":{"query":"..."}}

data: {"choices":[...]}    <- default stream (OpenAI chunk)

event: tool_call_end
data: {"type":"tool_call_end","id":"call_1","result_preview":"...","duration_ms":1100.0}
```

We need a proper SSE frame parser that:
- Splits on blank lines (`\n\n`) to get frames
- For each frame, reads `event:` and `data:` lines (a frame can have at most one `event:` line; `data:` lines concatenate)
- If `event:` line missing → it's a default-stream frame → parse OpenAI chunk JSON → call `onToken` (existing behavior)
- If `event:` line present → call the typed handler matching the event name

Also: extend the request-options surface to include `webSearch` and `wiki` body fields and the new typed callbacks.

- [ ] **Step 1: Replace `frontend/src/llm/LLMClient.js` entirely with:**

```javascript
import { config } from '../app/config.js';
import { log, error } from '../utils/logger.js';

/**
 * LLMClient — streaming chat-completions client for the nodeava-orch.
 *
 * Plan #5 rewrite: parses Plan #4's dual-flavor SSE stream. The default
 * `data:`-only frames carry OpenAI chunks (token content). Named-event
 * frames (`event: tool_call_start` etc.) carry typed payloads consumed
 * by the agentic-loop UI (state machine, future Tier A panels).
 *
 * Frame format (RFC 8895-ish):
 *
 *   <event-line>\n
 *   <data-line(s)>\n
 *   \n          <- blank-line frame separator
 *
 * Where:
 *   <event-line>  ::= "event: <name>"   (optional; absence means default stream)
 *   <data-line>   ::= "data: <text>"    (one or more; concatenate values with "\n")
 */
export class LLMClient {
  constructor() {
    this.abortController = null;
  }

  /**
   * Send a streaming chat completion request.
   *
   * @param {Array} messages - OpenAI-format messages [{role, content}]
   * @param {Object} handlers
   * @param {function(string)} handlers.onToken - per content token (existing behavior)
   * @param {function(string)} handlers.onDone - called once with the full assembled text
   * @param {function(Error)} handlers.onError - network or terminal SSE error
   * @param {function({id, name, arguments})} [handlers.onToolCallStart]
   * @param {function({id, result_preview, duration_ms, error})} [handlers.onToolCallEnd]
   * @param {function({stage, duration_ms, round_num})} [handlers.onStageTiming]
   * @param {function(string)} [handlers.onThinkingToken] - per thinking delta
   * @param {Object} [opts]
   * @param {boolean} [opts.webSearch] - inject browser.* tools in agentic loop
   * @param {boolean} [opts.wiki] - inject wiki.* tools in agentic loop
   */
  async chatCompletion(messages, handlers, opts = {}) {
    this.abort();
    this.abortController = new AbortController();

    const {
      onToken,
      onDone,
      onError,
      onToolCallStart,
      onToolCallEnd,
      onStageTiming,
      onThinkingToken,
    } = handlers || {};

    const body = {
      model: config.llmModel,
      messages,
      max_tokens: config.llmMaxTokens,
      stream: true,
    };
    if (opts.webSearch) body.web_search = true;
    if (opts.wiki) body.wiki = true;

    try {
      const response = await fetch(config.llmEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: this.abortController.signal,
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const err = new Error(`LLM HTTP ${response.status}: ${response.statusText}`);
        err.status = response.status;
        throw err;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Drain complete frames (separated by blank line "\n\n")
        let sepIdx;
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);
          const delta = this._handleFrame(frame, {
            onToken,
            onToolCallStart,
            onToolCallEnd,
            onStageTiming,
            onThinkingToken,
            onError,
          });
          if (delta) fullText += delta;
        }
      }

      // Drain any final partial buffer (unlikely but defensive)
      if (buffer.trim()) {
        const delta = this._handleFrame(buffer, {
          onToken,
          onToolCallStart,
          onToolCallEnd,
          onStageTiming,
          onThinkingToken,
          onError,
        });
        if (delta) fullText += delta;
      }

      log(`LLM response: ${fullText.length} chars`);
      if (onDone) onDone(fullText);
    } catch (err) {
      if (err.name === 'AbortError') {
        log('LLM request aborted');
        return;
      }
      const classified = this._classifyError(err);
      error('LLM error:', classified.message);
      if (onError) onError(classified);
    } finally {
      this.abortController = null;
    }
  }

  /**
   * Parse a single SSE frame and dispatch to the right handler.
   * Returns the content delta if this was a default-stream token frame
   * (so chatCompletion can accumulate fullText). Otherwise returns null.
   */
  _handleFrame(frame, handlers) {
    let eventType = null;
    const dataLines = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataLines.push(line.slice(6));
      }
    }
    if (dataLines.length === 0) return null;
    const dataStr = dataLines.join('\n');
    if (dataStr === '[DONE]') return null;

    // Default stream (no event:) → OpenAI chunk shape
    if (eventType === null) {
      try {
        const parsed = JSON.parse(dataStr);
        const delta = parsed.choices?.[0]?.delta?.content;
        if (delta && handlers.onToken) handlers.onToken(delta);
        return delta || null;
      } catch {
        // Malformed JSON on the default stream — skip
        return null;
      }
    }

    // Named event → typed payload, dispatch by event type
    let payload;
    try {
      payload = JSON.parse(dataStr);
    } catch {
      // Malformed payload — skip
      return null;
    }

    switch (eventType) {
      case 'thinking_token':
        if (handlers.onThinkingToken) handlers.onThinkingToken(payload.delta || '');
        break;
      case 'tool_call_start':
        if (handlers.onToolCallStart) {
          handlers.onToolCallStart({
            id: payload.id,
            name: payload.name,
            arguments: payload.arguments || {},
          });
        }
        break;
      case 'tool_call_end':
        if (handlers.onToolCallEnd) {
          handlers.onToolCallEnd({
            id: payload.id,
            result_preview: payload.result_preview || '',
            duration_ms: payload.duration_ms || 0,
            error: payload.error || null,
          });
        }
        break;
      case 'stage_timing':
        if (handlers.onStageTiming) {
          handlers.onStageTiming({
            stage: payload.stage,
            duration_ms: payload.duration_ms || 0,
            round_num: payload.round_num || null,
          });
        }
        break;
      case 'error':
        // SSE-channel error (not a network error). Surface it via onError.
        if (handlers.onError) {
          handlers.onError(new Error(payload.message || 'orchestrator error'));
        }
        break;
      default:
        // Unknown event type — log but don't fail
        log(`LLMClient: ignoring unknown SSE event '${eventType}'`);
    }
    return null;
  }

  _classifyError(err) {
    if (err.status === 503) {
      return new Error('LLM service is busy — try again shortly');
    }
    if (err.status === 404) {
      return new Error('LLM model not found — check model configuration');
    }
    if (err.status >= 500) {
      return new Error(`LLM server error (${err.status}) — check service logs`);
    }
    if (err.status >= 400) {
      return new Error(`LLM request error (${err.status}) — ${err.message}`);
    }
    if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError')) {
      return new Error('Cannot reach LLM service — check if container is running');
    }
    return err;
  }

  abort() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }
}
```

- [ ] **Step 2: Critical — Orchestrator.js currently calls `chatCompletion(messages, onToken, onDone, onError)` positionally.** That call will BREAK with the new object-bag signature. Search for the call site:

```bash
grep -n "this.llm.chatCompletion" frontend/src/pipeline/Orchestrator.js
```

You should find one line around line 174 with positional args. **Do NOT change it yet** — Task 4 will rewrite the orchestrator's call site to use the new object-bag signature. Until then, the build will break.

- [ ] **Step 3: Verify the build catches the breakage**

```bash
cd frontend && npm run build
```

The build itself should succeed (JS is dynamically typed; runtime would fail not build). To confirm the rewrite parsed correctly:

```bash
node -e "import('./frontend/src/llm/LLMClient.js').then(() => console.log('parsed OK')).catch(e => console.error(e.message))" 2>&1
```

Expected: `parsed OK` OR an import resolution error for `'../app/config.js'` (browser-import path). If the latter, ignore — the file is structurally fine.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/src/llm/LLMClient.js
git commit -m "feat(frontend): LLMClient consumes Plan #4 named SSE event types"
```

**Note:** the stack is half-broken between Task 2 and Task 4 (call site mismatch). Land Tasks 3 and 4 in the same session if possible. Don't open this branch as a PR until Task 4 lands.

---

## Task 3: `TTSManager.synthesizeFiller()` — short queued filler audio

**Files:**
- Modify: `frontend/src/tts/TTSManager.js`

Filler speech is a short phrase queued at the front of the TTS queue when a tool round begins. We don't want it to disrupt mid-sentence playback of a previous response — it just plays at the next opportunity. The simplest implementation: prepend to the queue if anything is queued, otherwise just enqueue normally.

- [ ] **Step 1: Read the current TTSManager.js to confirm the queue model**

```bash
grep -n "_queue\|_processNext\|synthesize" frontend/src/tts/TTSManager.js | head -20
```

Confirm `_queue` is a simple Array of strings and `synthesize(text)` calls `this._queue.push(text); this._processNext();`.

- [ ] **Step 2: Add `synthesizeFiller(text)` method to TTSManager**

Open `frontend/src/tts/TTSManager.js`, find the `synthesize(text)` method, and add the following method directly AFTER it:

```javascript
  /**
   * Plan #5: short filler audio ("let me look that up…") queued when an
   * agentic tool round runs longer than the filler-grace window.
   *
   * Behavior: prepends to the queue (so it plays sooner than any pending
   * sentences from the *previous* response that might still be in-flight).
   * Skips entirely if the same filler is already queued (avoid spamming
   * when multiple tool calls fire in quick succession).
   */
  synthesizeFiller(text) {
    if (!this.ready) {
      warn('TTS not ready, skipping filler synthesis');
      return;
    }
    if (!text?.trim()) return;
    if (this._queue.includes(text)) {
      log(`TTS filler "${text.substring(0, 30)}" already queued — skipping`);
      return;
    }
    this._queue.unshift(text);
    log(`TTS filler queued (queue length now ${this._queue.length})`);
    this._processNext();
  }
```

- [ ] **Step 3: Manual verification — confirm the file still parses**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/src/tts/TTSManager.js
git commit -m "feat(frontend): TTSManager.synthesizeFiller for tool-round filler audio"
```

---

## Task 4: `Orchestrator.js` — wire new callbacks, state transitions, filler timer

**Files:**
- Modify: `frontend/src/pipeline/Orchestrator.js`

This is the largest task. It does three things together because they're tightly coupled:

1. **Rewrite the LLM call site** to use the new object-bag handlers (fixes the Task-2 breakage).
2. **Add tool-event handlers** that transition state to `TOOL_CALLING` / `WIKI_QUERY` and back to `THINKING`.
3. **Filler-speech timer:** 800ms after the first tool call of a turn, queue one filler phrase. If the round ends sooner, cancel.

The toggles arrive from UIManager via two new public setters: `setWebSearch(bool)` and `setWiki(bool)` (Task 5 wires the UI). The Orchestrator stores them internally and passes them to LLMClient on each chat.

- [ ] **Step 1: Read the current call site in Orchestrator.js**

```bash
sed -n '170,210p' frontend/src/pipeline/Orchestrator.js
```

You'll see roughly:

```javascript
await this.llm.chatCompletion(
  messages,
  (token) => {
    // handle token
  },
  (full) => {
    // onDone
  },
  (err) => {
    // onError
  },
);
```

You're replacing this with the new shape, and adding three new handlers, and arming/disarming a filler timer.

- [ ] **Step 2: Modify Orchestrator.js — three sections**

**Section A:** find the constructor and ADD these lines at the end of the constructor (after `this._speakingTimer = null;`):

```javascript
    // Plan #5: agentic-tool state
    this._webSearchEnabled = false;
    this._wikiEnabled = false;
    this._fillerTimer = null;
    this._fillerPlayedThisTurn = false;
    this._activeToolName = null;

    // Plan #5: optional UI callbacks (UIManager wires these)
    this.onToolCallStart = null;  // ({id, name, arguments})
    this.onToolCallEnd = null;    // ({id, result_preview, duration_ms, error})
    this.onThinkingToken = null;  // (delta:string)
    this.onStageTiming = null;    // ({stage, duration_ms, round_num})
```

**Section B:** add three new public setters anywhere in the class (suggest just after the constructor):

```javascript
  /** Plan #5: toggle for browser.* tool family. Set by UIManager. */
  setWebSearch(enabled) {
    this._webSearchEnabled = !!enabled;
    log(`web_search toggle = ${this._webSearchEnabled}`);
  }

  /** Plan #5: toggle for wiki.* tool family. Set by UIManager. */
  setWiki(enabled) {
    this._wikiEnabled = !!enabled;
    log(`wiki toggle = ${this._wikiEnabled}`);
  }

  /**
   * Plan #5: classify a tool name into the right state.
   * Tool name starting with "wiki." → WIKI_QUERY; otherwise TOOL_CALLING.
   */
  _stateForTool(toolName) {
    return toolName && toolName.startsWith('wiki.')
      ? States.WIKI_QUERY
      : States.TOOL_CALLING;
  }

  /**
   * Plan #5: arm an 800ms filler timer when a tool round starts. If the
   * tool finishes before 800ms, cancel. If 800ms elapses, queue ONE
   * filler phrase and don't fire again for this user turn.
   */
  _armFillerTimer() {
    if (this._fillerPlayedThisTurn || this._fillerTimer !== null) return;
    this._fillerTimer = setTimeout(() => {
      if (this.state.isToolingActive() && !this._fillerPlayedThisTurn) {
        const phrase = this._activeToolName?.startsWith('wiki.')
          ? 'Let me check the wiki.'
          : 'Let me look that up.';
        this.tts.synthesizeFiller(phrase);
        this._fillerPlayedThisTurn = true;
      }
      this._fillerTimer = null;
    }, 800);
  }

  _cancelFillerTimer() {
    if (this._fillerTimer !== null) {
      clearTimeout(this._fillerTimer);
      this._fillerTimer = null;
    }
  }
```

**Section C:** rewrite the LLM call site. Find the existing `this.llm.chatCompletion(` call (around line 174) and replace the entire call expression with the new object-bag form. The full replacement block looks like this (NOTE: the surrounding context — variable scope, retry loop, error handling — must be preserved; only replace the call expression and the lambdas it took as positional args):

Find the call (your line numbers may vary; use grep -n to locate):

```javascript
await this.llm.chatCompletion(
  messages,
  (token) => {
    /* token handler */
  },
  (full) => {
    /* done handler */
  },
  (err) => {
    /* error handler */
  },
);
```

Replace it with:

```javascript
this._fillerPlayedThisTurn = false;  // reset per user turn
this._activeToolName = null;

await this.llm.chatCompletion(
  messages,
  {
    onToken: (token) => {
      // existing token handling (preserve whatever was in the original lambda)
      if (this.onAssistantToken) this.onAssistantToken(token);
      this._handleStreamToken(token);
    },
    onDone: (full) => {
      // existing done handling
      this._cancelFillerTimer();
      this._handleStreamDone(full);
    },
    onError: (err) => {
      this._cancelFillerTimer();
      this._handleStreamError(err);
    },
    onThinkingToken: (delta) => {
      // Surface to UI; don't speak it
      if (this.onThinkingToken) this.onThinkingToken(delta);
    },
    onToolCallStart: ({ id, name, arguments: args }) => {
      log(`Tool call start: ${name}(${JSON.stringify(args).substring(0, 80)})`);
      this._activeToolName = name;
      this.state.transition(this._stateForTool(name));
      this._armFillerTimer();
      if (this.onToolCallStart) this.onToolCallStart({ id, name, arguments: args });
    },
    onToolCallEnd: ({ id, result_preview, duration_ms, error: toolErr }) => {
      log(`Tool call end: ${id} (${duration_ms.toFixed(0)}ms${toolErr ? ', error: ' + toolErr : ''})`);
      this._cancelFillerTimer();
      // Back to THINKING — the loop will either call another tool or produce content
      this.state.transition(States.THINKING);
      this._activeToolName = null;
      if (this.onToolCallEnd) {
        this.onToolCallEnd({ id, result_preview, duration_ms, error: toolErr });
      }
    },
    onStageTiming: (timing) => {
      if (this.onStageTiming) this.onStageTiming(timing);
    },
  },
  {
    webSearch: this._webSearchEnabled,
    wiki: this._wikiEnabled,
  },
);
```

**CRITICAL:** the original Orchestrator's token-handler body is non-trivial (Qwen3 thinking-tag filtering, sentence boundary detection, TTS queuing). Do NOT lose that logic. The pattern to follow:

1. Open the file
2. Find the existing `chatCompletion(` call
3. **Read the entire body of the existing `(token) => { ... }` lambda** — copy it into `_handleStreamToken(token)` as a new private method
4. **Read the entire body of the existing `(full) => { ... }` lambda** — copy it into `_handleStreamDone(full)`
5. **Read the entire body of the existing `(err) => { ... }` lambda** — copy it into `_handleStreamError(err)`
6. THEN replace the chatCompletion call with the new object-bag form referencing those private methods

This way none of the original streaming behavior is lost.

- [ ] **Step 3: Manual verification — build succeeds**

```bash
cd frontend && npm run build
```

Expected: build succeeds. No syntax errors.

- [ ] **Step 4: Manual browser verification — vanilla chat still works**

Open the avatar UI at http://localhost:3005 (assuming the stack is up — see plan header). Send a plain text message via the input box (e.g. "Hello, who are you?"). Without any toggles set, the orchestrator should call LLMClient with `webSearch: false, wiki: false`, which means no body toggles → no agentic loop → vanilla streaming chat as before. The avatar should:

- Transition through `LISTENING` (skip if typed) → `THINKING` → `SPEAKING` → `IDLE`
- Produce the same response shape as Plan #2
- Show no tool-call events in the browser console

If anything is broken, the most likely cause is lost logic from the original `(token) =>` lambda. Re-read it and re-paste into `_handleStreamToken`.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/pipeline/Orchestrator.js
git commit -m "feat(frontend): Orchestrator handles tool events + filler-speech timer"
```

---

## Task 5: `ControlPanel.js` — tool toggles UI

**Files:**
- Modify: `frontend/src/ui/components/ControlPanel.js`
- Modify: `frontend/src/ui/UIManager.js`

Two minimal checkboxes added to the existing ControlPanel: "🔍 Web search" and "📚 Wiki". State persisted to `localStorage` (so attendees don't have to re-toggle on reload). On change, fires a callback the UIManager wires to `Orchestrator.setWebSearch` / `Orchestrator.setWiki`.

- [ ] **Step 1: Modify `frontend/src/ui/components/ControlPanel.js`**

Add two new public callback slots in the constructor — find the existing callback declarations (`this.onSpeak`, `this.onVoiceChange`, `this.onMicToggle`) and add right after them:

```javascript
    this.onWebSearchChange = null;  // Plan #5: callback(bool)
    this.onWikiChange = null;       // Plan #5: callback(bool)
```

In the `build()` method, after the voice selector is appended to the container, append a toggle row. Find the existing `this.container.appendChild(this.voiceSelect);` line and INSERT this AFTER it:

```javascript
    // Plan #5: tool toggles (agentic loop opt-in)
    const toggleRow = document.createElement('div');
    toggleRow.className = 'tool-toggle-row';
    toggleRow.style.cssText = 'display:flex;gap:1em;margin-top:0.5em;font-size:0.9em;';

    this.webSearchCheckbox = this._buildToggle({
      id: 'tool-web-search',
      label: '🔍 Web search',
      storageKey: 'nodeava.toggle.web_search',
      onChange: (v) => {
        if (this.onWebSearchChange) this.onWebSearchChange(v);
      },
    });

    this.wikiCheckbox = this._buildToggle({
      id: 'tool-wiki',
      label: '📚 Wiki',
      storageKey: 'nodeava.toggle.wiki',
      onChange: (v) => {
        if (this.onWikiChange) this.onWikiChange(v);
      },
    });

    toggleRow.appendChild(this.webSearchCheckbox.label);
    toggleRow.appendChild(this.wikiCheckbox.label);
    this.container.appendChild(toggleRow);
```

Then add the `_buildToggle` private method to the class (anywhere — e.g. just before the closing brace):

```javascript
  /**
   * Plan #5: build a single labelled checkbox bound to localStorage.
   * Returns {input, label} — caller appends `label` to the DOM.
   */
  _buildToggle({ id, label, storageKey, onChange }) {
    const initial = localStorage.getItem(storageKey) === '1';

    const labelEl = document.createElement('label');
    labelEl.style.cssText = 'display:flex;align-items:center;gap:0.4em;cursor:pointer;';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = id;
    input.checked = initial;
    input.addEventListener('change', () => {
      localStorage.setItem(storageKey, input.checked ? '1' : '0');
      onChange(input.checked);
    });

    const span = document.createElement('span');
    span.textContent = label;

    labelEl.appendChild(input);
    labelEl.appendChild(span);
    return { input, label: labelEl };
  }

  /** Plan #5: expose initial toggle state so UIManager can prime the orchestrator. */
  getInitialToggles() {
    return {
      webSearch: this.webSearchCheckbox?.input?.checked ?? false,
      wiki: this.wikiCheckbox?.input?.checked ?? false,
    };
  }
```

- [ ] **Step 2: Modify `frontend/src/ui/UIManager.js`**

In `_wireControlEvents` (or wherever the existing `onSpeak / onVoiceChange / onMicToggle` callbacks are wired), add wiring for the new toggles. Find the block that wires the existing callbacks and INSERT this right after them:

```javascript
    // Plan #5: tool toggles → orchestrator setters
    this.controlPanel.onWebSearchChange = (enabled) => {
      this.orchestrator.setWebSearch(enabled);
    };
    this.controlPanel.onWikiChange = (enabled) => {
      this.orchestrator.setWiki(enabled);
    };

    // Prime orchestrator with the initial (persisted) toggle state
    const initialToggles = this.controlPanel.getInitialToggles();
    this.orchestrator.setWebSearch(initialToggles.webSearch);
    this.orchestrator.setWiki(initialToggles.wiki);
```

- [ ] **Step 3: Build the frontend**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Manual browser verification**

1. Hard-refresh `http://localhost:3005` (Cmd/Ctrl-Shift-R) to pick up the new build.
2. You should see two new checkboxes next to the voice selector in the control panel.
3. Check the "🔍 Web search" box. In the browser DevTools console, you should see `web_search toggle = true` from the Orchestrator log.
4. Refresh the page. The checkbox should still be checked (localStorage persistence).
5. Uncheck it. Refresh. It should stay unchecked.

If any of these fail: check that `localStorage` is enabled (it is on localhost), that the `storageKey` literal matches between read + write, and that `_wireControlEvents` actually fires.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/src/ui/components/ControlPanel.js frontend/src/ui/UIManager.js
git commit -m "feat(frontend): ControlPanel tool toggles + UIManager wiring"
```

---

## Task 6: README + manual acceptance checklist

**Files:**
- Modify: `frontend/README.md` (create if missing) OR add a section to the top-level README
- Modify: `CLAUDE.md` (add note about new states + toggles for future Claude sessions)

- [ ] **Step 1: Find or create the frontend README**

```bash
test -f frontend/README.md && echo "exists" || echo "needs creation"
```

If it doesn't exist, create `frontend/README.md` with the content below. If it does exist, APPEND the new section.

The content to write/append:

```markdown
## Tool toggles (Plan #5)

Two checkboxes in the control panel opt into agentic features served by
the orchestrator (Plan #4):

- **🔍 Web search** — when enabled, the orchestrator's chat route runs an
  agentic loop with `browser.*` tools. The avatar may search the web, fetch
  pages, and synthesize an answer. Tool execution surfaces via:
  - State machine: `TOOL_CALLING` (or `WIKI_QUERY` for wiki tools)
  - Filler speech: "Let me look that up." after 800ms of tool execution
  - SSE events (consumed by `LLMClient.js`): `tool_call_start`, `tool_call_end`, `stage_timing`, `thinking_token`

- **📚 Wiki** — same shape, but injects `wiki.*` tools (read-only access to
  the on-disk wiki at `wiki/` in the repo). Useful for asking about NodeAva
  itself once Plan #6 fills in self-knowledge content.

Both toggles persist to `localStorage` (`nodeava.toggle.web_search`,
`nodeava.toggle.wiki`). Plan #8 will replace these with a proper command
center; Plan #5 keeps the UI minimal.

## State machine (Plan #5)

The full state list (frontend/src/app/state.js):

| State | When |
|---|---|
| `IDLE` | nothing happening |
| `LISTENING` | mic active, capturing audio |
| `TRANSCRIBING` | audio → text via STT |
| `THINKING` | LLM is computing |
| `TOOL_CALLING` | agentic loop executing a browser.* tool |
| `WIKI_QUERY` | agentic loop executing a wiki.* tool |
| `SPEAKING` | TTS audio playing through avatar lip-sync |

Transitions:
```
IDLE → LISTENING → TRANSCRIBING → THINKING
THINKING ↔ TOOL_CALLING ↔ WIKI_QUERY    (back-and-forth during a tool round)
THINKING → SPEAKING → IDLE
```
```

- [ ] **Step 2: Append to `CLAUDE.md` at repo root**

Find the existing CLAUDE.md and append a new section at the end:

```markdown
## Plan #5 — frontend tool toggles + state machine

- State machine in `frontend/src/app/state.js` now has 7 states: IDLE, LISTENING, TRANSCRIBING, THINKING, TOOL_CALLING, WIKI_QUERY, SPEAKING.
- `LLMClient.chatCompletion(messages, handlers, opts)` uses an object-bag handlers signature. Handlers: `onToken`, `onDone`, `onError`, `onToolCallStart`, `onToolCallEnd`, `onStageTiming`, `onThinkingToken`. Opts: `webSearch`, `wiki` (booleans → body fields).
- TTSManager has a `synthesizeFiller(text)` helper that prepends to the queue (used for "let me look that up..." when tool rounds run >800ms).
- ControlPanel exposes 2 tool toggles (web search, wiki). Persisted to localStorage keys `nodeava.toggle.web_search` and `nodeava.toggle.wiki`.
- Plan #8 will replace these toggles with a full command center.
```

- [ ] **Step 3: Commit**

```bash
git add frontend/README.md CLAUDE.md
git commit -m "docs(frontend): document Plan #5 state machine + tool toggles"
```

---

## Final acceptance checklist (manual browser verification)

After all 6 tasks land, bring up the full stack and run through this end-to-end:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml up -d
# Wait for all healthy
until \
  [ "$(docker inspect workshop-mvp-spec-llm-1 --format '{{.State.Health.Status}}')" = "healthy" ] && \
  [ "$(docker inspect workshop-mvp-spec-stt-1 --format '{{.State.Health.Status}}')" = "healthy" ] && \
  [ "$(docker inspect workshop-mvp-spec-tts-1 --format '{{.State.Health.Status}}')" = "healthy" ] && \
  [ "$(docker inspect nodeava-orch --format '{{.State.Health.Status}}')" = "healthy" ] && \
  [ "$(docker inspect searxng --format '{{.State.Health.Status}}')" = "healthy" ]; do
  sleep 2
done
echo "all healthy"
```

Then open `http://localhost:3005` (or your configured frontend port) in a browser and run through:

- [ ] **A1. Vanilla chat** (no toggles): Type "Hello, who are you?" + Speak. Avatar responds normally, no tool events in DevTools console, state goes THINKING → SPEAKING → IDLE.
- [ ] **A2. Wiki toggle**: Enable 📚 Wiki. Type "What does the wiki say about itself?" + Speak. Watch the state in StatusBar — it should transition into WIKI_QUERY for ~1-2 seconds, back to THINKING, then SPEAKING. DevTools console shows `Tool call start: wiki.list(...)` and `Tool call end: ... (Nms)`. Avatar speaks an answer that references the wiki stub content.
- [ ] **A3. Web search toggle**: Enable 🔍 Web search (disable wiki for clarity). Ask "What's the latest stable Linux kernel version?" Watch StatusBar → TOOL_CALLING. After 800ms you should hear the avatar say "Let me look that up." (filler), then a proper synthesized answer once SearXNG returns. Console shows `Tool call start: browser.search(...)`.
- [ ] **A4. Filler-grace short-circuit**: Disable filler test by mentally noting — if a tool returns in <800ms (wiki.list on a tiny wiki for instance), the filler should NOT play. Repeat A2 a few times. Most rounds finish in <500ms — you should NOT hear "Let me check the wiki" most of the time. Filler only fires when tool execution genuinely takes >800ms.
- [ ] **A5. Persistence**: Set both toggles. Refresh. Both checkboxes still set. Open another browser tab pointing at the same URL. Toggles match (localStorage is per-origin).
- [ ] **A6. Mic + voice + ControlPanel unchanged**: The existing mic toggle, voice selector, and Speak button work exactly as before — Plan #5 should not regress any Plan #1+#2 functionality.
- [ ] **A7. Both toggles together**: Enable BOTH. Ask "Tell me what the wiki says about TTS, and also search the web for the latest Kokoro release." The agent should pick wiki.* for the first half and browser.* for the second — or do one then the other. Watch the state transitions and verify either order works without breaking.

If all 7 pass, Plan #5 is done. Tear down:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml down
```

---

## What comes next (Plan #6)

Plan #6 fills the on-disk wiki with curated NodeAva self-knowledge. The compile step runs offline with a strong model (Claude Opus or equivalent) and produces a committed artifact. After Plan #6 lands, asking the avatar "What is NodeAva?" with the 📚 Wiki toggle produces an actually-useful answer instead of the current "wiki is a Plan #3 stub" deflection. Plan #6 also adds a drop-to-ingest flow so attendees can dump a PDF into the workshop and the agent extends the wiki live during the workshop.
