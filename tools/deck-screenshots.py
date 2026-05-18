#!/usr/bin/env python3
"""
Plan #10 — embed screenshot references into the v11 deck.

Adds <img> blocks to specific slides where a real screenshot beats the
abstract description: latency (slide 20), full digital human (slide 23),
provider/customize (slide 33), and benchmark (slide 34).

Edits NodeAvaWorkshopDeck_v11.html in place.
"""
from __future__ import annotations
from pathlib import Path

DECK = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v11.html')
ASSETS = 'NodeAvaWorkshopDeck_v10_assets'

# Common image style — keeps screenshots from overflowing the slide
IMG_STYLE = (
    'style="max-width: 100%; max-height: 460px; border-radius: 8px; '
    'box-shadow: 0 4px 24px rgba(0,0,0,0.4); margin-top: 1rem; '
    'border: 1px solid rgba(255,255,255,0.1);"'
)


def img(filename: str, alt: str) -> str:
    return f'<img src="{ASSETS}/{filename}" alt="{alt}" {IMG_STYLE}/>'


# Each entry: (anchor — text that exists in the slide source, html block to insert AFTER the anchor)
INSERTS = [
    # Slide 20 — Latency trace: show the FlowDiagram with chips populated
    (
        '<b>Teaching point:</b> users do not feel averages. They feel awkward pauses, interruptions, and late mouth movement.</div></div></div>',
        f'<div style="display:flex;justify-content:center;margin-top:1rem;">{img("04-flow-with-chips.png", "FlowDiagram showing per-stage timing chips: tts 0.21s, avatar 0.00s, and lanes lighting up as each stage runs")}</div>',
    ),
    # Slide 23 — Full digital human: show the live UI
    (
        'event: avatar.mouth_started</pre></div></div></section>\n<section class="slide" data-notes="&lt;p&gt;Start knowledge from first principles, not RAG jargon.&lt;/p&gt;" data-slide="26">',
        '',  # we'll insert into slide 23 separately
    ),
    # Slide 33 — Change voice/avatar/model/personality: show the drawer + 8-avatar gallery + personality modal
    (
        '<div class="demo-card"><div class="label">Knowledge</div><div class="title">Context</div><div class="desc">What the human knows now.</div></div></div>',
        f'<div style="display:flex;gap:1rem;justify-content:center;margin-top:1.2rem;flex-wrap:wrap;">{img("07-controls-with-8-avatars.png", "Dashboard drawer showing brain / voice / avatar / personality selectors with 8 avatars (4 male + 4 female)")}{img("06-personality-modal.png", "Personality editor modal with the active prompt prefilled — Save / Reset / Cancel buttons + ESC to close")}</div>',
    ),
    # Slide 34 — Benchmark: show the real comparison table
    (
        '<div class="metric"><div class="val">GB</div><div class="name">VRAM</div><div class="desc">Can this laptop sustain the loop?</div></div></div>',
        f'<div style="display:flex;justify-content:center;margin-top:1.2rem;">{img("05-benchmark-table.png", "Benchmark widget — 6 rows comparing Qwen3 4B Instruct vs SmolLM2 360M across short / wiki-tool / long-gen prompts")}</div>',
    ),
    # Slide 23 — open browser + walkthrough auto-start
    (
        'Offline badge:          enabled</pre></div></div>',
        '<div style="display:flex;justify-content:center;margin-top:1rem;">' + img('01-walk-step1-meet-ava.png', 'First-page-load walkthrough overlay — Step 1 of 7 — spotlight on the avatar canvas with tooltip') + '</div>',
    ),
]


def patch():
    text = DECK.read_text()
    original = len(text)
    applied = 0
    for anchor, block in INSERTS:
        if not block:
            continue
        if anchor in text:
            # Insert AFTER the anchor
            text = text.replace(anchor, anchor + block, 1)
            print(f"  ✓ inserted screenshot at: {anchor[:60]!r}")
            applied += 1
        else:
            print(f"  ✗ MISS: {anchor[:60]!r}")
    DECK.write_text(text)
    print(f"\n{applied} screenshot blocks inserted")
    print(f"file: {original:,} → {len(text):,} chars (delta {len(text)-original:+,})")


if __name__ == '__main__':
    patch()
