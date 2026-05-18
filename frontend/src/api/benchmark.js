/**
 * Benchmark runner — fires 3 fixed prompts against /v1/chat/completions
 * (single streaming request per prompt) and returns rows for the dashboard's
 * comparison table.
 *
 * Each prompt runs ONCE in streaming mode. We measure:
 *   - TTFT: time from request-send to first SSE chunk
 *   - E2E: wall-clock for the full stream
 *   - outputTokens: approximate count via whitespace-splitting the accumulated
 *     content. The orchestrator does not surface upstream-provider `usage`,
 *     so an exact token count is not available client-side. The whitespace
 *     approximation is ~1 token per word for BPE tokenizers — accurate
 *     enough for relative comparison between brains, which is the workshop
 *     purpose.
 *   - tokensPerSec: outputTokens / (e2eMs/1000)
 */

const BENCH_PROMPTS = [
  { id: 'short',     label: 'Short',     prompt: 'Say hi in one sentence.' },
  { id: 'wiki_tool', label: 'Wiki tool', prompt: 'What ports does NodeAva use?' },
  { id: 'long_gen',  label: 'Long gen',  prompt: 'Explain how the NodeAva pipeline works in detail.' },
];

/**
 * @typedef {Object} BenchmarkRow
 * @property {string} brainId
 * @property {string} brainLabel
 * @property {string} promptId
 * @property {string} promptLabel
 * @property {number} ttftMs       // time from request to first SSE chunk
 * @property {number} e2eMs        // wall-clock for the full streamed response
 * @property {number} outputTokens // word-count approximation of streamed content
 * @property {number} tokensPerSec // outputTokens / (e2eMs/1000); 0 if e2eMs is 0
 * @property {string} timestamp    // ISO string of when this row was recorded
 */

/**
 * Parse OpenAI-compatible SSE chunks out of a raw text blob and concatenate
 * their delta.content values into a single string.
 */
function _extractContent(rawSse) {
  let content = '';
  for (const line of rawSse.split('\n')) {
    if (!line.startsWith('data: ')) continue;
    const payload = line.slice(6).trim();
    if (!payload || payload === '[DONE]') continue;
    try {
      const obj = JSON.parse(payload);
      const delta = obj?.choices?.[0]?.delta?.content;
      if (delta) content += delta;
    } catch {
      // Non-JSON SSE line (e.g. event-name lines) — skip.
    }
  }
  return content;
}

async function _runOne(prompt) {
  const t0 = performance.now();
  let ttftMs = 0;

  const res = await fetch('/api/orch/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: [{ role: 'user', content: prompt }],
      stream: true,
    }),
  });
  if (!res.ok) throw new Error(`bench: ${res.status} ${res.statusText}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let raw = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    if (ttftMs === 0) ttftMs = performance.now() - t0;
    raw += decoder.decode(value, { stream: true });
  }
  raw += decoder.decode();  // flush
  const e2eMs = performance.now() - t0;

  const content = _extractContent(raw);
  const outputTokens = content.split(/\s+/).filter(Boolean).length;

  return { ttftMs, e2eMs, outputTokens };
}

/**
 * Run all 3 fixed prompts against the currently-active brain and return
 * one BenchmarkRow per prompt. Caller is responsible for swapping the brain
 * (via POST /v1/swap) before calling this — `brain` is just labeling.
 *
 * @param {object} brain {id, label} of the currently-active brain
 * @param {(progress:{promptIdx:number, promptLabel:string, total:number}) => void} onProgress
 * @returns {Promise<BenchmarkRow[]>}
 */
export async function runBenchmark(brain, onProgress = () => {}) {
  const rows = [];
  for (let i = 0; i < BENCH_PROMPTS.length; i++) {
    const p = BENCH_PROMPTS[i];
    onProgress({ promptIdx: i + 1, promptLabel: p.label, total: BENCH_PROMPTS.length });

    const { ttftMs, e2eMs, outputTokens } = await _runOne(p.prompt);
    const tokensPerSec = e2eMs > 0 ? (outputTokens / (e2eMs / 1000)) : 0;

    rows.push({
      brainId: brain.id,
      brainLabel: brain.label,
      promptId: p.id,
      promptLabel: p.label,
      ttftMs: Math.round(ttftMs),
      e2eMs: Math.round(e2eMs),
      outputTokens,
      tokensPerSec: Math.round(tokensPerSec * 10) / 10,
      timestamp: new Date().toISOString(),
    });
  }
  return rows;
}

export { BENCH_PROMPTS };
