#!/usr/bin/env python3
"""
Plan #10 deck-reconciliation patcher.

Reads NodeAvaWorkshopDeck_v10_slide2_wording.html, applies the inline edits
documented in docs/deck-reconciliation-2026-05-18.md, inserts the new
"The prompt is the program" slide between current slides 32 and 33, and
emits NodeAvaWorkshopDeck_v11.html alongside.

Pure-string operations against the source HTML so we don't perturb the
embedded base64 images or layout.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


SRC = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v10_slide2_wording.html')
DST = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v11.html')
ASSETS_DIR = 'NodeAvaWorkshopDeck_v10_assets'  # relative to deck


# (find, replace) — applied as plain string replace (no regex).
# Each tuple has an optional `note` for the patch log.
PATCHES = [
    # --- Slide 11 (Inspecting components) — script-name reality check ---
    (
        '<span class="cmd">00-preflight.sh</span>          prove the machine is ready\n'
        '<span class="cmd">01-brain-local-llm.sh</span>   prove the cognition layer works\n'
        '<span class="cmd">02-voice-tts.sh</span>         prove speech generation works\n'
        '<span class="cmd">03-ears-stt-file.sh</span>     prove transcription works\n'
        '<span class="cmd">08-latency-trace.sh</span>     prove we can see where time goes\n'
        '<span class="cmd">10-full-digital-human.sh</span> prove the loop is assembled',
        '<span class="cmd">./install.sh</span>             9-step idempotent wizard (preflight, install, models, stack)\n'
        '<span class="cmd">scripts/demos/test-llm.sh</span>        prove the cognition layer works\n'
        '<span class="cmd">scripts/demos/test-tts.sh</span>        prove speech generation works\n'
        '<span class="cmd">scripts/demos/test-stt.sh</span> WAV    prove transcription works on a known file\n'
        '<span class="cmd">scripts/demos/test-pipeline.sh</span>   end-to-end orchestrator + agentic loop\n'
        '<span class="cmd">scripts/demos/test-orchestrator.sh</span> brain selection + tool dispatch\n'
        'Browser at <span class="cmd">http://localhost:3000</span>    full digital human (mic, drawer, flow diagram)',
        'slide 11: replace planned numbered harness with shipped script set',
    ),

    # --- Slide 12 (Preflight) — port fixes + remove "../nodeava" relpath ---
    (
        '<b>Go to the workshop repo:</b><br/><code>cd ~/nodeava-workshop</code>',
        '<b>Clone the workshop kit:</b><br/><code>git clone https://github.com/Lucasmind/nodeava-workshop.git ~/nodeava-workshop &amp;&amp; cd ~/nodeava-workshop</code>',
        'slide 12: clone instead of cd-into-existing',
    ),
    (
        '<b>Point it at NodeAva:</b><br/><code>export NODEAVA_HOME=../nodeava</code>',
        '<b>Run the installer wizard:</b><br/><code>./install.sh</code>',
        'slide 12: integrated installer replaces NODEAVA_HOME env var',
    ),
    (
        '<b>Run preflight:</b><br/><code>./scripts/00-preflight.sh</code>',
        '<b>The wizard runs preflight as step 2:</b><br/><code>platform · GPU · Docker · disk · network · ports</code>',
        'slide 12: preflight is an installer step, not a separate script',
    ),
    (
        '<code>./scripts/00-preflight.sh --verbose</code><code>./scripts/00-preflight.sh --offline</code>',
        '<code>./install.sh --full-reset</code><code>NODEAVA_LLM_BACKEND=llama-cpp ./install.sh</code>',
        'slide 12: replace fake --verbose/--offline with real installer flags',
    ),
    (
        'llama.cpp:          <span class="ok">OK</span>',
        'Ollama (host):      <span class="ok">OK</span>',
        'slide 12: default LLM backend is Ollama (Plan #7)',
    ),
    (
        'Whisper:            <span class="ok">OK</span> <span class="copy-wrap"><span class="copy-text">http://localhost:8178</span><button class="copy-btn" type="button" title="Copy" aria-label="Copy http://localhost:8178" data-copy="http://localhost:8178">',
        'Whisper:            <span class="ok">OK</span> <span class="copy-wrap"><span class="copy-text">http://localhost:8080</span><button class="copy-btn" type="button" title="Copy" aria-label="Copy http://localhost:8080" data-copy="http://localhost:8080">',
        'slide 12: Whisper is on 8080, not 8178',
    ),
    (
        'aria-label="Copy http://localhost:8178" data-copy="http://localhost:8178">',
        'aria-label="Copy http://localhost:8080" data-copy="http://localhost:8080">',
        'slide 12: aria-label port fix (companion to copy-text)',
    ),
    (
        '<span class="copy-text">http://localhost:8080</span><button class="copy-btn" type="button" title="Copy" aria-label="Copy http://localhost:8080" data-copy="http://localhost:8080"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M5 15V7a2 2 0 0 1 2-2h8"></path></svg></button></span>\nKokoro TTS:',
        '<span class="copy-text">http://localhost:11434</span><button class="copy-btn" type="button" title="Copy" aria-label="Copy http://localhost:11434" data-copy="http://localhost:11434"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M5 15V7a2 2 0 0 1 2-2h8"></path></svg></button></span>\nKokoro TTS:',
        'slide 12: Ollama is on 11434 (was the first 8080 occurrence which collided with STT)',
    ),

    # --- Slide 13 (Test local LLM) — script + backend default ---
    (
        '<b>Stay in:</b> <code>nodeava-workshop</code></div>\n'
        '<div class="step"><b>Run the local LLM probe:</b><br/><code>./scripts/01-brain-local-llm.sh</code></div>',
        '<b>Stay in:</b> <code>nodeava-workshop</code></div>\n'
        '<div class="step"><b>Run the local LLM probe:</b><br/><code>./scripts/demos/test-llm.sh</code></div>',
        'slide 13: rename script',
    ),
    (
        '<code>./scripts/01-brain-local-llm.sh "Explain this like I am 12."</code><code>./scripts/01-brain-local-llm.sh --json</code>',
        '<code>./scripts/demos/test-llm.sh "Explain this like I am 12."</code><code>./scripts/demos/list-models.sh</code>',
        'slide 13: replace fake --json with real list-models companion script',
    ),
    (
        './workshop/scripts/01-brain-local-llm.sh</div><pre><span class="cmd">Prompt:</span> Explain what a digital human is in one sentence.\n'
        '\n'
        '<span class="key">Backend:</span> llama.cpp\n'
        '<span class="key">Model:</span>   Qwen3-4B',
        './scripts/demos/test-llm.sh</div><pre><span class="cmd">Prompt:</span> Explain what a digital human is in one sentence.\n'
        '\n'
        '<span class="key">Backend:</span> Ollama (host:11434) via nodeava-orch\n'
        '<span class="key">Model:</span>   qwen3:4b-instruct',
        'slide 13: terminal mock — Ollama default + qwen3:4b-instruct model id',
    ),

    # --- Slide 14 (TTS) — script rename + drop fake --voice flag ---
    (
        '<b>Run the TTS probe:</b><br/><code>./scripts/02-voice-tts.sh</code></div>',
        '<b>Run the TTS probe:</b><br/><code>./scripts/demos/test-tts.sh</code></div>',
        'slide 14: rename script',
    ),
    (
        '<code>./scripts/02-voice-tts.sh "Same words, new delivery."</code><code>./scripts/14-swap-voice.sh calm &amp;&amp; ./scripts/02-voice-tts.sh</code>',
        '<code>./scripts/demos/test-tts.sh "Same words, new delivery." am_fenrir</code><code>curl -X POST http://localhost:8082/v1/swap -d \'{"kind":"voice","id":"fenrir"}\'</code>',
        'slide 14: real test-tts.sh takes voice as 2nd positional arg; voice swap is /v1/swap not a flag',
    ),
    (
        './workshop/scripts/02-voice-tts.sh',
        './scripts/demos/test-tts.sh',
        'slide 14: terminal bar label',
    ),

    # --- Slide 15 (STT file) — script rename + drop fake --model flag ---
    (
        '<b>Run STT from file:</b><br/><code>./scripts/03-ears-stt-file.sh samples/what-is-nodeava.wav</code></div>',
        '<b>Run STT from file:</b><br/><code>./scripts/demos/test-stt.sh samples/what-is-nodeava.wav</code></div>',
        'slide 15: rename script',
    ),
    (
        '<code>./scripts/03-ears-stt-file.sh samples/introduce-yourself.wav</code><code>./scripts/03-ears-stt-file.sh --model base.en samples/noisy-room.wav</code>',
        '<code>./scripts/demos/test-stt.sh samples/introduce-yourself.wav</code><code>./scripts/demos/test-stt.sh samples/noisy-room.wav</code>',
        'slide 15: drop fake --model flag (whisper model is hardcoded in compose)',
    ),
    (
        './workshop/scripts/03-ears-stt-file.sh',
        './scripts/demos/test-stt.sh',
        'slide 15: terminal bar label',
    ),

    # --- Slide 16 (Live mic + turn detection) — point at the browser, not a CLI ---
    (
        '<b>Run live mic once:</b><br/><code>./scripts/04-ears-stt-mic.sh</code></div>\n'
        '<div class="step"><b>Say the test phrase:</b><br/><code>What is NodeAva?</code></div>\n'
        '<div class="step"><b>Watch the states:</b> idle → speech started → silence window → endpoint → transcript.</div>\n'
        '<div class="step"><b>Tune if needed:</b> too jumpy = raise silence window; too slow = lower it.</div>',
        '<b>Live mic happens in the browser:</b><br/><code>http://localhost:3000</code> · click <code>🎤 Mic</code></div>\n'
        '<div class="step"><b>Say the test phrase:</b><br/><code>What is NodeAva?</code></div>\n'
        '<div class="step"><b>Watch the FlowDiagram lanes:</b> mic → stt → llm → tool → tts → avatar (each with timing chip).</div>\n'
        '<div class="step"><b>900&nbsp;ms VAD grace:</b> clicking Mic-Off keeps VAD running briefly so an in-progress utterance still transcribes.</div>',
        'slide 16: live mic is in the browser; FlowDiagram is the state visualization',
    ),
    (
        './workshop/scripts/04-ears-stt-mic.sh --show-vad',
        'in-browser VAD state (Silero) — frontend/src/stt/STTManager.js',
        'slide 16: terminal bar label points to real code path',
    ),

    # --- Slide 17 (STT → LLM) — point at the running orchestrator ---
    (
        '<b>Run STT → LLM:</b><br/><code>./scripts/05-ears-to-brain.sh samples/what-is-nodeava.wav</code></div>\n'
        '<div class="step"><b>Observe:</b> transcript becomes the prompt.</div>',
        '<b>Test the orchestrator end-to-end:</b><br/><code>./scripts/demos/test-orchestrator.sh</code></div>\n'
        '<div class="step"><b>Observe:</b> transcript becomes the prompt; orchestrator picks Ollama/Claude/etc. per catalog.</div>',
        'slide 17: real path is test-orchestrator.sh + automatic provider dispatch',
    ),
    (
        '<code>./scripts/05-ears-to-brain.sh samples/ask-about-latency.wav</code><code>./scripts/05-ears-to-brain.sh --show-prompt samples/what-is-nodeava.wav</code>',
        '<code>./scripts/demos/test-orchestrator.sh "What is NodeAva?"</code><code>curl -s http://localhost:8082/v1/state | jq .active</code>',
        'slide 17: replace fake flag with real /v1/state introspection',
    ),
    (
        './workshop/scripts/05-ears-to-brain.sh samples/what-is-nodeava.wav',
        './scripts/demos/test-orchestrator.sh "What is NodeAva?"',
        'slide 17: terminal bar label',
    ),

    # --- Slide 18 (LLM → TTS) — pipeline test ---
    (
        '<b>Run LLM → TTS:</b><br/><code>./scripts/06-brain-to-voice.sh</code></div>',
        '<b>Run the integrated pipeline test:</b><br/><code>./scripts/demos/test-pipeline.sh</code></div>',
        'slide 18: pipeline test runs the end-to-end agentic loop',
    ),
    (
        '<code>./scripts/06-brain-to-voice.sh --chunk sentence</code><code>./scripts/06-brain-to-voice.sh --chunk 40chars</code>',
        '<code>./scripts/demos/test-pipeline.sh "Introduce yourself."</code><code>Open the browser — the FlowDiagram shows the streaming chunker live.</code>',
        'slide 18: chunk-size flag is not a thing; show real streaming in browser',
    ),
    (
        './workshop/scripts/06-brain-to-voice.sh',
        './scripts/demos/test-pipeline.sh',
        'slide 18: terminal bar label',
    ),

    # --- Slide 19 (Full voice loop) — open the browser ---
    (
        '<b>Run the full voice loop:</b><br/><code>./scripts/07-full-voice-loop.sh</code></div>',
        '<b>Open the browser:</b><br/><code>http://localhost:3000</code></div>',
        'slide 19: full voice loop is the running frontend',
    ),
    (
        '<code>./scripts/07-full-voice-loop.sh --push-to-talk</code><code>./scripts/07-full-voice-loop.sh --no-stream</code>',
        '<code>Press <kbd>]</kbd> to open the drawer</code><code>Click 🎤 Mic to start listening (click again to stop)</code>',
        'slide 19: real flags are keyboard shortcuts in the browser',
    ),
    (
        './workshop/scripts/07-full-voice-loop.sh --once',
        'http://localhost:3000 — dashboard FlowDiagram',
        'slide 19: terminal bar label points at the dashboard',
    ),

    # --- Slide 20 (Latency trace) — FlowDiagram chips replace standalone script ---
    (
        '<b>Run trace mode:</b><br/><code>./scripts/08-latency-trace.sh</code></div>',
        '<b>Open the drawer and run a turn:</b><br/><code>FlowDiagram chips populate per stage</code></div>',
        'slide 20: latency trace is in-browser via the FlowDiagram timing chips',
    ),
    (
        '<code>./scripts/08-latency-trace.sh --cold</code><code>./scripts/08-latency-trace.sh --compare streaming,no-stream</code>',
        '<code>Swap brains and re-ask to compare cold vs warm</code><code>Run the benchmark button for explicit comparison rows</code>',
        'slide 20: cold-vs-warm is a swap; explicit comparison is the benchmark widget',
    ),
    (
        './workshop/scripts/08-latency-trace.sh',
        'in-browser FlowDiagram + EventLog',
        'slide 20: terminal bar label',
    ),

    # --- Slide 21 (Streaming) — drop fake --no-stream flag ---
    (
        '<code>./scripts/08-latency-trace.sh --no-stream</code><code>./scripts/08-latency-trace.sh --stream</code>',
        '<code>Swap brain: qwen3-4b-thinking (always reasons → slow first token)</code><code>Swap brain: qwen3-4b-instruct (default, streams immediately)</code>',
        'slide 21: thinking-vs-instruct brain swap is the real comparison',
    ),

    # --- Slide 22 (Avatar say) — drop fake --voice / --avatar CLI flags ---
    (
        '<b>Run avatar-only speech:</b><br/><code>./scripts/09-avatar-say.sh "Hello, my voice is driving my face."</code></div>',
        '<b>Use the chat input in the browser:</b><br/><code>Type a sentence and press Send — the FlowDiagram shows tts → avatar timing.</code></div>',
        'slide 22: avatar-say is implicit in the running pipeline',
    ),
    (
        '<code>./scripts/09-avatar-say.sh --voice calm "Same words, different presence."</code><code>./scripts/09-avatar-say.sh --avatar ava2.glb "New face, same voice."</code>',
        '<code>Swap voice from the drawer: Bella → Fenrir (M, US)</code><code>Swap avatar: Mike (photoreal M, MIT) or Yui (anime F)</code>',
        'slide 22: avatar/voice swap is the dashboard',
    ),
    (
        './workshop/scripts/09-avatar-say.sh',
        'in-browser chat input → tts → avatar',
        'slide 22: terminal bar label',
    ),

    # --- Slide 23 (Full digital human) — open browser + walkthrough ---
    (
        '<b>Open the visualizer:</b><br/><code><span class="copy-wrap"><span class="copy-text">http://localhost:3000/workshop</span><button class="copy-btn" type="button" title="Copy" aria-label="Copy http://localhost:3000/workshop" data-copy="http://localhost:3000/workshop">',
        '<b>Open the browser:</b><br/><code><span class="copy-wrap"><span class="copy-text">http://localhost:3000</span><button class="copy-btn" type="button" title="Copy" aria-label="Copy http://localhost:3000" data-copy="http://localhost:3000">',
        'slide 23: no /workshop path — root URL serves the digital human',
    ),
    (
        '<b>Run full avatar loop:</b><br/><code>./scripts/10-full-digital-human.sh</code></div>',
        '<b>First-time visit: 7-step spotlight walkthrough auto-starts. Click <code>?</code> to re-run.</b></div>',
        'slide 23: full digital human is opening the browser; walkthrough fires on first load',
    ),
    (
        '<code>./scripts/10-full-digital-human.sh --show-events</code><code>./scripts/10-full-digital-human.sh --preset tutor</code>',
        '<code>Open the EventLog in the drawer (live typed events)</code><code>Swap personality: Patient Tutor (built-in catalog entry)</code>',
        'slide 23: events are in the drawer; presets are catalog entries',
    ),
    (
        './workshop/scripts/10-full-digital-human.sh --visualizer',
        'http://localhost:3000 — full dashboard',
        'slide 23: terminal bar label',
    ),

    # --- Slide 27 (Wiki structure) — match Plan #6 sub-organized layout ---
    (
        '<div class="bar">wiki/</div><pre>index.md\n'
        'architecture.md\n'
        'install.md\n'
        'troubleshooting.md\n'
        'personality.md\n'
        'workshop.md</pre>',
        '<div class="bar">wiki/  (20 pages, Karpathy-style LLM-maintained)</div><pre>concepts/\n'
        '  pipeline-orchestrator.md\n'
        '  agentic-loop.md\n'
        '  avatar-rendering.md\n'
        '  ...(8 more concept pages)\n'
        'entities/\n'
        '  nodeava.md, qwen3.md, kokoro.md, whisper.md, talkinghead.md\n'
        'faqs/\n'
        '  what-is-nodeava.md, how-do-i-X.md, ...(3 more FAQ pages)\n'
        '<span class="key">Compiled by:</span> services/wiki-compiler/compile_wiki.py (one-shot, with Sonnet)</pre>',
        'slide 27: real wiki has 20 pages in 3 subdirs (Plan #6)',
    ),

    # --- Slide 28 (Tool trace) — fix script name ---
    (
        './workshop/scripts/11-wiki-knowledge.sh "What is NodeAva?"',
        'In-browser: 📚 Wiki toggle ON, ask &ldquo;What is NodeAva?&rdquo;',
        'slide 28: wiki tool fires from the browser; verbal filler "Let me look that up" announces it',
    ),

    # --- Slide 29 (Drop in docs) — real ingest path ---
    (
        './workshop/scripts/12-drop-in-docs.sh samples/docs/my-facts.md',
        'curl -X POST http://localhost:8082/v1/ingest -F file=@my-facts.md',
        'slide 29: real ingest is /v1/ingest (multipart upload to orchestrator)',
    ),
    (
        'Copied document into wiki/custom/\n'
        'Updated index.\n'
        'Reloaded orchestrator knowledge view.',
        '{"file": "my-facts.md", "pages_changed": ["concepts/my-facts.md"]}\n'
        '(orchestrator invokes wiki-compiler with the upload + ANTHROPIC_API_KEY)',
        'slide 29: actual ingest response from /v1/ingest',
    ),
]


# Inline-screenshot inserts. Key: marker string in source HTML. Value: HTML
# block to inject AFTER the marker (just before the closing tag of the slide).
SCREENSHOT_INSERTS = [
    # Slide 20 — show the FlowDiagram with chips
    (
        '<b>Teaching point:</b> users do not feel averages.',
        # nothing — we'll insert the img into the right-side terminal block of the slide
        None,
    ),
]


# --- The new slide 32½: "The prompt is the program" ---
# Inserted RIGHT BEFORE the existing slide with `data-slide="33"`.
PROMPT_ENG_SLIDE = '''<section class="slide" data-notes="&lt;p&gt;Live findings from building Plan #8 — 7 places small instruct models stumble on tool use and prompt-following. Show 4 of them as a teaching moment between provider-swap and customize-it.&lt;/p&gt;" data-slide="32.5">
<div class="eyebrow"><span class="num">31.5</span>The prompt is the program</div>
<h2>How a 4B local model actually behaves</h2>
<p class="lede" style="margin-top:.8rem;max-width:82ch;">Reliable tool use is not free with a small model. Here are the four most useful failure modes we hit while building NodeAva &mdash; each one is a workshop moment.</p>
<div class="demo-grid" style="margin-top:1.5rem;">
  <div class="demo-card"><div class="label">Pitfall 1</div><div class="title">Two system prompts confuse the model</div><div class="desc">Frontend was sending its own legacy system prompt while the orchestrator injected the catalog personality. The longer one won; wiki-priming was ignored.<br/><b>Fix:</b> single source of truth &mdash; orchestrator owns the personality.</div></div>
  <div class="demo-card"><div class="label">Pitfall 2</div><div class="title">Word-level priming sensitivity</div><div class="desc">&ldquo;Search the web for X&rdquo; fires the tool. &ldquo;Can you search X?&rdquo; sometimes refuses with &ldquo;I can&rsquo;t access real-time data&rdquo;.<br/><b>Fix:</b> trigger-map table + anti-patterns in the personality prompt.</div></div>
  <div class="demo-card"><div class="label">Pitfall 3</div><div class="title">The narration trap</div><div class="desc">Small instruct models often say &ldquo;Let me look that up&rdquo; &mdash; then stop. They narrated the intent and consider the task done.<br/><b>Fix:</b> forbid narration in the prompt + the system speaks the verbal filler when the tool actually fires.</div></div>
  <div class="demo-card"><div class="label">Pitfall 4</div><div class="title">STT artifacts feed back</div><div class="desc">Whisper transcribes &ldquo;NodeAva&rdquo; as &ldquo;Node Ava&rdquo; (two words). A naive regex search returns zero hits.<br/><b>Fix:</b> whitespace-flex regex + per-word matching in wiki.search; the personality prompt acknowledges the transcription quirk.</div></div>
</div>
<div class="presence-note" style="margin-top:1.2rem;"><b>Teaching point:</b> the prompt is the program. With a 4B-class model, behavior is shaped at the system-prompt level, not by the model&rsquo;s capability ceiling.</div>
</section>
'''


def patch():
    if not SRC.exists():
        sys.exit(f"source not found: {SRC}")
    text = SRC.read_text()
    original_len = len(text)
    print(f"loaded {original_len:,} chars ({original_len/1024/1024:.1f} MB)")
    print()

    applied = 0
    missed = 0
    for find, replace, note in PATCHES:
        if find in text:
            text = text.replace(find, replace)
            print(f"  ✓ {note}")
            applied += 1
        else:
            print(f"  ✗ MISS: {note}")
            print(f"     (find string was {len(find)} chars; first 80: {find[:80]!r})")
            missed += 1

    # Insert the new prompt-eng slide before <section ... data-slide="33">
    slide33_marker = '<section class="slide" data-notes='
    # find the slide-33 occurrence
    idx_33 = text.find('data-slide="33"')
    if idx_33 < 0:
        print("  ✗ MISS: could not locate slide 33 anchor — prompt-eng slide NOT inserted")
        missed += 1
    else:
        # walk back to the opening <section ... that contains data-slide="33"
        sect_start = text.rfind('<section class="slide"', 0, idx_33)
        if sect_start < 0:
            print("  ✗ MISS: could not locate <section> opening for slide 33")
            missed += 1
        else:
            text = text[:sect_start] + PROMPT_ENG_SLIDE + text[sect_start:]
            print(f"  ✓ inserted 'The prompt is the program' slide as 32.5 (before slide 33)")
            applied += 1

    new_len = len(text)
    print()
    print(f"summary: {applied} applied, {missed} missed")
    print(f"file:    {original_len:,} → {new_len:,} chars (delta {new_len-original_len:+,})")

    DST.write_text(text)
    print(f"wrote:   {DST}")
    return applied, missed


if __name__ == '__main__':
    applied, missed = patch()
    sys.exit(0 if missed == 0 else 2)
