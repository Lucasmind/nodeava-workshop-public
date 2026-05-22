/**
 * Plan #10 — Spotlight walkthrough.
 *
 * Renders a full-page overlay with an SVG mask that cuts out the bounding
 * box of the current target element ("spotlight"), and positions a tooltip
 * adjacent to it. Steps advance via Next / Back / Skip buttons.
 *
 * Element selectors target dashboard surfaces. If a selector can't be
 * resolved, that step's spotlight falls back to a centered tooltip with no
 * cutout.
 */

const STEPS = [
  {
    target: '#avatar-container',
    title: 'Meet Ava',
    body: 'This is Ava. She runs entirely on your machine — no cloud APIs. Speech-to-text, the language model, text-to-speech, and her face are all local.',
  },
  {
    target: '#nv-mic-btn, #nv-send-btn',
    title: 'Talk or type',
    body: 'Click the Mic button to start listening (click it again to stop), or type a message and press Send. Either works.',
  },
  {
    target: '#nv-dash-toggle',
    title: 'Open the control drawer',
    body: 'Click this button (or press the "]" key) to open the dashboard. Everything you can swap or measure lives in there.',
    onAdvance: () => {
      // Open the drawer for the next steps
      document.getElementById('nv-dash-drawer')?.setAttribute('aria-hidden', 'false');
      document.getElementById('nv-dash-toggle')?.setAttribute('aria-expanded', 'true');
    },
  },
  {
    target: '#nv-dash-brain-row',
    title: 'Swap the brain',
    body: 'Pick the language model that drives her responses. Try the tiny SmolLM2 for fast-but-dumb, then Qwen3 4B for smart. You can swap mid-conversation.',
  },
  {
    target: '#nv-dash-tools-row',
    title: 'Give her tools',
    body: 'Toggle Web Search to let her answer current-event questions. Toggle Wiki to let her look up project knowledge. The toggles change behavior on the next turn.',
  },
  {
    target: '#nv-dash-flow',
    title: 'See the pipeline',
    body: 'This flow diagram lights up as each stage runs. The small chips show stage durations — you can watch where time goes per turn.',
  },
  {
    target: '#nv-dash-bench, #nv-dash-personality',
    title: 'Benchmark + make it yours',
    body: 'Click Benchmark to compare brains side-by-side. Edit the personality below to change how Ava speaks. Have fun.',
  },
];

export class Walkthrough {
  constructor() {
    this.idx = 0;
    this.overlayEl = null;
    this.maskRectEl = null;
    this.tooltipEl = null;
    this._resizeListener = null;
  }

  start() {
    this.idx = 0;
    this._mount();
    this._render();
  }

  end() {
    this._unmount();
  }

  isActive() {
    return this.overlayEl !== null && this.overlayEl.isConnected;
  }

  _mount() {
    if (this.overlayEl) return;

    this.overlayEl = document.createElement('div');
    this.overlayEl.className = 'nv-walk-overlay';
    this.overlayEl.setAttribute('role', 'dialog');
    this.overlayEl.setAttribute('aria-label', 'NodeAva walkthrough');

    // SVG mask: full-screen black rect minus a transparent hole over the target.
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.classList.add('nv-walk-svg');
    svg.setAttribute('xmlns', svgNS);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');

    const defs = document.createElementNS(svgNS, 'defs');
    const mask = document.createElementNS(svgNS, 'mask');
    mask.id = 'nv-walk-mask';
    const bg = document.createElementNS(svgNS, 'rect');
    bg.setAttribute('x', '0'); bg.setAttribute('y', '0');
    bg.setAttribute('width', '100%'); bg.setAttribute('height', '100%');
    bg.setAttribute('fill', 'white');
    const hole = document.createElementNS(svgNS, 'rect');
    hole.setAttribute('fill', 'black');
    hole.setAttribute('rx', '6'); hole.setAttribute('ry', '6');
    mask.appendChild(bg);
    mask.appendChild(hole);
    defs.appendChild(mask);
    svg.appendChild(defs);

    const dim = document.createElementNS(svgNS, 'rect');
    dim.setAttribute('x', '0'); dim.setAttribute('y', '0');
    dim.setAttribute('width', '100%'); dim.setAttribute('height', '100%');
    dim.setAttribute('fill', 'rgba(0,0,0,0.55)');
    dim.setAttribute('mask', 'url(#nv-walk-mask)');
    svg.appendChild(dim);

    this.maskRectEl = hole;
    this.overlayEl.appendChild(svg);

    // Tooltip
    this.tooltipEl = document.createElement('div');
    this.tooltipEl.className = 'nv-walk-tooltip';
    this.overlayEl.appendChild(this.tooltipEl);

    document.body.appendChild(this.overlayEl);

    this._resizeListener = () => this._render();
    window.addEventListener('resize', this._resizeListener);
  }

  _unmount() {
    if (this._resizeListener) {
      window.removeEventListener('resize', this._resizeListener);
      this._resizeListener = null;
    }
    if (this.overlayEl) {
      this.overlayEl.remove();
      this.overlayEl = null;
      this.maskRectEl = null;
      this.tooltipEl = null;
    }
  }

  _render() {
    const step = STEPS[this.idx];
    if (!step) {
      this.end();
      return;
    }

    // Resolve target (first match across the selector list)
    let targetEl = null;
    for (const sel of step.target.split(/\s*,\s*/)) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) {  // visible
        targetEl = el;
        break;
      }
    }

    if (targetEl) {
      const r = targetEl.getBoundingClientRect();
      const pad = 8;
      this.maskRectEl.setAttribute('x', String(Math.max(0, r.left - pad)));
      this.maskRectEl.setAttribute('y', String(Math.max(0, r.top - pad)));
      this.maskRectEl.setAttribute('width', String(r.width + pad * 2));
      this.maskRectEl.setAttribute('height', String(r.height + pad * 2));
      this._positionTooltip(r);
    } else {
      // Fallback: center the tooltip, no cutout
      this.maskRectEl.setAttribute('width', '0');
      this.maskRectEl.setAttribute('height', '0');
      this.tooltipEl.style.left = '50%';
      this.tooltipEl.style.top = '50%';
      this.tooltipEl.style.transform = 'translate(-50%, -50%)';
    }

    // Tooltip content
    this.tooltipEl.replaceChildren();
    const title = document.createElement('div');
    title.className = 'nv-walk-tooltip-title';
    title.textContent = step.title;
    const body = document.createElement('div');
    body.className = 'nv-walk-tooltip-body';
    body.textContent = step.body;
    const counter = document.createElement('div');
    counter.className = 'nv-walk-tooltip-counter';
    counter.textContent = `Step ${this.idx + 1} of ${STEPS.length}`;
    const btns = document.createElement('div');
    btns.className = 'nv-walk-tooltip-btns';

    const skip = document.createElement('button');
    skip.textContent = 'Skip';
    skip.className = 'nv-walk-btn-skip';
    skip.addEventListener('click', () => this.end());
    const back = document.createElement('button');
    back.textContent = 'Back';
    back.disabled = this.idx === 0;
    back.addEventListener('click', () => { this.idx--; this._render(); });
    const next = document.createElement('button');
    next.textContent = this.idx === STEPS.length - 1 ? 'Done' : 'Next';
    next.addEventListener('click', () => {
      if (step.onAdvance) step.onAdvance();
      this.idx++;
      if (this.idx >= STEPS.length) this.end();
      else this._render();
    });

    btns.appendChild(skip);
    btns.appendChild(back);
    btns.appendChild(next);

    this.tooltipEl.appendChild(counter);
    this.tooltipEl.appendChild(title);
    this.tooltipEl.appendChild(body);
    this.tooltipEl.appendChild(btns);
  }

  _positionTooltip(targetRect) {
    // Prefer below if there's room; otherwise above; otherwise centered.
    const t = this.tooltipEl;
    t.style.transform = '';
    const margin = 14;
    const tw = 320;  // matches CSS max-width
    const th = 180;  // rough estimate; CSS bounds it tightly
    let top = targetRect.bottom + margin;
    if (top + th > window.innerHeight - margin) {
      top = targetRect.top - th - margin;
    }
    if (top < margin) top = margin;
    let left = targetRect.left + (targetRect.width - tw) / 2;
    left = Math.max(margin, Math.min(window.innerWidth - tw - margin, left));
    t.style.left = `${left}px`;
    t.style.top = `${top}px`;
  }
}
