/**
 * Plan #10 — pick a verbal-filler phrase keyed to a tool family.
 *
 * Pure function. Maps a tool name to a random phrase from its pool.
 * Returns null if no pool matches — caller skips the filler entirely.
 */

const POOLS = {
  'wiki': [
    'Let me look that up.',
    'One second, checking my notes.',
    'Pulling that up now.',
  ],
  'browser': [
    'Let me search the web for that.',
    'One sec, looking that up online.',
    'Checking the web.',
  ],
};

/**
 * @param {string} toolName e.g. "wiki.search", "browser.search", "wiki.open"
 * @param {() => number} [rand=Math.random] dependency-inject for tests
 * @returns {string|null}
 */
export function pickPhrase(toolName, rand = Math.random) {
  if (!toolName || typeof toolName !== 'string') return null;
  const family = toolName.split('.')[0];
  const pool = POOLS[family];
  if (!pool || pool.length === 0) return null;
  return pool[Math.floor(rand() * pool.length)];
}

// Inline self-test for the dev-build only.
if (import.meta?.env?.DEV) {
  console.assert(pickPhrase('wiki.search', () => 0) === 'Let me look that up.', 'pickPhrase wiki[0]');
  console.assert(pickPhrase('browser.search', () => 0.99) === 'Checking the web.', 'pickPhrase browser[last]');
  console.assert(pickPhrase('unknown.tool') === null, 'pickPhrase unknown family');
  console.assert(pickPhrase(null) === null, 'pickPhrase null toolName');
  console.assert(pickPhrase('wiki.open', () => 0.5) === 'One second, checking my notes.', 'pickPhrase wiki middle');
}
