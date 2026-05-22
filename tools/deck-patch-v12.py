#!/usr/bin/env python3
"""
v11 → v12 deck patcher.

Re-ground-truths the testing slides (11, 13–19, 24, 28, 30) to point at
the new in-browser lab pages at /lab/N-{component}.html. Existing CLI
demo scripts stay in the deck as fallback / instructor-side options.

Pure-string operations against the source HTML so we don't perturb the
embedded base64 images or layout.

Run:  python3 tools/deck-patch-v12.py
Reads:  /home/rob/Downloads/NodeAvaWorkshopDeck_v11.html
Writes: /home/rob/Downloads/NodeAvaWorkshopDeck_v12.html
"""
from __future__ import annotations
import sys
from pathlib import Path


SRC = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v11.html')
DST = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v12.html')


# Each patch: (find, replace, description for the log).
# Patches are applied in order; each `find` string must occur EXACTLY ONCE
# in the source (or in the partially-patched output if earlier patches modify it).
PATCHES: list[tuple[str, str, str]] = [
    # ── Slide 11 — Inspecting components ─────────────────────────────
    (
        '<span class="cmd">./install.sh</span>             9-step idempotent wizard (preflight, install, models, stack)\n'
        '<span class="cmd">scripts/demos/test-llm.sh</span>        prove the cognition layer works\n'
        '<span class="cmd">scripts/demos/test-tts.sh</span>        prove speech generation works\n'
        '<span class="cmd">scripts/demos/test-stt.sh</span> WAV    prove transcription works on a known file\n'
        '<span class="cmd">scripts/demos/test-pipeline.sh</span>   end-to-end orchestrator + agentic loop\n'
        '<span class="cmd">scripts/demos/test-orchestrator.sh</span> brain selection + tool dispatch\n'
        'Browser at <span class="cmd">http://localhost:3000</span>    full digital human (mic, drawer, flow diagram)',

        '<span class="cmd">./setup.sh</span>                bootstrap from USB (Docker + Ollama + images)\n'
        '<span class="cmd">./install.sh</span>             9-step wizard (preflight, models, stack up, smoke verify)\n'
        '\n'
        '<span class="cmd">/lab/</span>                     workshop labs · one component per page\n'
        '  <span class="cmd">/lab/01-llm</span>             The Brain     · streaming tokens, TTFT, tok/s\n'
        '  <span class="cmd">/lab/02-stt</span>             The Ears      · mic → WAV → Whisper · RTF\n'
        '  <span class="cmd">/lab/03-tts</span>             The Voice     · Kokoro + word timestamps\n'
        '  <span class="cmd">/lab/04-orchestrator</span>    Nervous System · personality swap\n'
        '  <span class="cmd">/lab/05-tools</span>           The Hands     · wiki + browser, agentic loop\n'
        '  <span class="cmd">/lab/06-pipeline</span>        Whole Body    · full mic→STT→LLM→TTS chain\n'
        '\n'
        'Browser at <span class="cmd">http://localhost:3000</span>    the assembled digital human (mic, drawer, flow diagram)\n'
        'CLI fallback: <span class="cmd">scripts/demos/test-{llm,tts,stt,pipeline,orchestrator}.sh</span>',
        'slide 11: list lab URLs as the primary access method; CLI demoted to fallback',
    ),

    # ── Slide 13 — Test the local LLM ────────────────────────────────
    (
        '<div class="step"><b>Stay in:</b> <code>nodeava-workshop</code></div>\n'
        '<div class="step"><b>Run the local LLM probe:</b><br/><code>./scripts/demos/test-llm.sh</code></div>\n'
        '<div class="step"><b>Watch for:</b> backend, model, first token latency, tokens/sec.</div>\n'
        '<div class="step"><b>Explain:</b> this is cognition only. No ears, no voice, no face.</div></div>',

        '<div class="step"><b>Open the Lab page:</b><br/><code>http://localhost:3000/lab/01-llm.html</code></div>\n'
        '<div class="step"><b>Type a prompt, click <i>Run</i>:</b><br/>watch tokens stream live with TTFT + tok/s chips.</div>\n'
        '<div class="step"><b>Watch for:</b> first-token latency, tokens/sec, total time. Toggle <i>stream</i> off — see how perceived latency differs from total.</div>\n'
        '<div class="step"><b>Explain:</b> this is cognition only. No ears, no voice, no face. CLI fallback: <code>scripts/demos/test-llm.sh</code></div></div>',
        'slide 13: runbook now routes through /lab/01',
    ),

    # ── Slide 14 — Test TTS ──────────────────────────────────────────
    (
        '<div class="step"><b>Run the TTS probe:</b><br/><code>./scripts/demos/test-tts.sh</code></div>\n'
        '<div class="step"><b>Open the artifact:</b><br/><code>workshop/outputs/tts-test.wav</code></div>\n'
        '<div class="step"><b>Listen for:</b> startup delay, clarity, prosody, weird pronunciation.</div>\n'
        '<div class="step"><b>Point out:</b> first audio latency is different from total generation time.</div></div>',

        '<div class="step"><b>Open the Lab page:</b><br/><code>http://localhost:3000/lab/03-tts.html</code></div>\n'
        '<div class="step"><b>Type a sentence, click <i>Speak</i>:</b><br/>hear it spoken; word boxes light up in sync (per-word timestamps are how lip sync works).</div>\n'
        '<div class="step"><b>Listen for:</b> startup delay, clarity, prosody, weird pronunciation. Switch voices — same engine, only the embedding changes.</div>\n'
        '<div class="step"><b>Point out:</b> first-audio latency vs RTF vs total. RTF under 1 means streaming buys time to start playback before synth finishes. CLI fallback: <code>scripts/demos/test-tts.sh</code></div></div>',
        'slide 14: runbook now routes through /lab/03',
    ),

    # ── Slide 15 — Test STT with known audio ─────────────────────────
    (
        '<div class="step"><b>Use a known-good sample first:</b><br/><code>samples/what-is-nodeava.wav</code></div>\n'
        '<div class="step"><b>Run STT from file:</b><br/><code>./scripts/demos/test-stt.sh samples/what-is-nodeava.wav</code></div>\n'
        '<div class="step"><b>Compare:</b> expected transcript vs actual transcript.</div>\n'
        '<div class="step"><b>Only then:</b> move to live mic, where hardware and room noise enter.</div></div>',

        '<div class="step"><b>Open the Lab page:</b><br/><code>http://localhost:3000/lab/02-stt.html</code></div>\n'
        '<div class="step"><b>Click <i>Record</i>, say a sentence, click <i>Stop</i>:</b><br/>captured in-browser, converted to WAV, uploaded to Whisper. Audio length vs decode → RTF chip.</div>\n'
        '<div class="step"><b>Compare:</b> short utterance vs long one. RTF stays roughly constant — the model amortizes its setup cost.</div>\n'
        '<div class="step"><b>Then:</b> try silence. Whisper returns an empty (or hallucinated) transcript — that\'s why <b>endpointing</b> matters in Lab 6. CLI fallback: <code>scripts/demos/test-stt.sh samples/*.wav</code></div></div>',
        'slide 15: runbook now routes through /lab/02 with live mic',
    ),

    # ── Slide 19 — Run the full voice loop ───────────────────────────
    # Has multiple <h2>; identify via the specific runbook text.
    (
        '<h2>Run the full voice loop</h2>',
        '<h2>Run the full voice loop  <span style="font-size:0.5em;color:#888;">· /lab/06-pipeline</span></h2>',
        'slide 19: add lab URL to title',
    ),

    # ── Slide 24 — Why the orchestrator exists ───────────────────────
    (
        '<h2>Why the orchestrator exists</h2>',
        '<h2>Why the orchestrator exists  <span style="font-size:0.5em;color:#888;">· /lab/04-orchestrator</span></h2>',
        'slide 24: add lab URL to title',
    ),

    # ── Slide 28 — Trace a question through a tool call ──────────────
    (
        '<h2>Trace a question through a tool call</h2>',
        '<h2>Trace a question through a tool call  <span style="font-size:0.5em;color:#888;">· /lab/05-tools</span></h2>',
        'slide 28: add lab URL to title',
    ),

    # ── Slide 30 — Use tools to extend ──────────────────────────────
    (
        '<h2>Use tools to extend what the system can do</h2>',
        '<h2>Use tools to extend what the system can do  <span style="font-size:0.5em;color:#888;">· /lab/05-tools</span></h2>',
        'slide 30: add lab URL to title',
    ),

    # ── Slide 13 — Add lab URL to title ──────────────────────────────
    (
        '<h2>Test the local LLM</h2>',
        '<h2>Test the local LLM  <span style="font-size:0.5em;color:#888;">· /lab/01-llm</span></h2>',
        'slide 13: add lab URL to title',
    ),

    # ── Slide 14 — Add lab URL to title ──────────────────────────────
    (
        '<h2>Test text-to-speech</h2>',
        '<h2>Test text-to-speech  <span style="font-size:0.5em;color:#888;">· /lab/03-tts</span></h2>',
        'slide 14: add lab URL to title',
    ),

    # ── Slide 15 — Add lab URL to title ──────────────────────────────
    (
        '<h2>Test speech-to-text with a known audio file</h2>',
        '<h2>Test speech-to-text  <span style="font-size:0.5em;color:#888;">· /lab/02-stt</span></h2>',
        'slide 15: shortened title + add lab URL',
    ),
]


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: source deck not found at {SRC}", file=sys.stderr)
        return 2

    html = SRC.read_text(encoding="utf-8")
    applied = 0
    failed = []

    for find, replace, note in PATCHES:
        count = html.count(find)
        if count == 0:
            failed.append((note, "find string not found"))
            continue
        if count > 1:
            failed.append((note, f"find string occurs {count}× — ambiguous"))
            continue
        html = html.replace(find, replace, 1)
        applied += 1
        print(f"  ✓ {note}")

    if failed:
        print()
        print(f"  ✗ {len(failed)} patches failed:")
        for note, reason in failed:
            print(f"    - {note}  ({reason})")
        print()

    DST.write_text(html, encoding="utf-8")
    print()
    print(f"  applied: {applied}/{len(PATCHES)} patches")
    print(f"  wrote:   {DST}  ({len(html):,} bytes)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
