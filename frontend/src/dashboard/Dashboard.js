/**
 * Plan #8 dashboard — top-level drawer container.
 *
 * Owns the drawer open/close state, mounts child components, listens for
 * keyboard shortcut. Children (ControlsPanel, FlowDiagram, EventLog) are
 * added in later tasks.
 *
 * Security: all server-returned strings (catalog labels, brain ids, etc.)
 * are placed in the DOM via textContent, never innerHTML.
 */

import * as api from './api.js';
import { ControlsPanel } from './components/ControlsPanel.js';
import { FlowDiagram } from './components/FlowDiagram.js';
import { EventLog } from './components/EventLog.js';
import { BenchmarkPanel } from './components/BenchmarkPanel.js';
import { PersonalityEditor } from './components/PersonalityEditor.js';
import { WalkthroughTrigger } from './components/WalkthroughTrigger.js';

export class Dashboard {
  /**
   * @param {DashboardState} state the shared dashboard state + event channel
   */
  constructor(state) {
    this.state = state;
    this.drawerEl = document.getElementById('nv-dash-drawer');
    this.toggleEl = document.getElementById('nv-dash-toggle');
    this.walkBtnEl = document.getElementById('nv-walk-trigger');
    this.controlsEl = document.getElementById('nv-dash-controls');
    this.benchEl = document.getElementById('nv-dash-bench');
    this.personalityEl = document.getElementById('nv-dash-personality');
    this.flowEl = document.getElementById('nv-dash-flow');
    this.eventsEl = document.getElementById('nv-dash-events');
    if (!this.drawerEl || !this.toggleEl) {
      throw new Error('Dashboard: drawer or toggle element missing from DOM');
    }
    if (!this.benchEl) {
      throw new Error('Dashboard: bench mount missing');
    }
    if (!this.personalityEl) throw new Error('Dashboard: personality mount missing');
    this._wireToggle();
    this._wireKeyboard();
    this._loadInitial();
  }

  _wireToggle() {
    this.toggleEl.addEventListener('click', () => this.toggle());
  }

  _wireKeyboard() {
    document.addEventListener('keydown', (e) => {
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if (e.key === ']') {
        e.preventDefault();
        this.toggle();
      }
    });
  }

  toggle() {
    const open = this.drawerEl.getAttribute('aria-hidden') === 'false';
    this.setOpen(!open);
  }

  setOpen(open) {
    this.drawerEl.setAttribute('aria-hidden', open ? 'false' : 'true');
    this.toggleEl.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  async _loadInitial() {
    try {
      const [catalog, state] = await Promise.all([api.getCatalog(), api.getState()]);
      this.state.catalog = catalog;
      this.state.setServerState(state);
      // Plan #10: refreshAvatarFromState is available here for future swap
      // callsites that route through Dashboard rather than ControlsPanel.
      // At boot the avatar is already loading via AvatarManager.loadAvatar(),
      // so we intentionally skip calling _refreshAvatar() here.
      this._mountControls();
    } catch (err) {
      console.error('[Dashboard] init failed:', err);
      this.controlsEl.replaceChildren();
      this.controlsEl.appendChild(document.createTextNode('Dashboard offline (orchestrator unreachable)'));
      // Even when offline, the walkthrough should be available so attendees
      // can use the ? button while waiting for the orchestrator to come up.
      if (this.walkBtnEl && !this.walkthroughTrigger) {
        try {
          this.walkthroughTrigger = new WalkthroughTrigger(this.walkBtnEl, this.state);
          // Skip initAutoStart on offline — attendee may just want to wait.
          // The ? button still works manually.
        } catch (_) { /* tolerate */ }
      }
    }
  }

  _mountControls() {
    this.controlsPanel = new ControlsPanel(this.controlsEl, this.state);
    this.flowDiagram = new FlowDiagram(this.flowEl, this.state);
    this.benchPanel = new BenchmarkPanel(this.benchEl, this.state);
    this.personalityEditor = new PersonalityEditor(this.personalityEl, this.state);
    this.eventLog = new EventLog(this.eventsEl, this.state);
    if (this.walkBtnEl) {
      this.walkthroughTrigger = new WalkthroughTrigger(this.walkBtnEl, this.state);
      this.walkthroughTrigger.initAutoStart();
    }
  }
}
