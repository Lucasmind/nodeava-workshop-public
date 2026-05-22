/**
 * Plan #8 dashboard — fetch wrappers for /v1/catalog, /v1/state, /v1/swap.
 *
 * All requests go through the Vite proxy at /api/orch (configured in
 * vite.config.js to forward to localhost:8082).
 */

const BASE = '/api/orch';

export async function getCatalog() {
  const resp = await fetch(`${BASE}/v1/catalog`);
  if (!resp.ok) throw new Error(`getCatalog: HTTP ${resp.status}`);
  return await resp.json();
}

export async function getState() {
  const resp = await fetch(`${BASE}/v1/state`);
  if (!resp.ok) throw new Error(`getState: HTTP ${resp.status}`);
  return await resp.json();
}

/**
 * @param {string} kind one of "brain", "voice", "avatar", "personality", "tools"
 * @param {string} id catalog entry id, or tool name when kind=="tools"
 * @param {boolean|undefined} value required when kind=="tools"
 * @returns {Promise<object>} the new full state response (same shape as getState)
 */
export async function swap(kind, id, value) {
  const body = { kind, id };
  if (value !== undefined) body.value = value;
  const resp = await fetch(`${BASE}/v1/swap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
    throw new Error(err.error || `swap failed: HTTP ${resp.status}`);
  }
  return await resp.json();
}

/**
 * Plan #10 — POST a custom personality prompt. Returns the new server state.
 */
export async function postCustomPersonality(systemPrompt) {
  const res = await fetch('/api/orch/v1/personality/custom', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ system_prompt: systemPrompt }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`POST /v1/personality/custom: ${res.status} ${text}`);
  }
  return res.json();
}
