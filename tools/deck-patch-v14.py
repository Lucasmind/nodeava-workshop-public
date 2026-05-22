#!/usr/bin/env python3
"""
v13 → v14 deck patcher.

Spec from instructor:
  * Slides 13/14/15 are out of order: currently Lab1, Lab3, Lab2.
    Swap 14 ↔ 15 so the order is Lab1, Lab2, Lab3.
  * Slides 16-19 don't align with labs 4/5/6. Rewrite:
      - slide 16 → Lab 4 (Orchestrator / Nervous System)
      - slide 17 → Lab 5 (Tools / Hands)
      - slide 18 → Lab 6 (Pipeline / Whole Body)
      - slide 19 → transition slide leading to slide 20 ("Run the full
        digital human loop" — the avatar payoff)
  * Drop slide 21 ("Drive the avatar from generated speech") — redundant
    with the digital-human-loop slide right before it.

Pattern matches deck-patch-v13.py: list-of-sections rewrite, then
renumber data-slide + eyebrow .num sequentially.

Run:   python3 tools/deck-patch-v14.py
Reads: /home/rob/Downloads/NodeAvaWorkshopDeck_v13.html
Writes: /home/rob/Downloads/NodeAvaWorkshopDeck_v14.html
"""
from __future__ import annotations
import base64
import re
import sys
from pathlib import Path


SRC = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v13.html')
DST = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v14.html')
SHOT_DIR = Path('/home/rob/.claude/jobs/a5d283ca/deck-screenshots')


def b64_img(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode('ascii')


def make_lab_slide(
    *,
    slide_num: int,
    eyebrow_num: int,
    demo_label: str,
    title: str,
    lab_path: str,
    runbook_steps: list[str],
    teaching_point: str,
    screenshot_b64: str,
    speaker_notes: str = '',
) -> str:
    """Build a lab-aligned slide matching the deck-13 template."""
    steps_html = '\n'.join(
        f'<div class="step">{s}</div>'
        for s in runbook_steps
    )
    notes_attr = speaker_notes.replace('"', '&quot;')
    return (
        f'<section class="slide" data-notes="{notes_attr}" data-slide="{slide_num}">\n'
        f'<div class="eyebrow"><span class="num">{eyebrow_num}</span>{demo_label}</div>\n'
        f'<h2>{title}  <span style="font-size:0.5em;color:#888;">· {lab_path}</span></h2>\n'
        f'<div class="lab-grid">\n'
        f'<div class="lab-left"><div class="lab-card teach"><div class="lab-label">Runbook</div>'
        f'<div class="steps">{steps_html}</div>'
        f'<div class="learn-box"><b>Teaching point:</b> {teaching_point}</div></div></div>\n'
        f'<div class="lab-right"><div class="terminal teach" style="padding:0;overflow:hidden;">'
        f'<div class="bar">http://localhost:3000{lab_path}.html</div>'
        f'<img src="data:image/png;base64,{screenshot_b64}" alt="{lab_path}" '
        f'style="display:block;width:100%;height:auto;background:#0d1117;">'
        f'</div></div>\n'
        f'</div>\n'
        f'</section>'
    )


def make_transition_slide(*, slide_num: int, eyebrow_num: int) -> str:
    """Replaces slide 19 — the bridge between organ tests and the full avatar."""
    return (
        f'<section class="slide" data-notes="&lt;p&gt;You\'ve tested every organ in isolation. Now we put them together — speech in, transcribed text, reasoning, spoken reply, lip-synced face. This is the moment everything earlier in the workshop has been pointing at.&lt;/p&gt;" data-slide="{slide_num}">\n'
        f'<div class="eyebrow"><span class="num">{eyebrow_num}</span>Assembly</div>\n'
        f'<h2>From six organs to one digital human</h2>\n'
        f'<p class="lede" style="margin-top:1.2rem;">You\'ve tested every organ in isolation. The dashboard takes the same six pieces and runs them as one continuous loop: <b>your voice</b> → STT → orchestrator (with personality, tools, memory) → LLM → TTS → avatar mouth + face.</p>\n'
        f'<div style="margin-top:1.6rem;display:grid;grid-template-columns:repeat(6, 1fr);gap:0.6rem;max-width:1000px;font-size:0.88em;">\n'
        f'  <div style="text-align:center;padding:0.9rem 0.4rem;border:1px solid #30363d;border-radius:8px;background:#161b22;"><div style="color:#58a6ff;font-size:0.72em;letter-spacing:.1em;text-transform:uppercase;">Lab 1</div><div style="margin-top:.3rem;font-weight:600;">Brain</div></div>\n'
        f'  <div style="text-align:center;padding:0.9rem 0.4rem;border:1px solid #30363d;border-radius:8px;background:#161b22;"><div style="color:#58a6ff;font-size:0.72em;letter-spacing:.1em;text-transform:uppercase;">Lab 2</div><div style="margin-top:.3rem;font-weight:600;">Ears</div></div>\n'
        f'  <div style="text-align:center;padding:0.9rem 0.4rem;border:1px solid #30363d;border-radius:8px;background:#161b22;"><div style="color:#58a6ff;font-size:0.72em;letter-spacing:.1em;text-transform:uppercase;">Lab 3</div><div style="margin-top:.3rem;font-weight:600;">Voice</div></div>\n'
        f'  <div style="text-align:center;padding:0.9rem 0.4rem;border:1px solid #30363d;border-radius:8px;background:#161b22;"><div style="color:#58a6ff;font-size:0.72em;letter-spacing:.1em;text-transform:uppercase;">Lab 4</div><div style="margin-top:.3rem;font-weight:600;">Nerves</div></div>\n'
        f'  <div style="text-align:center;padding:0.9rem 0.4rem;border:1px solid #30363d;border-radius:8px;background:#161b22;"><div style="color:#58a6ff;font-size:0.72em;letter-spacing:.1em;text-transform:uppercase;">Lab 5</div><div style="margin-top:.3rem;font-weight:600;">Hands</div></div>\n'
        f'  <div style="text-align:center;padding:0.9rem 0.4rem;border:1px solid #30363d;border-radius:8px;background:#161b22;"><div style="color:#58a6ff;font-size:0.72em;letter-spacing:.1em;text-transform:uppercase;">Lab 6</div><div style="margin-top:.3rem;font-weight:600;">Body</div></div>\n'
        f'</div>\n'
        f'<p style="margin-top:1.4rem;font-size:0.96em;color:#9aa8b8;">All six were running the whole time. The dashboard at <code>localhost:3000</code> just <i>uses</i> them — exactly the same containers and host services that powered every lab — with one addition: the avatar at the front and the streaming chunker that hands text to TTS sentence-by-sentence so audio starts before the LLM finishes thinking.</p>\n'
        f'<p style="margin-top:1.0rem;font-size:1.05em;color:#e6edf3;"><b>Next slide:</b> open the dashboard. Use your voice. Meet Ava.</p>\n'
        f'</section>'
    )


def renumber_slide(slide_html: str, new_data_slide: int, new_eyebrow: int) -> str:
    out = re.sub(r'data-slide="[\d.]+"', f'data-slide="{new_data_slide}"', slide_html, count=1)
    out = re.sub(r'<span class="num">[\d]+</span>', f'<span class="num">{new_eyebrow}</span>', out, count=1)
    return out


def main() -> int:
    if not SRC.exists():
        print(f'ERROR: source deck not found at {SRC}', file=sys.stderr)
        return 2

    html = SRC.read_text(encoding='utf-8')
    pat = re.compile(
        r'<section class="slide[^"]*"[^>]*data-slide="([\d.]+)"[^>]*>.*?</section>',
        re.DOTALL,
    )
    matches = list(pat.finditer(html))
    if not matches:
        print('ERROR: no slide sections found', file=sys.stderr)
        return 1

    slide_map: dict[str, str] = {}
    for m in matches:
        ds = re.search(r'data-slide="([\d.]+)"', m.group(0)).group(1)
        slide_map[ds] = m.group(0)
    print(f'  parsed {len(slide_map)} slides from v13')

    # ── Step 1: swap slide 14 ↔ 15 so the demo order is Lab1, Lab2, Lab3 ────
    if '14' in slide_map and '15' in slide_map:
        slide_map['14'], slide_map['15'] = slide_map['15'], slide_map['14']
        print('  ✓ swapped slides 14 ↔ 15 (now Lab1, Lab2, Lab3 in order)')

    # ── Step 2: rewrite slides 16, 17, 18 as labs 4, 5, 6 ────────────────────
    shot_04 = b64_img(SHOT_DIR / 'lab-04-orchestrator.png')
    shot_05 = b64_img(SHOT_DIR / 'lab-05-tools.png')
    shot_06 = b64_img(SHOT_DIR / 'lab-06-pipeline.png')

    slide_map['16'] = make_lab_slide(
        slide_num=16, eyebrow_num=15,
        demo_label='Demo 04 · Nervous system',
        title='Swap the personality, watch the brain change',
        lab_path='/lab/04-orchestrator',
        runbook_steps=[
            '<b>Open:</b> <code>http://localhost:3000/lab/04-orchestrator.html</code>',
            '<b>Send a message</b> (try "Tell me one interesting fact about clocks") and read the reply.',
            '<b>Open the personality dropdown</b> — pick a different one (try <i>dry-historian</i> or <i>improv-comic</i>). The active <i>system prompt</i> updates on screen.',
            '<b>Send the same message again.</b> Same model, same temperature, same tokens — radically different tone.',
        ],
        teaching_point='The model is bytes; the personality is the program. The system prompt is where the most expressive engineering happens — and it\'s a few hundred words of plain English.',
        screenshot_b64=shot_04,
        speaker_notes='&lt;p&gt;This is the slide where attendees go &quot;oh — that&apos;s how it works&quot;. Read the active system prompt aloud before they pick a new personality. The contrast lands harder when they hear the old prompt first.&lt;/p&gt;',
    )

    slide_map['17'] = make_lab_slide(
        slide_num=17, eyebrow_num=16,
        demo_label='Demo 05 · Hands',
        title='The agentic loop — wiki recall and live web search',
        lab_path='/lab/05-tools',
        runbook_steps=[
            '<b>Open:</b> <code>http://localhost:3000/lab/05-tools.html</code>',
            '<b>Both toggles off.</b> Ask "What is NodeAva?" — the model guesses from training data.',
            '<b>Flip wiki on, ask again.</b> Watch the round-by-round panel: model emits <code>wiki.search</code>, orchestrator runs it, results fed back, grounded answer.',
            '<b>Flip web search on, ask a current-events question.</b> Same loop, different tool family.',
            '<b>Try the force-tool checkbox.</b> Small models (4B) skip tools on confident-feeling questions; the toggle prepends a directive that forces the reach.',
        ],
        teaching_point='Tool use turns the avatar from a chatty model into an operator. Watch the rounds chip — sometimes the loop spins; this is where small-model brittleness lives, and it\'s a teachable moment, not a bug.',
        screenshot_b64=shot_05,
        speaker_notes='&lt;p&gt;The round-by-round panel is the point — attendees should SEE the model decide to reach for a tool, the orchestrator execute it, and the results feed back. If a tool call goes sideways (model misnames the tool or loops), don&apos;t fix it — that&apos;s the &quot;prompt is the program&quot; lesson surfacing live.&lt;/p&gt;',
    )

    slide_map['18'] = make_lab_slide(
        slide_num=18, eyebrow_num=17,
        demo_label='Demo 06 · Whole body',
        title='Voice in, voice out — the latency budget',
        lab_path='/lab/06-pipeline',
        runbook_steps=[
            '<b>Open:</b> <code>http://localhost:3000/lab/06-pipeline.html</code>',
            '<b>Click Record, speak a question, click Stop.</b> Or use the text-input toggle if there\'s a mic problem.',
            '<b>Watch the four stage chips light up:</b> STT → LLM → TTS → total.',
            '<b>Read the timing:</b> STT ~200 ms · LLM ~1.5 s · TTS ~600 ms → total ~2.5 s. That feels conversational. Above ~4 s it feels like a walkie-talkie.',
        ],
        teaching_point='This lab is sequential on purpose — each stage waits for the previous one. The real app overlaps them with streaming + sentence chunking. That overlap is the difference between "feels alive" and "feels broken".',
        screenshot_b64=shot_06,
        speaker_notes='&lt;p&gt;This is the budget slide. Quote the rough numbers (~2.5s end-to-end is conversational, ~4s is uncanny, ~7s and people ask if it&apos;s broken). The next slide shows what happens when you streaming-overlap these stages — the dashboard runs ahead, audio starts before reasoning finishes.&lt;/p&gt;',
    )

    print('  ✓ rewrote slides 16, 17, 18 → labs 4, 5, 6 with live screenshots')

    # ── Step 3: replace slide 19 with the transition slide ────────────────────
    slide_map['19'] = make_transition_slide(slide_num=19, eyebrow_num=18)
    print('  ✓ slide 19 → transition slide ("From six organs to one digital human")')

    # ── Step 4: drop slide 21 ────────────────────────────────────────────────
    # In v13: slide 21 = "Drive the avatar from generated speech".
    if '21' in slide_map:
        del slide_map['21']
        print('  ✓ dropped slide 21 (Drive the avatar from generated speech)')

    # ── Step 5: rebuild + renumber sequentially ───────────────────────────────
    surviving_ids = sorted(slide_map.keys(), key=lambda s: float(s))
    final_sections: list[str] = []
    for i, sid in enumerate(surviving_ids, start=1):
        final_sections.append(
            renumber_slide(slide_map[sid], new_data_slide=i, new_eyebrow=i - 1)
        )
    print(f'  ✓ renumbered {len(final_sections)} slides sequentially')

    first_start = matches[0].start()
    last_end = matches[-1].end()
    out_html = html[:first_start] + '\n'.join(final_sections) + html[last_end:]

    DST.write_text(out_html, encoding='utf-8')
    print()
    print(f'  ✓ wrote {DST}  ({len(out_html):,} bytes; was {len(html):,})')
    print(f'  ✓ slide count: {len(final_sections)}  (was {len(matches)})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
