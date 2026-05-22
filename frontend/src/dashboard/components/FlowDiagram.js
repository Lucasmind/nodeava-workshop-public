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

// Pipeline stage_timing event names → FlowDiagram lane ids.
// Backend stages: first_token (TTFT) and final (total LLM e2e) both map to
// the llm lane — last value wins, which is what we want.
// Frontend stages: stt, tts, avatar_speak are emitted client-side.
// round_start / round_end are for the EventLog only — not mapped here.
const STAGE_TO_LANE = {
  // Backend (orchestrator SSE)
  first_token: 'llm',
  final: 'llm',
  // Frontend (client-side timing emissions)
  stt: 'stt',
  tts: 'tts',
  avatar_speak: 'avatar',
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

      const chip = document.createElement('span');
      chip.className = 'nv-dash-lane-chip';

      lane.appendChild(glyph);
      lane.appendChild(label);
      lane.appendChild(status);
      lane.appendChild(chip);
      this.mountEl.appendChild(lane);

      this.lanes[def.id] = { lane, label, status, chip };
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
        for (const id in this.lanes) {
          this.lanes[id].chip.textContent = '';
        }
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
      case 'stage_timing': {
        const laneId = STAGE_TO_LANE[payload.stage];
        if (!laneId) break;
        const lane = this.lanes[laneId];
        if (!lane) break;
        const seconds = (payload.duration_ms / 1000).toFixed(2);
        lane.chip.textContent = `${seconds}s`;
        break;
      }
      // thinking_token, done are in the event log only — too granular
      // for the spatial visualization without visual jitter.
    }
  }
}
