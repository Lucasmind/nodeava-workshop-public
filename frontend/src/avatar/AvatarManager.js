import { TalkingHead } from '@met4citizen/talkinghead';
import { config } from '../app/config.js';
import { log } from '../utils/logger.js';

export class AvatarManager {
  constructor({ dashboardState = null } = {}) {
    this.head = null;
    this.container = null;
    this.loaded = false;
    this._dashboardState = dashboardState;
  }

  async init(containerEl) {
    this.container = containerEl;

    this.head = new TalkingHead(this.container, {
      ttsEndpoint: null,
      lipsyncModules: ['en'],
      lipsyncLang: 'en',
      cameraView: config.cameraView,
      avatarMood: config.initialMood,
      avatarIdleEyeContact: 0.3,
      avatarSpeakingEyeContact: 0.6,
      avatarIdleHeadMove: 0.5,
      avatarSpeakingHeadMove: 0.5,
      pcmSampleRate: config.pcmSampleRate,
      modelFPS: 30,
      cameraRotateEnable: true,
      cameraPanEnable: false,
      cameraZoomEnable: false,
      lightAmbientIntensity: 2,
      lightDirectIntensity: 30,
    });

    log('AvatarManager initialized');
  }

  async _resolveAvatarUrl() {
    try {
      const resp = await fetch('/api/orch/v1/state');
      if (!resp.ok) return config.avatarUrl;
      const stateBody = await resp.json();
      const avatarId = stateBody?.active?.avatar;
      if (!avatarId) return config.avatarUrl;
      const catResp = await fetch('/api/orch/v1/catalog');
      if (!catResp.ok) return config.avatarUrl;
      const cat = await catResp.json();
      const entry = (cat.avatars || []).find((a) => a.id === avatarId);
      return entry?.glb_path || config.avatarUrl;
    } catch (_e) {
      return config.avatarUrl;
    }
  }

  async loadAvatar(url = null, onProgress = null) {
    if (url === null) {
      url = await this._resolveAvatarUrl();
    }
    if (!this.head) throw new Error('AvatarManager not initialized');

    log(`Loading avatar: ${url}`);

    await this.head.showAvatar(
      {
        url,
        body: config.avatarBody,
        avatarMood: config.initialMood,
        lipsyncLang: 'en',
      },
      onProgress
    );

    this.loaded = true;
    log('Avatar loaded');
  }

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

  setMood(mood) {
    if (!this.head || !this.loaded) return;
    this.head.setMood(mood);
  }

  setView(view, opts = {}) {
    if (!this.head) return;
    this.head.setView(view, opts);
  }

  speakAudio(audioData, opts = {}, onSubtitles = null) {
    if (!this.head || !this.loaded) return;
    this._dashboardState?.emit('avatar.speaking', {});
    this.head.speakAudio(audioData, opts, onSubtitles);
  }

  stopSpeaking() {
    if (!this.head) return;
    try {
      this.head.stopSpeaking();
    } catch {
      // May not have stopSpeaking — TalkingHead uses speech queue
    }
    this._dashboardState?.emit('avatar.idle', {});
  }

  lookAtCamera(durationMs = 1000) {
    if (!this.head) return;
    this.head.lookAtCamera(durationMs);
  }

  start() {
    if (this.head) this.head.start();
  }

  stop() {
    if (this.head) this.head.stop();
  }

  get audioCtx() {
    return this.head?.audioCtx || null;
  }

  get isLoaded() {
    return this.loaded;
  }
}
