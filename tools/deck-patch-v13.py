#!/usr/bin/env python3
"""
v12 → v13 deck patcher.

Structural edits per user spec:
  1. Combine slides 11 + 12 into a single "clone & install" slide.
  2. Insert a new install-overview slide (lingers during the install demo).
  3. Replace pseudo-console panels in slides 13/14/15 with real screenshots
     of /lab/01, /lab/03, /lab/02 captured live from localhost:3030.
  4. Swap slides 20 ↔ 23 so "Run the full digital human loop" comes earlier.
  5. Drop slides 21 (Use streaming), 29 (Add your own documents), 31 (Switch
     model providers), 32 (Escalate to stronger model).
  6. Renumber data-slide attributes + eyebrow .num spans so they're sequential
     in the new visual order.

Pure-Python over the source HTML — no DOM parser needed. We split on slide
section boundaries, mutate the list, then rejoin.

Run:    python3 tools/deck-patch-v13.py
Reads:  /home/rob/Downloads/NodeAvaWorkshopDeck_v12.html
Writes: /home/rob/Downloads/NodeAvaWorkshopDeck_v13.html
"""
from __future__ import annotations
import base64
import re
import sys
from pathlib import Path


SRC = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v12.html')
DST = Path('/home/rob/Downloads/NodeAvaWorkshopDeck_v13.html')
SHOT_DIR = Path('/home/rob/.claude/jobs/a5d283ca/deck-screenshots')


def b64_img(path: Path) -> str:
    raw = path.read_bytes()
    return base64.b64encode(raw).decode('ascii')


def img_panel(label: str, png: str) -> str:
    """Build a right-pane img replacement matching the deck's bar+content structure."""
    return (
        '<div class="lab-right">'
        f'<div class="terminal teach" style="padding:0;overflow:hidden;">'
        f'<div class="bar">{label}</div>'
        f'<img src="data:image/png;base64,{png}" alt="{label}" '
        'style="display:block;width:100%;height:auto;background:#0d1117;">'
        '</div></div>'
    )


# ── Build the new slide 11 (Clone & Install) ────────────────────────────────
def new_slide_clone(slide_num: int, eyebrow_num: int) -> str:
    return (
        f'<section class="slide" data-notes="&lt;p&gt;Everyone runs this together — the install bootstraps Docker, Ollama, all the models, and the full NodeAva stack. Linger here while the room catches up.&lt;/p&gt;" data-slide="{slide_num}">\n'
        f'<div class="eyebrow"><span class="num">{eyebrow_num}</span>Clone &amp; install</div>\n'
        f'<h2>Get the kit and run it</h2>\n'
        f'<p class="lede" style="margin-top:1.2rem;">Three commands. The first <code>setup.sh</code> bootstraps Docker, Ollama, and the model bundle; it then hands off to the NodeAva install wizard which builds the orchestrator, pulls workshop models, brings the stack up, and smoke-verifies it.</p>\n'
        f'<div class="terminal" style="margin-top:1.5rem;max-width:1000px;">'
        f'<div class="bar">terminal</div>'
        f'<pre><span class="cmd">git clone https://github.com/Lucasmind/nodeava-workshop-public.git</span>\n'
        f'<span class="cmd">cd nodeava-workshop-public</span>\n'
        f'<span class="cmd">./setup.sh</span>           <span class="key"># same exact UX as the USB key</span>\n'
        f'\n'
        f'<span class="key"># on the USB instead? plug it in and run the same setup.sh from the stick.</span></pre>'
        f'</div>\n'
        f'<p style="margin-top:1.4rem;font-size:0.92em;color:#9aa8b8;">The clone path pulls Docker images from <code>ghcr.io</code> (10-12 GB over the network); the USB path loads them from pre-bundled tarballs (no network needed past the install scripts).</p>\n'
        f'</section>'
    )


# ── Build the new slide 12 (Install overview — lingers) ─────────────────────
def new_slide_install_overview(slide_num: int, eyebrow_num: int) -> str:
    return (
        f'<section class="slide" data-notes="&lt;p&gt;Linger here while everyone installs. Talk through each step. Call out the gotchas BEFORE they hit them.&lt;/p&gt;" data-slide="{slide_num}">\n'
        f'<div class="eyebrow"><span class="num">{eyebrow_num}</span>Install</div>\n'
        f'<h2>What the installer does (and where it can pinch)</h2>\n'
        f'<div class="lab-grid">\n'
        f'  <div class="lab-left">\n'
        f'    <div class="lab-card teach">\n'
        f'      <div class="lab-label">setup.sh — 7 steps</div>\n'
        f'      <div class="steps">\n'
        f'        <div class="step"><b>1. Detect platform</b> — mac / linux / wsl2 + arch + GPU + free-disk preflight (20&nbsp;GB hard floor).</div>\n'
        f'        <div class="step"><b>2. Install Docker</b> — Docker Desktop on Mac; native via offline install-docker.sh on Linux/WSL2 (online with USB fallback).</div>\n'
        f'        <div class="step"><b>3. Install Ollama</b> — Homebrew on Mac; systemd on Linux/WSL2. Binds 0.0.0.0:11434 so containers can reach it.</div>\n'
        f'        <div class="step"><b>4. Load Docker images</b> — USB: <code>docker load</code> from tarballs. Clone: <code>docker pull</code> from <code>ghcr.io</code>.</div>\n'
        f'        <div class="step"><b>5. Stage Ollama models</b> — USB: copy blobs into <code>/usr/share/ollama/.ollama</code>. Clone: <code>ollama pull qwen3:4b-instruct</code>.</div>\n'
        f'        <div class="step"><b>6. Stage source tree</b> — copies into <code>~/nodeava-workshop/</code>.</div>\n'
        f'        <div class="step"><b>7. Hand off to <code>install.sh</code></b> — runs the 9-step wizard (preflight → inventory → models → stack up → smoke).</div>\n'
        f'      </div>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'  <div class="lab-right">\n'
        f'    <div class="lab-card teach" style="background:rgba(240, 176, 62, 0.06);border-color:rgba(240, 176, 62, 0.3);">\n'
        f'      <div class="lab-label" style="color:#f0b03e;">Gotchas (call these out)</div>\n'
        f'      <div class="steps">\n'
        f'        <div class="step"><b>NVIDIA Container Toolkit:</b> step 2 of <code>install.sh</code> auto-installs it if missing — accept the <code>[Y/n]</code> prompt.</div>\n'
        f'        <div class="step"><b>Blackwell (RTX 50-series):</b> auto-detected — installer pins <code>kokoro-fastapi-cpu</code> for TTS. CPU TTS is ~2-5 s / sentence vs &lt;0.5 s on Ampere/Ada.</div>\n'
        f'        <div class="step"><b>Apple Silicon:</b> step 7 builds <code>orchestrator</code> + <code>frontend</code> from source (no arm64 bundle ships for first-party images). Add ~3 min.</div>\n'
        f'        <div class="step"><b>Wifi flakey?</b> Re-plug the USB and run <code>./setup.sh --offline</code> — bundled installers + tarballs, no <code>get.docker.com</code>, no <code>ollama.com</code> needed.</div>\n'
        f'        <div class="step"><b>STT exit&nbsp;132?</b> Upstream <code>:main-vulkan</code> regressed. Setup retags the bundled pre-regression image automatically. If you hit it: <code>docker pull ghcr.io/lucasmind/nodeava-workshop/whisper-stt:known-good</code>.</div>\n'
        f'        <div class="step"><b>When done:</b> open <a href="http://localhost:3000/" style="color:#58a6ff;">http://localhost:3000/</a> for the dashboard and <a href="http://localhost:3000/lab/" style="color:#58a6ff;">/lab/</a> for the six workshop labs.</div>\n'
        f'      </div>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'</div>\n'
        f'</section>'
    )


def replace_right_pane(slide_html: str, new_right_pane: str) -> str:
    """Replace the entire <div class="lab-right">…</div> block (one section)."""
    start = slide_html.find('<div class="lab-right">')
    if start < 0:
        return slide_html
    # Walk forward to find the matching </div> (balanced)
    depth = 0
    i = start
    while i < len(slide_html):
        if slide_html[i:i+5] == '<div ' or slide_html[i:i+4] == '<div':
            depth += 1
            i = slide_html.find('>', i) + 1
            continue
        if slide_html[i:i+6] == '</div>':
            depth -= 1
            i += 6
            if depth == 0:
                end = i
                break
            continue
        i += 1
    else:
        return slide_html
    return slide_html[:start] + new_right_pane + slide_html[end:]


def renumber_slide(slide_html: str, new_data_slide: int, new_eyebrow: int) -> str:
    """Update data-slide="N" + first <span class="num">N</span> in the slide."""
    out = re.sub(
        r'data-slide="[\d.]+"',
        f'data-slide="{new_data_slide}"',
        slide_html, count=1,
    )
    out = re.sub(
        r'<span class="num">[\d]+</span>',
        f'<span class="num">{new_eyebrow}</span>',
        out, count=1,
    )
    return out


def main() -> int:
    if not SRC.exists():
        print(f'ERROR: source deck not found at {SRC}', file=sys.stderr)
        return 2

    html = SRC.read_text(encoding='utf-8')

    # ── Step 1: split into [pre_first_slide, slide_1, slide_2, ..., post_last_slide]
    # Slides are <section class="slide ..."> ... </section>. We segment using a regex
    # that matches each top-level <section class="slide ..."> block.
    pat = re.compile(r'<section class="slide[^"]*"[^>]*data-slide="[\d.]+"[^>]*>.*?</section>',
                     re.DOTALL)
    matches = list(pat.finditer(html))
    if not matches:
        print('ERROR: no <section class="slide"> blocks found', file=sys.stderr)
        return 1

    # Build map slide-id (data-slide value as string) → original-html
    slide_map: dict[str, str] = {}
    for m in matches:
        ds = re.search(r'data-slide="([\d.]+)"', m.group(0)).group(1)
        slide_map[ds] = m.group(0)

    print(f'  parsed {len(matches)} slides ({sorted(slide_map.keys(), key=lambda s: float(s))[:5]}… up to {sorted(slide_map.keys(), key=lambda s: float(s))[-5:]})')

    # ── Step 2: load screenshots and patch slides 13/14/15 ────────────────
    shot_01 = b64_img(SHOT_DIR / 'lab-01-llm.png')
    shot_02 = b64_img(SHOT_DIR / 'lab-02-stt.png')
    shot_03 = b64_img(SHOT_DIR / 'lab-03-tts.png')
    # Lab 4/5/6 screenshots also available; not slotted by user spec but
    # we could swap them in for slides 24/28/19 if desired later.

    if '13' in slide_map:
        slide_map['13'] = replace_right_pane(slide_map['13'], img_panel('http://localhost:3000/lab/01-llm.html', shot_01))
        print('  ✓ slide 13: terminal → screenshot of /lab/01-llm')
    if '14' in slide_map:
        slide_map['14'] = replace_right_pane(slide_map['14'], img_panel('http://localhost:3000/lab/03-tts.html', shot_03))
        print('  ✓ slide 14: terminal → screenshot of /lab/03-tts')
    if '15' in slide_map:
        slide_map['15'] = replace_right_pane(slide_map['15'], img_panel('http://localhost:3000/lab/02-stt.html', shot_02))
        print('  ✓ slide 15: terminal → screenshot of /lab/02-stt')

    # ── Step 3: combine 11 + 12 → new clone-and-install slide ────────────────
    # Replace slide 11 with the new combined slide, then delete old slide 12
    # (preflight) which is being subsumed. The new install-overview slot is
    # injected after the combined slide in the rebuild loop below.
    slide_map['11'] = new_slide_clone(11, 10)
    slide_map['_install_overview'] = new_slide_install_overview(12, 11)
    if '12' in slide_map:
        del slide_map['12']
        print('  ✓ dropped old slide 12 (preflight) — content folded into new clone-and-install + install-overview slides')
    print('  ✓ slide 11 → new clone-and-install slide')
    print('  ✓ NEW install-overview slide inserted after (new slide 12)')

    # ── Step 4: swap content of slides 20 ↔ 23 ────────────────────────────────
    if '20' in slide_map and '23' in slide_map:
        old_20, old_23 = slide_map['20'], slide_map['23']
        # Swap content but preserve each one's outer <section data-slide="N">
        # by extracting the inner HTML and putting it in the other's shell.
        # Simpler: keep both whole, swap which slide-id key holds which content.
        slide_map['20'], slide_map['23'] = old_23, old_20
        print('  ✓ swapped slide 20 ↔ slide 23 (Run digital human ↔ Measure latency)')

    # ── Step 5: drop slides 21, 29, 31, 32 ────────────────────────────────────
    for d in ('21', '29', '31', '32'):
        if d in slide_map:
            del slide_map[d]
            print(f'  ✓ dropped slide {d}')

    # ── Step 6: walk through original section order; rebuild new HTML ──────
    new_sections: list[str] = []

    # Iterate original slide order (by float-sorted data-slide)
    # but inject the new install-overview after slide 11.
    surviving_ids = sorted(
        [k for k in slide_map.keys() if k != '_install_overview'],
        key=lambda s: float(s),
    )

    for sid in surviving_ids:
        new_sections.append(slide_map[sid])
        if sid == '11':
            new_sections.append(slide_map['_install_overview'])

    # ── Step 7: renumber everything sequentially ──────────────────────────
    final_sections: list[str] = []
    for i, sect in enumerate(new_sections, start=1):
        final_sections.append(renumber_slide(sect, new_data_slide=i, new_eyebrow=i - 1))

    print(f'  ✓ renumbered {len(final_sections)} slides sequentially')

    # ── Step 8: rebuild the document by replacing the slide region ─────────
    # The slides occupy a contiguous block in the source.
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
