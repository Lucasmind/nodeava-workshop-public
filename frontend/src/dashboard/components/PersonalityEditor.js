/**
 * Plan #10 — Personality editor.
 *
 * In the drawer: compact summary + "✎ Edit personality" button.
 * Clicking opens a modal overlay with a roomy textarea + Save/Reset/Cancel.
 *
 * Save POSTs /v1/personality/custom and switches to it. Reset swaps back
 * to the catalog's default personality.
 */

import { postCustomPersonality, swap } from '../api.js';

export class PersonalityEditor {
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this._modalEl = null;
    this._modalTextarea = null;
    this._modalStatus = null;
    this._dirty = false;
    this._build();
    this.state.addEventListener('state', () => this._refreshSummary());
  }

  _build() {
    this.mountEl.replaceChildren();

    const header = document.createElement('div');
    header.className = 'nv-dash-personality-header';
    header.textContent = 'PERSONALITY EDITOR';
    this.mountEl.appendChild(header);

    this.openBtn = document.createElement('button');
    this.openBtn.className = 'nv-dash-personality-open';
    this.openBtn.textContent = '✎ Edit personality';
    this.openBtn.addEventListener('click', () => this._openModal());
    this.mountEl.appendChild(this.openBtn);

    this.summaryEl = document.createElement('div');
    this.summaryEl.className = 'nv-dash-personality-summary';
    this.mountEl.appendChild(this.summaryEl);

    this._refreshSummary();
  }

  _refreshSummary() {
    const activeId = this.state.serverState?.active?.personality;
    const p = activeId ? this.state.getPersonality(activeId) : null;
    const label = p?.label || activeId || '—';
    const preview = (p?.system_prompt || '').replace(/\s+/g, ' ').slice(0, 80);
    this.summaryEl.replaceChildren();
    const labelEl = document.createElement('div');
    labelEl.className = 'nv-dash-personality-summary-label';
    labelEl.textContent = `Active: ${label}`;
    this.summaryEl.appendChild(labelEl);
    if (preview) {
      const previewEl = document.createElement('div');
      previewEl.className = 'nv-dash-personality-summary-preview';
      previewEl.textContent = preview + (p.system_prompt.length > 80 ? '…' : '');
      this.summaryEl.appendChild(previewEl);
    }
  }

  _openModal() {
    if (this._modalEl) return;
    this._dirty = false;

    this._modalEl = document.createElement('div');
    this._modalEl.className = 'nv-pers-modal-overlay';
    this._modalEl.setAttribute('role', 'dialog');
    this._modalEl.setAttribute('aria-label', 'Personality editor');
    this._modalEl.addEventListener('click', (e) => {
      if (e.target === this._modalEl) this._closeModal();
    });

    const panel = document.createElement('div');
    panel.className = 'nv-pers-modal-panel';

    const titleBar = document.createElement('div');
    titleBar.className = 'nv-pers-modal-titlebar';
    const titleEl = document.createElement('div');
    titleEl.className = 'nv-pers-modal-title';
    titleEl.textContent = 'Personality editor';
    titleBar.appendChild(titleEl);
    const closeX = document.createElement('button');
    closeX.className = 'nv-pers-modal-close';
    closeX.textContent = '✕';
    closeX.setAttribute('aria-label', 'Close');
    closeX.addEventListener('click', () => this._closeModal());
    titleBar.appendChild(closeX);
    panel.appendChild(titleBar);

    const help = document.createElement('div');
    help.className = 'nv-pers-modal-help';
    help.textContent =
      'Write a system prompt that defines how Ava behaves. ' +
      'Tip: keep the [emotion] bracket convention — the avatar reads ' +
      '[happy] / [sad] / [neutral] etc. as a mood signal and strips it ' +
      'from the spoken text.';
    panel.appendChild(help);

    this._modalTextarea = document.createElement('textarea');
    this._modalTextarea.className = 'nv-pers-modal-textarea';
    this._modalTextarea.placeholder = 'Write the system prompt that defines how Ava behaves…';
    this._modalTextarea.addEventListener('input', () => { this._dirty = true; });
    // Seed from active personality
    const activeId = this.state.serverState?.active?.personality;
    const p = activeId ? this.state.getPersonality(activeId) : null;
    if (p?.system_prompt) this._modalTextarea.value = p.system_prompt;
    panel.appendChild(this._modalTextarea);

    const btnRow = document.createElement('div');
    btnRow.className = 'nv-pers-modal-btnrow';

    this._modalStatus = document.createElement('div');
    this._modalStatus.className = 'nv-pers-modal-status';
    btnRow.appendChild(this._modalStatus);

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'nv-pers-modal-btn-cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => this._closeModal());
    btnRow.appendChild(cancelBtn);

    const resetBtn = document.createElement('button');
    resetBtn.className = 'nv-pers-modal-btn-reset';
    resetBtn.textContent = 'Reset to default';
    resetBtn.addEventListener('click', () => this._reset());
    btnRow.appendChild(resetBtn);

    const saveBtn = document.createElement('button');
    saveBtn.className = 'nv-pers-modal-btn-save';
    saveBtn.textContent = 'Save as My Personality';
    saveBtn.addEventListener('click', () => this._save(saveBtn));
    btnRow.appendChild(saveBtn);

    panel.appendChild(btnRow);
    this._modalEl.appendChild(panel);
    document.body.appendChild(this._modalEl);

    // Esc to close
    this._modalKeyHandler = (e) => {
      if (e.key === 'Escape') this._closeModal();
    };
    document.addEventListener('keydown', this._modalKeyHandler);

    // Focus textarea
    setTimeout(() => this._modalTextarea?.focus(), 0);
  }

  _closeModal() {
    if (!this._modalEl) return;
    document.removeEventListener('keydown', this._modalKeyHandler);
    this._modalEl.remove();
    this._modalEl = null;
    this._modalTextarea = null;
    this._modalStatus = null;
    this._dirty = false;
  }

  async _save(saveBtn) {
    const prompt = this._modalTextarea.value.trim();
    if (!prompt) {
      this._modalStatus.textContent = 'Cannot save an empty prompt.';
      return;
    }
    saveBtn.disabled = true;
    this._modalStatus.textContent = 'Saving…';
    try {
      const newState = await postCustomPersonality(prompt);
      // Inject the custom entry into the local catalog so the selector has a matching <option>.
      const cat = this.state.catalog;
      if (cat?.personalities) {
        const customEntry = {
          id: 'custom',
          label: 'My Personality (custom)',
          system_prompt: prompt,
          available: true,
        };
        const i = cat.personalities.findIndex((p) => p.id === 'custom');
        if (i >= 0) cat.personalities[i] = customEntry;
        else cat.personalities.push(customEntry);
      }
      this.state.setServerState(newState);
      this._modalStatus.textContent = 'Saved. Next turn will use this personality.';
      this._dirty = false;
      setTimeout(() => this._closeModal(), 700);
    } catch (err) {
      this._modalStatus.textContent = `Failed: ${err.message}`;
    } finally {
      saveBtn.disabled = false;
    }
  }

  async _reset() {
    const defaultPersonality = (this.state.catalog?.personalities || []).find(
      (p) => p.default === true,
    );
    if (!defaultPersonality) return;
    try {
      const newState = await swap('personality', defaultPersonality.id);
      this.state.setServerState(newState);
      // Re-seed textarea from new active personality
      if (this._modalTextarea) {
        this._modalTextarea.value = defaultPersonality.system_prompt || '';
      }
      this._dirty = false;
      if (this._modalStatus) {
        this._modalStatus.textContent = `Reset to "${defaultPersonality.label}".`;
      }
    } catch (err) {
      if (this._modalStatus) this._modalStatus.textContent = `Reset failed: ${err.message}`;
    }
  }
}
