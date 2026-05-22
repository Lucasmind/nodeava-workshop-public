import { config } from '../app/config.js';
import { log, error, warn } from '../utils/logger.js';

export class TTSManager {
  constructor({ dashboardState = null } = {}) {
    this.ready = false;
    this.onAudioReady = null; // callback(audioData | null) — null signals a failed sentence
    this._voice = config.ttsDefaultVoice;  // fallback until state loads
    // Promise resolves once the UI-id → kokoro-id mapping has been applied.
    // synthesize() awaits this so the first utterance isn't sent with a UI
    // id that Kokoro 400's on.
    this._voiceReady = this._loadVoiceFromState();
    this._speed = config.ttsDefaultSpeed;
    this._abortController = null;
    this._queue = [];
    this._processing = false;
    this._cancelled = false;
    this._dashboardState = dashboardState;
    this._currentText = null; // text being synthesized, for tts.playing event
  }

  async init() {
    log('Initializing TTS (Kokoro-FastAPI container)...');
    this.ready = true;
    log('TTS ready');
  }

  synthesize(text) {
    if (!this.ready) {
      warn('TTS not ready, skipping synthesis');
      if (this.onAudioReady) this.onAudioReady(null);
      return;
    }
    if (!text?.trim()) {
      if (this.onAudioReady) this.onAudioReady(null);
      return;
    }

    this._queue.push(text);
    this._processNext();
  }

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

  async _processNext() {
    if (this._processing || this._queue.length === 0) return;
    this._processing = true;
    this._cancelled = false;

    // Block the FIRST utterance until _loadVoiceFromState() has translated
    // the orchestrator's UI-side voice id (e.g., "bella") into the kokoro
    // voice id (e.g., "af_bella"). Without this, the first synthesis can
    // race the catalog lookup and send the bare UI id — Kokoro returns
    // HTTP 400 and the dashboard silently produces no audio.
    if (this._voiceReady) {
      try { await this._voiceReady; } catch (_) {}
      this._voiceReady = null; // only block the first call
    }

    const text = this._queue.shift();
    this._currentText = text;
    const t0 = performance.now();
    const charCount = text.length;
    log(`TTS synthesize (${charCount} chars): "${text.substring(0, 60)}..."`);

    this._abortController = new AbortController();

    let result;
    try {
      const res = await fetch(config.ttsEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'kokoro',
          input: text,
          voice: this._voice,
          speed: this._speed,
          response_format: 'pcm',
          stream: false,
          return_timestamps: true,
        }),
        signal: this._abortController.signal,
      });

      if (!res.ok) {
        const err = new Error(`TTS HTTP ${res.status}: ${await res.text()}`);
        err.status = res.status;
        throw err;
      }

      result = await res.json();
    } catch (err) {
      if (err.name === 'AbortError') {
        this._processing = false;
        return;
      }
      const msg = this._classifyError(err);
      error('TTS synthesis error:', msg);
      if (this.onAudioReady) this.onAudioReady(null);
      this._processing = false;
      if (!this._cancelled) this._processNext();
      return;
    }

    const elapsed_ms = Math.round(performance.now() - t0);
    log(`TTS audio ready in ${elapsed_ms}ms (${charCount} chars): "${text.substring(0, 40)}..."`);

    const audioData = this._transformResponse(result);
    this._dashboardState?.emit('stage_timing', { stage: 'tts', duration_ms: elapsed_ms });
    this._dashboardState?.emit('tts.playing', { text, voice: this._voice });
    if (this.onAudioReady) {
      this.onAudioReady(audioData);
    }

    this._processing = false;
    if (!this._cancelled) {
      if (this._queue.length === 0) {
        this._dashboardState?.emit('tts.done', {});
      }
      this._processNext();
    }
  }

  _transformResponse(result) {
    // Decode base64 PCM audio to ArrayBuffer
    const binaryStr = atob(result.audio);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i);
    }
    const audioBuffer = bytes.buffer;

    // Map timestamps to TalkingHead's expected format
    const words = [];
    const wtimes = [];
    const wdurations = [];

    if (result.timestamps) {
      for (const ts of result.timestamps) {
        words.push(ts.word);
        wtimes.push(ts.start_time * 1000);       // seconds → ms
        wdurations.push((ts.end_time - ts.start_time) * 1000);
      }
    }

    return {
      audio: [audioBuffer],  // Array of ArrayBuffer — TalkingHead concatenates + converts PCM
      words,
      wtimes,
      wdurations,
    };
  }

  async _loadVoiceFromState() {
    try {
      const resp = await fetch('/api/orch/v1/state');
      if (!resp.ok) return;
      const body = await resp.json();
      const stateVoice = body?.active?.voice;
      if (!stateVoice) return;
      // Translate "bella" → "af_bella" via catalog
      const catResp = await fetch('/api/orch/v1/catalog');
      if (!catResp.ok) return;
      const cat = await catResp.json();
      const v = (cat.voices || []).find((x) => x.id === stateVoice);
      if (v?.kokoro_voice) this._voice = v.kokoro_voice;
    } catch (_e) {
      // Best-effort. Keep the fallback voice.
    }
  }

  /**
   * Plan #8: re-fetch state and apply the new active voice.
   * Called by the dashboard after a voice swap so the next utterance
   * uses the new voice immediately.
   */
  async refreshVoiceFromState() {
    await this._loadVoiceFromState();
  }

  // Accepts either a kokoro voice id (e.g., "af_bella") or a UI catalog id
  // (e.g., "bella"). UI ids are resolved through /v1/catalog's kokoro_voice
  // field — sending the bare UI id to Kokoro returns HTTP 400 "Voice not
  // found", which is silent failure from the dashboard's POV. This guard
  // keeps callers from having to know the difference.
  setVoice(voiceName) {
    if (/^[a-z]{2}_/.test(voiceName)) {
      this._voice = voiceName;
      log(`TTS voice set to: ${voiceName}`);
      return;
    }
    // Looks like a UI id — resolve via catalog (async; fire and forget).
    // Next utterance will use the resolved kokoro voice.
    log(`TTS voice "${voiceName}" looks like a UI id — resolving via catalog...`);
    fetch('/api/orch/v1/catalog')
      .then((r) => (r.ok ? r.json() : null))
      .then((cat) => {
        const v = cat?.voices?.find((x) => x.id === voiceName);
        if (v?.kokoro_voice) {
          this._voice = v.kokoro_voice;
          log(`TTS voice resolved: ${voiceName} → ${v.kokoro_voice}`);
        } else {
          warn(`TTS voice "${voiceName}" not found in catalog — keeping ${this._voice}`);
        }
      })
      .catch(() => {});
  }

  setSpeed(speed) {
    this._speed = speed;
  }

  _classifyError(err) {
    if (err.status === 503) return 'TTS service is busy — try again shortly';
    if (err.status >= 500) return `TTS server error (${err.status}) — check service logs`;
    if (err.status >= 400) return `TTS request error (${err.status}) — ${err.message}`;
    if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError')) {
      return 'Cannot reach TTS service — check if container is running';
    }
    return err.message;
  }

  clear() {
    this._queue = [];
    this._cancelled = true;
    if (this._abortController) {
      this._abortController.abort();
      this._abortController = null;
    }
  }

  get isReady() {
    return this.ready;
  }
}
