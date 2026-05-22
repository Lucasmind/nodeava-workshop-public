import { States } from '../../app/state.js';

export class StatusBar {
  constructor(containerEl) {
    this.container = containerEl;
    this.indicators = {};
    this.build();
  }

  build() {
    this.indicators.state = this.createIndicator('State', 'idle');
    this.indicators.stt = this.createIndicator('STT', 'unknown');
    this.indicators.llm = this.createIndicator('LLM', 'unknown');
    this.indicators.tts = this.createIndicator('TTS', 'unknown');
  }

  createIndicator(label, status) {
    const el = document.createElement('div');
    el.className = 'status-indicator';

    const dot = document.createElement('span');
    dot.className = 'status-dot';

    const text = document.createElement('span');
    text.textContent = label;

    el.appendChild(dot);
    el.appendChild(text);
    this.container.appendChild(el);

    return { el, dot, text };
  }

  setService(name, status) {
    const ind = this.indicators[name];
    if (!ind) return;
    ind.dot.className = 'status-dot';
    if (status === 'connected' || status === 'ready') {
      ind.dot.classList.add('connected');
    } else if (status === 'error') {
      ind.dot.classList.add('error');
    } else if (status === 'loading') {
      ind.dot.classList.add('loading');
    }
  }

  setState(state) {
    const labels = {
      [States.IDLE]: 'Idle',
      [States.LISTENING]: 'Listening...',
      [States.TRANSCRIBING]: 'Transcribing...',
      [States.THINKING]: 'Thinking...',
      [States.SPEAKING]: 'Speaking...',
      [States.TOOL_CALLING]: 'Tool calling...',
      [States.WIKI_QUERY]: 'Wiki query...',
    };
    this.indicators.state.text.textContent = labels[state] || state;
  }
}
