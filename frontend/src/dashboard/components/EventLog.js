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
