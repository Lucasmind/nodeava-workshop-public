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
    this.brainSel.el.id = 'nv-dash-brain-row';
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
        // Plan #10: use reload() for live swap; refreshAvatarFromState looks up
        // glb_path + body from the catalog so we don't need to duplicate that logic.
        if (window.refreshAvatarFromState) {
          try {
            await window.refreshAvatarFromState(resp, this.state.catalog);
          } catch (e) {
            // Surface the failure via the selector's built-in errorEl.
            this.avatarSel.errorEl.textContent = `Avatar load failed: ${e.message || e}`;
            console.error('[ControlsPanel] avatar reload failed:', e);
          }
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
    toolRow.id = 'nv-dash-tools-row';

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
        cb.checked = !cb.checked;
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
    if (this.personalitySel) {
      // Plan #10 fix — catalog may have grown a 'custom' personality at runtime.
      // If the active id isn't an existing <option>, rebuild from the catalog.
      const opts = [...this.personalitySel.selectEl.options].map((o) => o.value);
      if (active.personality && !opts.includes(active.personality)) {
        const cat = this.state.catalog;
        this.personalitySel.setOptions(
          (cat?.personalities || []).map((p) => ({ value: p.id, label: p.label, available: p.available })),
          active.personality,
        );
      } else {
        this.personalitySel.setValue(active.personality);
      }
    }
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
    if (brainEntry.kind === 'lmstudio') {
      // Plan #11: LM Studio reports binary loaded-state (no VRAM split). The
      // residency snapshot lives under system.ollama (legacy key) regardless
      // of the active backend.
      const loadedList = ollama.loaded || [];
      if (brainEntry.model === 'auto' || !brainEntry.model) {
        this.brainSel.setChip(
          loadedList.length
            ? { label: 'loaded', color: 'green' }
            : { label: 'auto', color: 'blue' },
        );
        return;
      }
      const isLoaded = loadedList.some((m) => m.model === brainEntry.model);
      this.brainSel.setChip(
        isLoaded
          ? { label: 'loaded', color: 'green' }
          : { label: 'not loaded', color: 'gray' },
      );
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
