import { ControlPanel } from './components/ControlPanel.js';
import { SubtitleOverlay } from './components/SubtitleOverlay.js';
import { StatusBar } from './components/StatusBar.js';
import { States } from '../app/state.js';
import { log, warn } from '../utils/logger.js';

export class UIManager {
  constructor(orchestrator) {
    this.orchestrator = orchestrator;
    this.controlPanel = null;
    this.subtitles = null;
    this.statusBar = null;
    this.errorTimeout = null;
  }

  init() {
    this.subtitles = new SubtitleOverlay(document.getElementById('subtitle-overlay'));
    this.statusBar = new StatusBar(document.getElementById('status-bar'));
    this.controlPanel = new ControlPanel(document.getElementById('control-panel'));

    this._wireOrchestratorEvents();
    this._wireControlEvents();

    this.statusBar.setState(States.IDLE);

    // Plan #10 — periodic real health probes for STT/LLM/TTS, replacing the
    // hardcoded `setService('tts', 'connected')` lie. Probes run every 5s
    // and update the dots based on actual fetch results.
    this._probeServices();
    this._healthTimer = setInterval(() => this._probeServices(), 5000);

    log('UIManager initialized');
  }

  async _probeServices() {
    const probe = async (path) => {
      try {
        const r = await fetch(path, { method: 'GET', signal: AbortSignal.timeout(2500) });
        return r.ok;
      } catch (_) {
        return false;
      }
    };
    const [stt, tts, orch] = await Promise.all([
      probe('/api/stt/'),
      probe('/api/tts/health'),
      probe('/api/orch/v1/state'),
    ]);
    let llmOk = false;
    if (orch) {
      try {
        const r = await fetch('/api/orch/v1/state', { signal: AbortSignal.timeout(2500) });
        const j = await r.json();
        llmOk = !!j?.system?.ollama?.reachable;
      } catch (_) {}
    }
    this.statusBar.setService('stt', stt ? 'connected' : 'error');
    this.statusBar.setService('tts', tts ? 'connected' : 'error');
    this.statusBar.setService('llm', llmOk ? 'connected' : 'error');
  }

  _wireOrchestratorEvents() {
    const orch = this.orchestrator;

    orch.onStateChange = (newState) => {
      this.statusBar.setState(newState);

      if (newState === States.SPEAKING) {
        this.subtitles.startAssistant();
      }
      if (newState === States.IDLE) {
        this.subtitles.finalizeCurrent();
      }
      if (newState === States.LISTENING) {
        this.controlPanel.setMicState(true);
      }
    };

    orch.onUserSpeech = (text) => {
      this.subtitles.showUser(text);
    };

    orch.onAssistantSentence = (text) => {
      this.subtitles.appendSentence(text);
    };

    orch.onAssistantDone = (text) => {
      this.subtitles.replaceAssistant(text);
      this.subtitles.scheduleCleanup();
    };

    orch.onError = (msg) => {
      this.showError(msg);
    };
  }

  _wireControlEvents() {
    this.controlPanel.onSpeak = (text) => {
      this.orchestrator.handleUserInput(text);
    };

    this.controlPanel.onMicToggle = (active) => {
      if (active) {
        this.orchestrator.startListening();
      } else {
        this.orchestrator.stopListening();
      }
    };

    this.controlPanel.onVoiceChange = (voice) => {
      this.orchestrator.setVoice(voice);
    };
  }

  showError(message) {
    warn('UI Error:', message);
    // Show error in status bar area
    const errorEl = document.createElement('div');
    errorEl.className = 'status-indicator';
    errorEl.style.background = 'rgba(244, 67, 54, 0.3)';
    errorEl.textContent = message;
    const statusBar = document.getElementById('status-bar');
    statusBar.appendChild(errorEl);

    if (this.errorTimeout) clearTimeout(this.errorTimeout);
    this.errorTimeout = setTimeout(() => {
      errorEl.remove();
    }, 5000);
  }
}
