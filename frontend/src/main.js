import { Orchestrator } from './pipeline/Orchestrator.js';
import { UIManager } from './ui/UIManager.js';
import { log, error } from './utils/logger.js';
import { Dashboard } from './dashboard/Dashboard.js';
import { DashboardState } from './dashboard/state.js';

// Plan #10 — Meshopt support for compressed GLBs (e.g. HANA-Tool-processed
// VRoid models). TalkingHead constructs its own GLTFLoader per showAvatar
// and doesn't expose it. The GLTFLoader constructor sets
// `this.meshoptDecoder = null`, so a prototype-level field assignment is
// shadowed. Instead, wrap `parse` (called after loadAsync fetches the
// file) so we inject the decoder just before the parser snapshots options.
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
const _origGLTFLoaderParse = GLTFLoader.prototype.parse;
GLTFLoader.prototype.parse = function (...args) {
  if (!this.meshoptDecoder) this.meshoptDecoder = MeshoptDecoder;
  return _origGLTFLoaderParse.apply(this, args);
};

// Plan #8: create DashboardState first so it can be passed to Orchestrator
// and wired into the pipeline managers at construction time.
const dashboardState = new DashboardState();
const orchestrator = new Orchestrator({ dashboardState });
window.__orch = orchestrator; // debug access
window.__dashboardState = dashboardState;
let ui = null;

async function boot() {
  const container = document.getElementById('avatar-container');
  const loadingOverlay = createLoadingOverlay();
  document.body.appendChild(loadingOverlay);

  try {
    await orchestrator.init(container, (text, pct) => {
      updateLoading(loadingOverlay, text, pct);
    });

    ui = new UIManager(orchestrator);
    ui.init();

    // Plan #8: dashboard
    const dashboard = new Dashboard(dashboardState);
    window.__dash = dashboard; // debug access

    // Plan #8: expose manager globals for dashboard reach-in
    // after swaps (avatar → loadAvatar, voice → refreshVoiceFromState)
    window.__avatarManager = orchestrator.avatar;
    window.avatarManager = orchestrator.avatar; // Plan #10: canonical alias for refreshAvatarFromState
    window.__ttsManager = orchestrator.tts;
    window.__sttManager = orchestrator.stt;

    // Plan #10 — live avatar swap helper, mirrors refreshVoiceFromState pattern.
    window.refreshAvatarFromState = async function (serverState, catalog) {
      const activeId = serverState?.active?.avatar;
      if (!activeId) return;
      const entry = catalog?.avatars?.find((a) => a.id === activeId);
      if (!entry) return;
      if (window.avatarManager && entry.glb_path) {
        await window.avatarManager.reload(entry.glb_path, entry.body);
      }
    };

    await sleep(400);
    loadingOverlay.classList.add('hidden');
    setTimeout(() => loadingOverlay.remove(), 500);

    document.addEventListener('visibilitychange', () => {
      orchestrator.handleVisibility(document.visibilityState === 'visible');
    });

    log('Boot complete — all systems ready');
  } catch (err) {
    error('Boot failed:', err);
    updateLoading(loadingOverlay, `Error: ${err.message}`, 0);
  }
}

function createLoadingOverlay() {
  const overlay = document.createElement('div');
  overlay.className = 'loading-overlay';

  const text = document.createElement('div');
  text.className = 'loading-text';
  text.textContent = 'Loading...';

  const bar = document.createElement('div');
  bar.className = 'loading-bar';

  const fill = document.createElement('div');
  fill.className = 'loading-bar-fill';

  bar.appendChild(fill);
  overlay.appendChild(text);
  overlay.appendChild(bar);

  return overlay;
}

function updateLoading(overlay, text, pct) {
  const textEl = overlay.querySelector('.loading-text');
  const fillEl = overlay.querySelector('.loading-bar-fill');
  if (textEl) textEl.textContent = text;
  if (fillEl) fillEl.style.width = `${pct}%`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

boot();
