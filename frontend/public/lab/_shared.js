// NodeAva Workshop Lab — shared utilities.
// Vanilla JS, no build step. All DOM mutations use textContent + element
// children rather than innerHTML, so a stray '<' in a response can't
// execute as markup.

// ── Timing helpers ─────────────────────────────────────────────────────
const now = () => performance.now();
const ms = (d) => `${d.toFixed(0)} ms`;
const sec = (d) => `${(d / 1000).toFixed(2)} s`;

function setChip(id, label, value, status = "") {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = "chip" + (status ? " " + status : "");
  while (el.firstChild) el.removeChild(el.firstChild);
  el.appendChild(document.createTextNode(label + " "));
  const b = document.createElement("b");
  b.textContent = String(value);
  el.appendChild(b);
}

function clearChips(...ids) {
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = "chip";
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(document.createTextNode((el.dataset.label || "") + " "));
    const b = document.createElement("b");
    b.textContent = "—";
    el.appendChild(b);
  });
}

// ── Console logger ─────────────────────────────────────────────────────
function logLine(consoleEl, text, type = "") {
  const div = document.createElement("div");
  div.className = "line" + (type ? " " + type : "");
  div.textContent = String(text);
  consoleEl.appendChild(div);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

function clearConsole(consoleEl) {
  while (consoleEl.firstChild) consoleEl.removeChild(consoleEl.firstChild);
}

// ── SSE parser for streaming responses ─────────────────────────────────
// Yields one object per complete SSE message:
//   { event: "message" | "<name>", data: <parsed JSON object> | "[DONE]" }
// Pairs `event:` lines with the following `data:` line so callers can
// dispatch on event.event (default "message" for un-named events, i.e.
// OpenAI-style token chunks).
async function* parseSSE(response) {
  if (!response.body) throw new Error("no response body for SSE");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let curEvent = "message";
  let curData = null;

  const flush = () => {
    if (curData == null) return null;
    const out = { event: curEvent, data: curData };
    curEvent = "message";
    curData = null;
    return out;
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).replace(/\r$/, "");
      buf = buf.slice(idx + 1);
      if (!line) {
        // Empty line ends the current message
        const msg = flush();
        if (msg) yield msg;
        continue;
      }
      if (line.startsWith(":")) continue; // comment
      if (line.startsWith("event:")) {
        curEvent = line.slice(6).trim();
        continue;
      }
      if (line.startsWith("data:")) {
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") { curData = "[DONE]"; continue; }
        try { curData = JSON.parse(payload); } catch { curData = { __raw: payload }; }
      }
    }
  }
  const tail = flush();
  if (tail) yield tail;
}

// ── Decode Kokoro PCM JSON → playable WAV Blob ─────────────────────────
// Kokoro /dev/captioned_speech with response_format=pcm returns base64 PCM
// (16-bit signed, mono, 24 kHz). Wrap in a WAV header so <audio> can play.
function pcmToWavBlob(pcmBytes, sampleRate = 24000, channels = 1, bitsPerSample = 16) {
  const byteRate = sampleRate * channels * bitsPerSample / 8;
  const blockAlign = channels * bitsPerSample / 8;
  const dataSize = pcmBytes.byteLength;
  const buf = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buf);
  const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  new Uint8Array(buf, 44).set(new Uint8Array(pcmBytes));
  return new Blob([buf], { type: "audio/wav" });
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}

// ── Pre-flight probe ───────────────────────────────────────────────────
async function preflight(elId, services) {
  const el = document.getElementById(elId);
  if (!el) return true;
  el.className = "preflight checking";
  el.textContent = "Checking services…";
  const probes = {
    // 'llm' = orchestrator-routed LLM endpoint (the path Plan #7+ chat uses)
    llm:    () => fetch("/api/llm/v1/models").then(r => r.ok),
    // 'ollama' = bypasses the orchestrator, hits Ollama on the host directly.
    // Lab 1 uses this so attendees measure raw LLM TTFT without the
    // orchestrator's personality prefill or agentic tool loop in the way.
    ollama: () => fetch("/api/ollama/v1/models").then(r => r.ok),
    tts:    () => fetch("/api/tts/v1/audio/voices").then(r => r.ok),
    stt:    () => fetch("/api/stt/").then(r => r.ok || r.status === 404 || r.status === 405),
    orch:   () => fetch("/api/orch/v1/state").then(r => r.ok),
  };
  const results = await Promise.all(services.map(async (s) => {
    try { return { s, ok: await probes[s]() }; }
    catch { return { s, ok: false }; }
  }));
  const failed = results.filter(r => !r.ok).map(r => r.s);
  if (failed.length === 0) {
    el.className = "preflight ok";
    el.textContent = "✓ All services reachable: " + services.join(", ");
    return true;
  }
  el.className = "preflight error";
  el.textContent = "✗ Services not reachable: " + failed.join(", ") + ". Start them and refresh.";
  return false;
}

// ── Format helpers ─────────────────────────────────────────────────────
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(2) + " MB";
}

// ── Small live-list helpers ────────────────────────────────────────────
// Fetch the list of Ollama models the host has pulled. Returns
// e.g. [{name:"qwen3:4b-instruct", size_bytes:N}, ...] or [] on error.
async function listOllamaModels() {
  try {
    const r = await fetch("/api/ollama/v1/models");
    if (!r.ok) return [];
    const j = await r.json();
    // OpenAI-compatible shape: { data: [{id: "qwen3:4b-instruct"}, ...] }
    return (j.data || []).map(d => ({ name: d.id }));
  } catch { return []; }
}

// Populate a <select> with the given options. Each option is {value, label, selected?}.
function fillSelect(selEl, options) {
  while (selEl.firstChild) selEl.removeChild(selEl.firstChild);
  for (const o of options) {
    const opt = document.createElement("option");
    opt.value = o.value;
    opt.textContent = o.label;
    if (o.selected) opt.selected = true;
    selEl.appendChild(opt);
  }
}

// Bind a range slider to a display element + change handler. Returns a
// getValue() function.
function bindSlider(sliderEl, valEl, fmt) {
  const fmtFn = fmt || ((v) => String(v));
  const sync = () => { if (valEl) valEl.textContent = fmtFn(sliderEl.value); };
  sliderEl.addEventListener("input", sync);
  sync();
  return () => sliderEl.value;
}

window.NA = {
  now, ms, sec, setChip, clearChips,
  logLine, clearConsole,
  parseSSE, pcmToWavBlob, b64ToBytes,
  preflight, fmtBytes,
  listOllamaModels, fillSelect, bindSlider,
};
