/**
 * Plan #10 — Walkthrough trigger + first-load persistence.
 *
 * On page load: if localStorage flag `nodeava.walkthrough.completed` is
 * unset, auto-start the walkthrough once the dashboard's state has loaded
 * (so the spotlight targets in steps 4-7 actually exist).
 *
 * Clicking the "?" button always re-starts the walkthrough.
 */

import { Walkthrough } from './Walkthrough.js';

const LS_KEY = 'nodeava.walkthrough.completed';

export class WalkthroughTrigger {
  constructor(btnEl, dashboardState = null) {
    if (!btnEl) throw new Error('WalkthroughTrigger: button element required');
    this.btnEl = btnEl;
    this.state = dashboardState;
    this.walk = new Walkthrough();
    this.btnEl.addEventListener('click', () => this._startManual());
  }

  /**
   * Called once at app init. Triggers the auto-tour on first run.
   * Waits for the first 'state' event from DashboardState before firing
   * (which guarantees controls/selectors have rendered) and adds a small
   * settling delay so layout is final.
   */
  initAutoStart() {
    if (localStorage.getItem(LS_KEY)) return;
    const fire = () => {
      // Settling delay so any drawer-opening transitions finish before the
      // spotlight measures bounding rects.
      setTimeout(() => {
        if (!this.walk.isActive()) this._startAuto();
      }, 600);
    };
    if (this.state && !this.state.serverState) {
      // State hasn't arrived yet — wait for it once.
      const onState = () => {
        this.state.removeEventListener('state', onState);
        fire();
      };
      this.state.addEventListener('state', onState);
      // Fallback timer in case state never arrives (offline orchestrator).
      setTimeout(fire, 2500);
    } else {
      fire();
    }
  }

  _startAuto() {
    this._startCommon();
  }

  _startManual() {
    this._startCommon();
  }

  _startCommon() {
    if (this.walk.isActive()) return;
    this.walk.start();
    // Patch the walkthrough's end() so completion marks the flag.
    const origEnd = this.walk.end.bind(this.walk);
    this.walk.end = () => {
      origEnd();
      try { localStorage.setItem(LS_KEY, '1'); } catch (_) { /* private mode */ }
      this.walk.end = origEnd;
    };
  }
}
