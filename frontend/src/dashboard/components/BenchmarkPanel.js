/**
 * Plan #10 — Benchmark widget.
 *
 * Renders a "Benchmark this brain" button + a comparison table. Each click
 * runs 3 fixed prompts against the currently-active brain (via api/benchmark.js)
 * and appends 3 rows to the table. Rows persist in memory until "Clear" is
 * clicked or the page reloads.
 */

import { runBenchmark } from '../../api/benchmark.js';
import { log } from '../../utils/logger.js';

export class BenchmarkPanel {
  constructor(mountEl, state) {
    this.mountEl = mountEl;
    this.state = state;
    this.rows = [];
    this.running = false;
    this._build();
    this.state.addEventListener('state', () => this._refreshButtonLabel());
  }

  _build() {
    this.mountEl.replaceChildren();

    const header = document.createElement('div');
    header.className = 'nv-dash-bench-header';
    header.textContent = 'BENCHMARK';
    this.mountEl.appendChild(header);

    this.btnEl = document.createElement('button');
    this.btnEl.className = 'nv-dash-bench-btn';
    this.btnEl.addEventListener('click', () => this._run());
    this.mountEl.appendChild(this.btnEl);

    this.statusEl = document.createElement('div');
    this.statusEl.className = 'nv-dash-bench-status';
    this.statusEl.textContent = '';
    this.mountEl.appendChild(this.statusEl);

    this.tableEl = document.createElement('table');
    this.tableEl.className = 'nv-dash-bench-table';
    this.mountEl.appendChild(this.tableEl);

    this.clearBtn = document.createElement('button');
    this.clearBtn.className = 'nv-dash-bench-clear';
    this.clearBtn.textContent = 'Clear table';
    this.clearBtn.addEventListener('click', () => {
      this.rows = [];
      this._renderTable();
    });
    this.mountEl.appendChild(this.clearBtn);

    this._refreshButtonLabel();
    this._renderTable();
  }

  _refreshButtonLabel() {
    const brain = this._activeBrain();
    if (!brain) {
      this.btnEl.textContent = 'Benchmark (loading brain…)';
      this.btnEl.disabled = true;
      return;
    }
    this.btnEl.textContent = this.running
      ? 'Running…'
      : `Benchmark ${brain.label}`;
    this.btnEl.disabled = this.running;
  }

  _activeBrain() {
    const id = this.state.serverState?.active?.brain;
    return id ? this.state.getBrain(id) : null;
  }

  async _run() {
    const brain = this._activeBrain();
    if (!brain || this.running) return;
    this.running = true;
    this._refreshButtonLabel();
    this.statusEl.textContent = 'Starting…';
    try {
      const rows = await runBenchmark(brain, ({ promptIdx, promptLabel, total }) => {
        this.statusEl.textContent = `Running ${promptIdx} of ${total}: ${promptLabel}`;
      });
      this.rows.push(...rows);
      this.statusEl.textContent = `Done (${rows.length} rows added).`;
      this._renderTable();
    } catch (err) {
      log('Benchmark failed', err);
      this.statusEl.textContent = `Failed: ${err.message}`;
    } finally {
      this.running = false;
      this._refreshButtonLabel();
    }
  }

  _renderTable() {
    this.tableEl.replaceChildren();
    if (this.rows.length === 0) {
      const empty = document.createElement('caption');
      empty.textContent = 'No runs yet. Click the button above to start.';
      this.tableEl.appendChild(empty);
      this.clearBtn.style.display = 'none';
      return;
    }
    this.clearBtn.style.display = '';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const h of ['Brain', 'Prompt', 'TTFT', 'Tok/s', 'E2E', 'Tokens']) {
      const th = document.createElement('th');
      th.textContent = h;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    this.tableEl.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const r of this.rows) {
      const tr = document.createElement('tr');
      const cells = [
        r.brainLabel,
        r.promptLabel,
        `${(r.ttftMs / 1000).toFixed(2)}s`,
        r.tokensPerSec.toFixed(1),
        `${(r.e2eMs / 1000).toFixed(2)}s`,
        String(r.outputTokens),
      ];
      for (const c of cells) {
        const td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    this.tableEl.appendChild(tbody);
  }
}
