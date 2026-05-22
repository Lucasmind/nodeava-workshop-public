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
