/**
 * Plan #8 — reusable selector component.
 *
 * Usage:
 *   const sel = new Selector({
 *     label: 'Brain',
 *     options: [
 *       {value:'qwen3-4b', label:'Qwen3 4B', available:true, reason:null},
 *       {value:'claude-sonnet', label:'Claude Sonnet', available:false, reason:'set ANTHROPIC_API_KEY'},
 *     ],
 *     value: 'qwen3-4b',
 *     onChange: async (newValue) => { ... },
 *     showChip: true, // optional residency chip slot
 *   });
 *   parent.appendChild(sel.el);
 *   sel.setChip({label:'gpu', color:'green'}); // optional
 *
 * All option labels are inserted via textContent (no HTML injection).
 */

export class Selector {
  constructor({ label, options, value, onChange, showChip = false }) {
    this.onChange = onChange;
    this.el = document.createElement('div');
    this.el.className = 'nv-dash-row';

    const labelEl = document.createElement('div');
    labelEl.className = 'nv-dash-row-label';
    labelEl.textContent = label;
    this.el.appendChild(labelEl);

    const controlRow = document.createElement('div');
    controlRow.className = 'nv-dash-row-control';
    this.el.appendChild(controlRow);

    this.selectEl = document.createElement('select');
    this.selectEl.className = 'nv-dash-select';
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label + (opt.available === false ? ' (unavailable)' : '');
      if (opt.available === false) {
        o.disabled = true;
        if (opt.reason) o.title = opt.reason;
      }
      this.selectEl.appendChild(o);
    }
    this.selectEl.value = value;
    this.selectEl.addEventListener('change', () => this._handleChange());
    controlRow.appendChild(this.selectEl);

    if (showChip) {
      this.chipEl = document.createElement('span');
      this.chipEl.className = 'nv-dash-chip nv-dash-chip-empty';
      controlRow.appendChild(this.chipEl);
    }

    this.errorEl = document.createElement('div');
    this.errorEl.className = 'nv-dash-row-error';
    this.el.appendChild(this.errorEl);
  }

  async _handleChange() {
    const newValue = this.selectEl.value;
    this.errorEl.textContent = '';
    try {
      await this.onChange(newValue);
    } catch (err) {
      // Show error inline; selector value stays at user's choice (no auto-revert).
      this.errorEl.textContent = err.message || String(err);
    }
  }

  setValue(value) {
    this.selectEl.value = value;
  }

  /**
   * Plan #10 fix — rebuild the option list (e.g. after a custom personality
   * is added to the catalog at runtime). The change listener stays attached
   * since selectEl itself is not replaced.
   *
   * @param {Array<{value, label, available?, reason?}>} options
   * @param {string} [value] optional selection after rebuild
   */
  setOptions(options, value) {
    this.selectEl.replaceChildren();
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = opt.value;
      o.textContent = opt.label + (opt.available === false ? ' (unavailable)' : '');
      if (opt.available === false) {
        o.disabled = true;
        if (opt.reason) o.title = opt.reason;
      }
      this.selectEl.appendChild(o);
    }
    if (value !== undefined) this.selectEl.value = value;
  }

  /**
   * Update the chip (residency or status indicator).
   * @param {{label:string, color:'green'|'yellow'|'red'|'gray'|'blue'}|null} chip
   *   pass null to clear.
   */
  setChip(chip) {
    if (!this.chipEl) return;
    if (!chip) {
      this.chipEl.textContent = '';
      this.chipEl.className = 'nv-dash-chip nv-dash-chip-empty';
      return;
    }
    this.chipEl.textContent = chip.label;
    this.chipEl.className = `nv-dash-chip nv-dash-chip-${chip.color}`;
  }
}
