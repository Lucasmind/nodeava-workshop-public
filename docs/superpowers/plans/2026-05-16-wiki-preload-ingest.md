# Wiki Preload + Ingest Implementation Plan (Plan #6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Plan #3 wiki stub with a real, LLM-compiled self-knowledge wiki — so when a workshop attendee installs NodeAva and asks "what is this?", they get a coherent answer immediately. Plus a `POST /v1/ingest` endpoint so attendees can drop a file mid-workshop and watch the wiki grow.

**Architecture:** A new `services/wiki-compiler/` Python tool reads a manifest of `(topic, sources, template)` triples and produces wiki pages by calling Anthropic Sonnet 4.6 via LiteLLM. Run once offline, commit the generated markdown. A separate `POST /v1/ingest` endpoint accepts file uploads at runtime, writes them to `raw/`, and invokes the compiler against the new source — adds a `sources/<title>.md` summary plus updates relevant `concepts/` pages and `log.md`. Both code paths share the same compiler. The runtime ingest uses `asyncio.create_subprocess_exec` (NOT shell-string exec) so user-supplied filenames cannot inject commands.

**Tech Stack:**
- `litellm>=1.50,<2.0` (already in orchestrator) + `pyyaml` (new, for manifest)
- Anthropic Sonnet 4.6 (model `anthropic/claude-sonnet-4-6`) — strong enough for markdown writing, ~5x cheaper than Opus
- FastAPI multipart upload via `python-multipart`

**Working directory:** `/media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec`. All paths repo-relative.

**Branch:** `worktree-workshop-mvp-spec` tracking `workshop/main`.

**API cost budget:** ~$0.60 for the one-time compilation in Task 3. User has ~$5 of credits. Task 3 must capture token-usage logs so the actual spend is auditable.

---

## Task 1: Scaffold the wiki-compiler package

**Files:**
- Create: `services/wiki-compiler/compile_wiki.py`
- Create: `services/wiki-compiler/requirements.txt`
- Create: `services/wiki-compiler/README.md`
- Create: `services/wiki-compiler/prompts/system.txt`
- Create: `services/wiki-compiler/prompts/concept_page.txt`
- Create: `services/wiki-compiler/prompts/entity_page.txt`
- Create: `services/wiki-compiler/prompts/faq_page.txt`
- Create: `services/wiki-compiler/prompts/index_page.txt`

This task builds the **scaffolding only** — directory structure, requirements, prompt templates, and a CLI skeleton with `--help`. No actual LLM calls. Task 2 fills in the manifest content and Task 3 runs the compilation.

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p services/wiki-compiler/prompts
```

- [ ] **Step 2: Create `services/wiki-compiler/requirements.txt`**

```
litellm>=1.50,<2.0
pyyaml>=6.0,<7.0
```

- [ ] **Step 3: Create `services/wiki-compiler/prompts/system.txt`**

```
You are writing pages for NodeAva's self-knowledge wiki. NodeAva is a
fully-local digital-human stack: an avatar (browser, Three.js) that talks
via a pipeline of services on the user's own machine. Workshop attendees
read these pages directly AND ask an LLM about them — so write for both
audiences.

Rules:
- Markdown only. No frontmatter blocks unless explicitly asked.
- One-paragraph opener that answers the page's title in plain English.
- Concrete details — model names, port numbers, file paths — when relevant.
- Cross-link other wiki pages with [[wiki-link]] syntax (e.g. [[text-to-speech]]).
- Avoid hedging language ("you might consider", "it may be useful"). Be direct.
- Avoid emoji and decorative formatting. The TTS will read this aloud sometimes.
- Length: 200-400 words for concept/entity pages. Shorter for FAQs (100-200 words).
- Voice: third-person describing NodeAva, NOT first-person ("Ava thinks...").
- No marketing language. No "Welcome to NodeAva!" intros.
```

- [ ] **Step 4: Create `services/wiki-compiler/prompts/concept_page.txt`**

```
Write a wiki page titled "{title}" for NodeAva's `wiki/concepts/{slug}.md`.

Source material:

{sources}

The page should explain the concept clearly: what it is, why NodeAva uses
it, how it fits into the pipeline. Include specific model names, port
numbers, or file paths when they appear in the source material. Cross-link
to related concept/entity pages where natural.

Output ONLY the markdown body of the page, starting with a `# {title}` heading.
```

- [ ] **Step 5: Create `services/wiki-compiler/prompts/entity_page.txt`**

```
Write a wiki page titled "{title}" for NodeAva's `wiki/entities/{slug}.md`.

Source material:

{sources}

An entity page describes a specific named thing — a model, a library, a
service. The page should answer:
- What is this entity?
- What is its role in NodeAva specifically?
- Concrete facts: version, license, size, port, where to find it in the repo
- Where to learn more (upstream URL if known from sources)

Output ONLY the markdown body, starting with a `# {title}` heading.
```

- [ ] **Step 6: Create `services/wiki-compiler/prompts/faq_page.txt`**

```
Write a wiki FAQ page titled "{title}" for NodeAva's `wiki/faqs/{slug}.md`.

Source material:

{sources}

FAQ pages answer a single specific question — typically of the form "How
do I..." or "What is...". Keep it tight: opener that restates the
question, then the answer in 100-200 words. Use a numbered list if the
answer is a sequence of steps. Use code blocks for shell commands or
config snippets. Cross-link related pages.

Output ONLY the markdown body, starting with a `# {title}` heading.
```

- [ ] **Step 7: Create `services/wiki-compiler/prompts/index_page.txt`**

```
Regenerate `wiki/index.md` for NodeAva's self-knowledge wiki.

Pages currently in the wiki (path → title → one-line summary):

{pages}

Write the index page. Structure:
1. A short opener (3-4 sentences) explaining the wiki's purpose: this is
   the LLM's first stop for "what do I know?". The agent reads this index
   before opening specific pages.
2. Four sections — `## Concepts`, `## Entities`, `## FAQs`, `## Sources`.
   List pages under each, formatted as: `- [Title](concepts/slug.md) — summary`.
3. `## Sources` should say "(empty — populated at runtime via /v1/ingest)"
   if no source pages exist yet.

Output ONLY the markdown body, starting with `# Wiki Index`.
```

- [ ] **Step 8: Create `services/wiki-compiler/compile_wiki.py`** with a CLI skeleton:

```python
"""
compile_wiki.py - Compile NodeAva's self-knowledge wiki from a manifest.

Reads `manifest.yml` listing topics (concepts / entities / faqs) and the
NodeAva source files that should inform each one. For every topic, calls
Anthropic via LiteLLM with the source content + a template prompt, writes
the result to `wiki/<category>/<slug>.md`, and appends a log entry.

Finally regenerates `wiki/index.md` from the full set of pages.

Usage:
  ANTHROPIC_API_KEY=... python compile_wiki.py [--dry-run]
  python compile_wiki.py --ingest <file>     # one-off ingest of a new source

Cost: ~$0.60 with Anthropic Sonnet 4.6 for a full 20-page compilation.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

log = logging.getLogger("wiki-compiler")


# Paths are relative to the repo root (parent of services/).
REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_DIR = REPO_ROOT / "wiki"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.yml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be compiled without calling the API")
    parser.add_argument("--ingest", metavar="FILE",
                        help="Compile a single new source file into the wiki "
                             "(used by the /v1/ingest endpoint)")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-6",
                        help="LiteLLM model identifier (default: %(default)s)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    log.info("Repo root: %s", REPO_ROOT)
    log.info("Wiki dir: %s", WIKI_DIR)
    log.info("Manifest: %s", MANIFEST_PATH)

    if not MANIFEST_PATH.is_file():
        log.error("Manifest not found: %s", MANIFEST_PATH)
        return 1

    with MANIFEST_PATH.open() as fp:
        manifest = yaml.safe_load(fp)
    topic_count = sum(len(manifest.get(cat, [])) for cat in ("concepts", "entities", "faqs"))
    log.info("Manifest loaded: %d topics across %d categories",
             topic_count, len([c for c in ("concepts", "entities", "faqs") if manifest.get(c)]))

    if args.dry_run:
        log.info("Dry run — printing topic list:")
        for cat in ("concepts", "entities", "faqs"):
            for topic in manifest.get(cat, []):
                log.info("  %s/%s — %s", cat, topic["slug"], topic["title"])
        return 0

    # Task 2 fills in the manifest. Task 3 implements the actual compilation.
    log.warning(
        "Compilation step not yet implemented (Task 3). "
        "Run with --dry-run to validate the manifest."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9: Create `services/wiki-compiler/README.md`**

```markdown
# wiki-compiler

Compiles NodeAva's self-knowledge wiki from a manifest. Used:

1. **Offline, once**, to pre-populate `wiki/` before the workshop ships.
2. **At runtime**, invoked by `POST /v1/ingest` to compile a freshly-dropped
   source file into the wiki.

## How it works

`manifest.yml` lists topics in three categories — `concepts`, `entities`,
`faqs`. Each topic has:

```yaml
- slug: text-to-speech         # filename, becomes concepts/text-to-speech.md
  title: Text-to-Speech (TTS)  # heading in the page
  sources:                     # files read as input
    - frontend/src/tts/TTSManager.js
    - CLAUDE.md
```

For each topic, the compiler reads the source files, formats them into a
prompt (using `prompts/concept_page.txt` / `entity_page.txt` / `faq_page.txt`),
calls Anthropic Sonnet 4.6 via LiteLLM, and writes the result to
`wiki/<category>/<slug>.md`.

After all pages are written, `prompts/index_page.txt` regenerates
`wiki/index.md` so the agent's `wiki.list` tool reflects the new state.

## Recompiling

```bash
# From the repo root
export ANTHROPIC_API_KEY=...

cd services/wiki-compiler
pip install -r requirements.txt

# Validate the manifest without API calls
python compile_wiki.py --dry-run

# Full compilation (~$0.60 with Sonnet 4.6)
python compile_wiki.py
```

## Adding a new topic

1. Add an entry under the right category in `manifest.yml`.
2. Re-run `compile_wiki.py`.
3. Review the generated page in `wiki/<category>/<slug>.md`.
4. Commit if happy.

## Ingest pipeline

`POST /v1/ingest` (multipart upload of a file) → the orchestrator writes
it to `raw/uploads/<filename>` → invokes the compiler as a subprocess
via `asyncio.create_subprocess_exec` (NOT shell-string exec — filenames
are passed as a list element so user-supplied names can't inject) → the
compiler adds a `sources/<slug>.md` summary and updates any concept pages
whose subject is mentioned in the source.
```

- [ ] **Step 10: Smoke test the scaffold**

```bash
cd services/wiki-compiler
python compile_wiki.py --help 2>&1 | head -20
```

Expected: help text shows up. No import errors.

```bash
python compile_wiki.py --dry-run 2>&1 | tail -5
```

Expected: error "Manifest not found" (since Task 2 hasn't created it yet) — this is correct at this stage; we verify the file-existence check fires.

- [ ] **Step 11: Commit**

```bash
cd ../..
git add services/wiki-compiler/
git commit -m "feat(wiki): scaffold wiki-compiler (CLI + prompts + README)"
```

---

## Task 2: Author the manifest

**Files:**
- Create: `services/wiki-compiler/manifest.yml`

The manifest is the editorial choice of what the workshop wiki covers. It must be authored thoughtfully — the wiki is what attendees read first and is what trains their first impression of NodeAva.

**Authoring guide:** read the existing NodeAva docs (`CLAUDE.md`, `README.md`, `services/orchestrator/README.md`, the frontend's `frontend/README.md`, plus the source headers in `frontend/src/pipeline/Orchestrator.js`, `frontend/src/llm/LLMClient.js`, the orchestrator's `routes/chat.py`, the wiki tools at `services/orchestrator/orchestrator/tools/wiki.py`, etc.). Use the file contents as the "source material" for each topic in the manifest.

The manifest should cover **the top 15 questions** workshop attendees are likely to ask:

1. What is NodeAva?
2. How does it work end-to-end (the pipeline)?
3. What model does the LLM use?
4. How does speech-to-text work?
5. How does text-to-speech work?
6. What is the avatar made of?
7. Can I run this on my laptop?
8. What are the system requirements?
9. How do I change the voice?
10. How do I swap the LLM model?
11. What is the "agentic loop"?
12. What tools can the agent use?
13. What's the command center?
14. How do I make the avatar search the web?
15. How do I add my own knowledge to the wiki?

- [ ] **Step 1: Create `services/wiki-compiler/manifest.yml`** with the following content:

```yaml
# Manifest for NodeAva's self-knowledge wiki.
# Each entry compiles into wiki/<category>/<slug>.md.

concepts:
  - slug: nodeava-overview
    title: What is NodeAva?
    summary: One-page elevator pitch + architecture diagram in words.
    sources:
      - CLAUDE.md
      - README.md

  - slug: pipeline-architecture
    title: The NodeAva Pipeline
    summary: How user speech becomes avatar speech, stage by stage.
    sources:
      - CLAUDE.md
      - frontend/src/pipeline/Orchestrator.js
      - docker-compose.yml

  - slug: language-model
    title: The Language Model
    summary: Qwen3-4B via llama.cpp; thinking mode; tool calling.
    sources:
      - CLAUDE.md
      - services/orchestrator/README.md
      - services/orchestrator/orchestrator/providers/local.py

  - slug: text-to-speech
    title: Text-to-Speech (TTS)
    summary: Kokoro-82M via Kokoro-FastAPI; PCM + word timestamps; lip sync.
    sources:
      - frontend/src/tts/TTSManager.js
      - CLAUDE.md

  - slug: speech-to-text
    title: Speech-to-Text (STT)
    summary: Whisper base.en via whisper.cpp; VAD before transcription.
    sources:
      - frontend/src/stt/STTManager.js
      - CLAUDE.md

  - slug: avatar-rendering
    title: The 3D Avatar
    summary: TalkingHead + Three.js; loading custom .glb avatars.
    sources:
      - frontend/src/avatar/AvatarManager.js
      - CLAUDE.md

  - slug: agentic-loop
    title: The Agentic Loop
    summary: How tool calls cascade; max rounds; named SSE events.
    sources:
      - services/orchestrator/orchestrator/agentic.py
      - services/orchestrator/README.md

  - slug: tool-registry
    title: The Tool Registry
    summary: How browser.* and wiki.* tools are registered; adding custom tools.
    sources:
      - services/orchestrator/orchestrator/tools/__init__.py
      - services/orchestrator/orchestrator/tools/base.py
      - services/orchestrator/README.md

  - slug: web-search
    title: How NodeAva Searches the Web
    summary: SearXNG + browser.search/open/find; SSRF guards.
    sources:
      - services/orchestrator/orchestrator/tools/browser.py
      - services/orchestrator/README.md
      - configs/searxng/settings.yml

  - slug: wiki-system
    title: The Wiki System
    summary: Karpathy-style markdown wiki; index-driven retrieval; ingest pipeline.
    sources:
      - services/orchestrator/orchestrator/tools/wiki.py
      - services/wiki-compiler/README.md

entities:
  - slug: qwen3-4b
    title: Qwen3-4B (Default LLM)
    summary: Alibaba's 4B-parameter thinking model; Q4_K_M quantization.
    sources:
      - CLAUDE.md
      - docker-compose.yml

  - slug: kokoro-tts
    title: Kokoro-82M (TTS Engine)
    summary: 82M-parameter neural TTS; runs on GPU or CPU.
    sources:
      - CLAUDE.md
      - docker-compose.yml

  - slug: whisper-base-en
    title: Whisper base.en (STT Model)
    summary: OpenAI's English-only base model; runs via whisper.cpp.
    sources:
      - CLAUDE.md
      - docker-compose.yml

  - slug: talkinghead
    title: TalkingHead (Avatar Engine)
    summary: Browser-side 3D avatar with lip sync; CC BY-NC-SA 4.0 licensing.
    sources:
      - frontend/src/avatar/AvatarManager.js
      - CLAUDE.md

  - slug: searxng
    title: SearXNG (Search Engine)
    summary: Self-hosted meta-search; bundled, JSON API enabled.
    sources:
      - configs/searxng/settings.yml
      - services/orchestrator/README.md

faqs:
  - slug: system-requirements
    title: System Requirements
    summary: 8 GB GPU minimum; supported OSes; what doesn't work.
    sources:
      - CLAUDE.md
      - README.md

  - slug: change-voice
    title: How do I change the avatar's voice?
    summary: Voice selector in the control panel; available Kokoro voices.
    sources:
      - frontend/src/ui/components/ControlPanel.js
      - frontend/src/tts/TTSManager.js

  - slug: swap-model
    title: How do I swap the LLM model?
    summary: Provider toggle (local vs cloud); model file replacement (local).
    sources:
      - services/orchestrator/README.md
      - CLAUDE.md

  - slug: enable-web-search
    title: How do I make the avatar search the web?
    summary: The 🔍 Web search toggle in the control panel.
    sources:
      - frontend/README.md
      - services/orchestrator/README.md

  - slug: add-to-wiki
    title: How do I add my own knowledge to the wiki?
    summary: POST /v1/ingest with a file; the agent compiles it into the wiki.
    sources:
      - services/wiki-compiler/README.md
      - services/orchestrator/README.md
```

- [ ] **Step 2: Validate the manifest**

```bash
cd services/wiki-compiler
python compile_wiki.py --dry-run 2>&1 | tail -25
```

Expected: lists each topic as "category/slug — title" with the right counts. 10 concepts + 5 entities + 5 faqs = 20 topics.

- [ ] **Step 3: Commit**

```bash
cd ../..
git add services/wiki-compiler/manifest.yml
git commit -m "feat(wiki): manifest for 20-page self-knowledge wiki"
```

---

## Task 3: Implement the compilation logic + run it

**Files:**
- Modify: `services/wiki-compiler/compile_wiki.py`

This task replaces the `main()` body's placeholder with real compilation logic, then runs it once to produce the wiki content. **Requires the `ANTHROPIC_API_KEY` env var** (passed in by the controller when dispatching this task — see "Cost note" below).

**Cost note:** ~$0.60 with `anthropic/claude-sonnet-4-6`. The user has ~$5 of Anthropic credits remaining. The script must log the per-call token usage so the actual spend is auditable. If any call returns >5000 output tokens, abort and flag — that's runaway behavior.

- [ ] **Step 1: Replace `services/wiki-compiler/compile_wiki.py` ENTIRELY with the full implementation**

```python
"""
compile_wiki.py - Compile NodeAva's self-knowledge wiki from a manifest.

Reads `manifest.yml` listing topics (concepts / entities / faqs) and the
NodeAva source files that should inform each one. For every topic, calls
Anthropic via LiteLLM with the source content + a template prompt, writes
the result to `wiki/<category>/<slug>.md`, and appends a log entry.

Finally regenerates `wiki/index.md` from the full set of pages.

Usage:
  ANTHROPIC_API_KEY=... python compile_wiki.py [--dry-run]
  python compile_wiki.py --ingest <file>     # one-off ingest of a new source

Cost: ~$0.60 with Anthropic Sonnet 4.6 for a full 20-page compilation.
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

log = logging.getLogger("wiki-compiler")


# Paths are relative to the repo root (parent of services/).
REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_DIR = REPO_ROOT / "wiki"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.yml"

# Per-call safety limit. If any single completion returns more than this,
# something is wrong (model in a loop, or system prompt failure).
MAX_OUTPUT_TOKENS = 5000

CATEGORY_TEMPLATE = {
    "concepts": "concept_page.txt",
    "entities": "entity_page.txt",
    "faqs": "faq_page.txt",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be compiled without calling the API")
    parser.add_argument("--ingest", metavar="FILE",
                        help="Compile a single new source file into the wiki")
    parser.add_argument("--model", default="anthropic/claude-sonnet-4-6",
                        help="LiteLLM model identifier (default: %(default)s)")
    parser.add_argument("--only", metavar="SLUG",
                        help="Compile only the named topic (for re-runs)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY env var is required for actual compilation. "
                  "Use --dry-run to validate the manifest without API calls.")
        return 2

    log.info("Repo root: %s", REPO_ROOT)
    log.info("Model: %s", args.model)

    if not MANIFEST_PATH.is_file():
        log.error("Manifest not found: %s", MANIFEST_PATH)
        return 1

    with MANIFEST_PATH.open() as fp:
        manifest = yaml.safe_load(fp)

    if args.dry_run:
        for cat in ("concepts", "entities", "faqs"):
            for topic in manifest.get(cat, []):
                log.info("  %s/%s — %s", cat, topic["slug"], topic["title"])
        return 0

    # Ensure category directories exist (preserves Plan #3 stub structure).
    for cat in ("concepts", "entities", "faqs", "sources", "comparisons"):
        (WIKI_DIR / cat).mkdir(parents=True, exist_ok=True)

    system_prompt = (PROMPTS_DIR / "system.txt").read_text()

    # --ingest <file> mode: process one new source → sources/<slug>.md
    # (used by POST /v1/ingest at runtime). Skip the full compilation.
    if args.ingest:
        return _do_ingest(Path(args.ingest), args.model, system_prompt)

    # Full-compile path (no --ingest)
    total_input_tokens = 0
    total_output_tokens = 0
    pages_written: list[dict] = []
    started = time.monotonic()

    for cat in ("concepts", "entities", "faqs"):
        for topic in manifest.get(cat, []):
            if args.only and topic["slug"] != args.only:
                continue
            page, usage = _compile_topic(
                category=cat,
                topic=topic,
                model=args.model,
                system_prompt=system_prompt,
            )
            out_path = WIKI_DIR / cat / f"{topic['slug']}.md"
            out_path.write_text(page)
            pages_written.append({
                "category": cat,
                "slug": topic["slug"],
                "title": topic["title"],
                "summary": topic.get("summary", ""),
                "path": f"{cat}/{topic['slug']}.md",
            })
            total_input_tokens += usage["input_tokens"]
            total_output_tokens += usage["output_tokens"]
            log.info("  wrote %s  (in=%d out=%d)",
                     out_path.relative_to(REPO_ROOT),
                     usage["input_tokens"], usage["output_tokens"])

    # Regenerate index.md from the full set of existing pages (not just
    # the ones we wrote this run — preserves any handwritten additions).
    index_md, idx_usage = _regenerate_index(model=args.model, system_prompt=system_prompt)
    (WIKI_DIR / "index.md").write_text(index_md)
    total_input_tokens += idx_usage["input_tokens"]
    total_output_tokens += idx_usage["output_tokens"]
    log.info("  wrote wiki/index.md  (in=%d out=%d)",
             idx_usage["input_tokens"], idx_usage["output_tokens"])

    # Append a log entry to wiki/log.md
    elapsed = time.monotonic() - started
    log_entry = (
        f"\n## [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] "
        f"compile-all\n\n"
        f"- Model: {args.model}\n"
        f"- Pages compiled: {len(pages_written)}\n"
        f"- Tokens: {total_input_tokens:,} in, {total_output_tokens:,} out\n"
        f"- Elapsed: {elapsed:.1f}s\n"
    )
    log_path = WIKI_DIR / "log.md"
    existing = log_path.read_text() if log_path.exists() else "# Wiki Activity Log\n"
    log_path.write_text(existing + log_entry)
    log.info("appended log entry to %s", log_path)

    log.info(
        "Done. %d pages, %d total tokens (in=%d out=%d)",
        len(pages_written),
        total_input_tokens + total_output_tokens,
        total_input_tokens,
        total_output_tokens,
    )
    return 0


def _read_sources(source_paths: list[str]) -> str:
    """Concatenate the contents of source files into a single labelled block."""
    chunks = []
    for rel_path in source_paths:
        abs_path = REPO_ROOT / rel_path
        if not abs_path.is_file():
            log.warning("  source not found: %s — skipping", rel_path)
            continue
        try:
            content = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            log.warning("  cannot read %s: %s — skipping", rel_path, e)
            continue
        chunks.append(f"--- FILE: {rel_path} ---\n\n{content}\n")
    return "\n".join(chunks)


def _compile_topic(
    *, category: str, topic: dict, model: str, system_prompt: str
) -> tuple[str, dict]:
    """Compile one topic page. Returns (markdown, usage_dict)."""
    import litellm

    template_name = CATEGORY_TEMPLATE[category]
    template = (PROMPTS_DIR / template_name).read_text()
    sources = _read_sources(topic.get("sources", []))

    user_msg = template.format(
        title=topic["title"],
        slug=topic["slug"],
        sources=sources or "(no sources provided)",
    )

    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.3,
    )

    choice = resp.choices[0]
    text = choice.message.content or ""
    usage = {
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }
    if usage["output_tokens"] >= MAX_OUTPUT_TOKENS:
        raise RuntimeError(
            f"completion for {topic['slug']} hit MAX_OUTPUT_TOKENS — "
            "possible runaway. Aborting before more API spend."
        )
    return text.strip() + "\n", usage


def _regenerate_index(*, model: str, system_prompt: str) -> tuple[str, dict]:
    """Regenerate wiki/index.md from the full set of pages on disk."""
    import litellm

    pages = []
    for cat in ("concepts", "entities", "faqs", "sources", "comparisons"):
        cat_dir = WIKI_DIR / cat
        if not cat_dir.is_dir():
            continue
        for md_path in sorted(cat_dir.glob("*.md")):
            # Extract first heading and first paragraph (best-effort).
            text = md_path.read_text()
            title = md_path.stem  # fallback
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            # Use first non-heading, non-empty line as summary (truncated).
            summary = ""
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    summary = stripped[:160].rstrip()
                    if len(stripped) > 160:
                        summary += "…"
                    break
            pages.append({
                "path": f"{cat}/{md_path.stem}.md",
                "title": title,
                "summary": summary,
            })

    pages_str = "\n".join(
        f"- {p['path']} — {p['title']}: {p['summary']}" for p in pages
    )
    template = (PROMPTS_DIR / "index_page.txt").read_text()
    user_msg = template.format(pages=pages_str or "(no pages yet)")

    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.3,
    )
    text = resp.choices[0].message.content or ""
    usage = {
        "input_tokens": resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
    }
    return text.strip() + "\n", usage


def _do_ingest(source_path: Path, model: str, system_prompt: str) -> int:
    """Process a single new source file → sources/<slug>.md summary page.

    Called by POST /v1/ingest at runtime. Doesn't touch concepts/ — that's
    a more invasive operation that needs heuristics for "is this concept
    page about this source?". Keeping ingest scope minimal for v1.
    """
    import litellm
    import re

    if not source_path.is_file():
        log.error("source not found: %s", source_path)
        return 1

    try:
        content = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        log.error("cannot read %s: %s", source_path, e)
        return 1

    # Slug from filename: strip extension, lowercase, replace non-alnum with -.
    slug = re.sub(r"[^a-z0-9]+", "-", source_path.stem.lower()).strip("-")
    if not slug:
        slug = "ingested-source"
    title = source_path.stem

    ingest_prompt = (PROMPTS_DIR / "ingest_source.txt").read_text()
    user_msg = ingest_prompt.format(
        title=title,
        slug=slug,
        filename=source_path.name,
        content=content[:20000],  # cap large files
    )

    log.info("Ingesting %s → wiki/sources/%s.md", source_path.name, slug)
    resp = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.3,
    )
    page = (resp.choices[0].message.content or "").strip() + "\n"
    in_tok = resp.usage.prompt_tokens
    out_tok = resp.usage.completion_tokens
    if out_tok >= MAX_OUTPUT_TOKENS:
        log.error("ingest hit MAX_OUTPUT_TOKENS — aborting")
        return 2

    # Ensure sources/ exists
    (WIKI_DIR / "sources").mkdir(parents=True, exist_ok=True)
    out_path = WIKI_DIR / "sources" / f"{slug}.md"
    out_path.write_text(page)
    log.info("wrote %s (in=%d out=%d)", out_path.relative_to(REPO_ROOT), in_tok, out_tok)

    # Append log entry
    log_entry = (
        f"\n## [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] "
        f"ingest | {source_path.name} → sources/{slug}.md\n\n"
        f"- Model: {model}\n"
        f"- Tokens: {in_tok:,} in, {out_tok:,} out\n"
    )
    log_path = WIKI_DIR / "log.md"
    existing = log_path.read_text() if log_path.exists() else "# Wiki Activity Log\n"
    log_path.write_text(existing + log_entry)

    # Regenerate index.md so wiki.list reflects the new sources/ page
    index_md, _ = _regenerate_index(model=model, system_prompt=system_prompt)
    (WIKI_DIR / "index.md").write_text(index_md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 1b: Create `services/wiki-compiler/prompts/ingest_source.txt`**

(Add to Task 1's prompt set — but it's easier to author it here since it's specific to ingest.)

```
Write a wiki source-summary page for `wiki/sources/{slug}.md`. This page
summarizes a freshly-ingested document so the agent can find and quote
the source's contents via the wiki tools.

Source file: {filename}
Title: {title}

Contents:

{content}

The page should:
- Open with a 1-2 sentence summary of what this document is about.
- List the 3-5 most important facts, claims, or entities from the document.
- Be a faithful summary — don't add information that isn't in the source.
- Length: 150-300 words.

Output ONLY the markdown body, starting with a `# {title}` heading.
```

- [ ] **Step 2: Install compiler deps + verify dry-run still works**

```bash
cd services/wiki-compiler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python compile_wiki.py --dry-run
```

Expected: lists 20 topics. No API calls.

- [ ] **Step 3: Run the actual compilation**

```bash
# Controller passes the API key in. The implementer should NOT hardcode it.
# Expect 20 pages × ~10s/page = ~3-4 min total runtime.

ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" python compile_wiki.py 2>&1 | tee /tmp/wiki-compile.log
```

Expected output last few lines:

```
INFO ... wrote wiki/index.md  (in=NNN out=NNN)
INFO ... appended log entry to .../wiki/log.md
INFO ... Done. 20 pages, NNNN total tokens (in=NNNNN out=NNNNN)
```

If any single page fails, the script aborts — re-run with `--only <slug>` to retry just that one.

If the total output tokens cost exceeds the per-page safety limit, you'll see a `RuntimeError: completion for <slug> hit MAX_OUTPUT_TOKENS`. Investigate before retrying.

- [ ] **Step 4: Spot-check a few generated pages**

```bash
cd ../..
ls wiki/concepts/
head -20 wiki/concepts/nodeava-overview.md
head -20 wiki/concepts/agentic-loop.md
head -10 wiki/faqs/system-requirements.md
head -30 wiki/index.md
```

The pages should:
- Start with `# <Title>` heading
- Have a coherent opening paragraph
- Reference concrete facts from the source files (e.g. "Qwen3-4B", "/api/llm", "port 8082")
- Use `[[wiki-link]]` syntax for cross-references

If any page is garbage or empty, that's a compilation problem — investigate `/tmp/wiki-compile.log` for the failing page and retry with `--only <slug>`.

- [ ] **Step 5: Commit the generated content**

```bash
git add wiki/ services/wiki-compiler/compile_wiki.py
git commit -m "feat(wiki): pre-compile self-knowledge wiki (20 pages via Sonnet 4.6)"
```

- [ ] **Step 6: Verify the wiki tools can read the new content**

The orchestrator's wiki tools (Plan #3) operate on the on-disk wiki. After the compilation, they should return real content.

Quick smoke test via Python (no Docker needed):

```bash
cd services/orchestrator
source .venv/bin/activate

python -c "
import asyncio
from orchestrator.tools.wiki import WikiList, WikiSearch, WikiOpen

async def main():
    # wiki.list should now return a comprehensive index
    list_tool = WikiList(wiki_dir='../../wiki')
    out = await list_tool.execute({})
    print('=== wiki.list (first 500 chars) ===')
    print(out[:500])
    print()

    # wiki.search should find content
    search_tool = WikiSearch(wiki_dir='../../wiki')
    out = await search_tool.execute({'query': 'Qwen3'})
    print('=== wiki.search Qwen3 (first 500 chars) ===')
    print(out[:500])

asyncio.run(main())
"
```

Expected:
- `wiki.list` output contains links to multiple categories with actual page references (not the Plan #3 "empty" stub)
- `wiki.search Qwen3` finds matches in `wiki/entities/qwen3-4b.md` and probably `concepts/language-model.md`

- [ ] **Step 7: Cost report**

Look at `wiki/log.md` for the appended entry — confirm total input + output tokens. Verify cost calculation:
- Sonnet 4.6: $3/M input, $15/M output
- Estimated total: <$1.00

If actual cost exceeds $1.50 — investigate (might be a manifest that pulled in too much source material).

---

## Task 4: `POST /v1/ingest` endpoint

**Files:**
- Create: `services/orchestrator/orchestrator/ingest/__init__.py`
- Create: `services/orchestrator/orchestrator/ingest/runner.py`
- Create: `services/orchestrator/orchestrator/routes/ingest.py`
- Modify: `services/orchestrator/orchestrator/main.py` (register ingest router)
- Create: `services/orchestrator/tests/test_routes_ingest.py`

The endpoint accepts a multipart file upload, writes it to `raw/uploads/<filename>`, invokes the wiki-compiler with `--ingest <path>`, and returns the compile result + a list of pages that changed.

**Security note:** the runner uses `asyncio.create_subprocess_exec` — argv-style invocation, NOT a shell string. The compiler path and the source file path are passed as separate list elements; user-supplied filenames cannot inject shell commands. The route ALSO sanitizes the uploaded filename before writing it to disk (path-traversal-safe).

For Plan #6 we ship **synchronous compilation** — the request blocks until the compile finishes (or aborts on error). Async-with-polling is a v1.1 polish.

**Caveat:** the compiler needs `ANTHROPIC_API_KEY` to be set in the orchestrator container's environment. Document this in the README; do NOT hardcode.

- [ ] **Step 1: Create `services/orchestrator/orchestrator/ingest/__init__.py`** (empty marker):

```python
"""Plan #6: runtime ingest pipeline — drop a file → wiki compiler updates wiki/."""
```

- [ ] **Step 2: Create `services/orchestrator/orchestrator/ingest/runner.py`**

```python
"""Shell out to the wiki-compiler with a newly-uploaded source file.

Runs synchronously. Returns the captured stdout/stderr + a list of pages
that changed on disk, by snapshotting wiki/ mtimes before/after.

Uses asyncio.create_subprocess_exec (NOT shell) — the compiler path and
source path are passed as separate argv elements. User-controlled filenames
cannot inject shell commands.
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("orchestrator.ingest.runner")


# Paths inside the container. For the Dockerized orchestrator, /app/wiki
# is the bind-mount target from Plan #3. The wiki-compiler lives in a
# sibling directory at /app/wiki-compiler (Plan #6 Dockerfile update).
WIKI_DIR = Path(os.environ.get("WIKI_DIR", "/app/wiki"))
RAW_DIR = Path(os.environ.get("RAW_DIR", "/app/raw"))
COMPILER_PATH = Path(
    os.environ.get("WIKI_COMPILER_PATH", "/app/wiki-compiler/compile_wiki.py")
)


@dataclass
class IngestResult:
    ok: bool
    pages_changed: list[str]
    stdout: str
    stderr: str
    error: str | None = None


async def ingest_file(source_path: Path) -> IngestResult:
    """Run the compiler against a single source file.

    `source_path` must already exist (the route writes it before calling).
    Returns IngestResult with pages_changed populated from a mtime diff.
    """
    if not COMPILER_PATH.is_file():
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="",
            error=f"compiler not found at {COMPILER_PATH}",
        )
    if not source_path.is_file():
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="",
            error=f"source file not found: {source_path}",
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="",
            error="ANTHROPIC_API_KEY env var not set in the orchestrator container",
        )

    pre_snapshot = _snapshot_mtimes(WIKI_DIR)
    log.info("Ingest: running compiler against %s", source_path)

    # asyncio.create_subprocess_exec — argv-style invocation, no shell.
    # User-supplied paths are passed as separate list elements; they cannot
    # be interpreted as shell metacharacters.
    proc = await asyncio.create_subprocess_exec(
        "python",
        str(COMPILER_PATH),
        "--ingest",
        str(source_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(COMPILER_PATH.parent),
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")

    post_snapshot = _snapshot_mtimes(WIKI_DIR)
    changed = [
        p for p, mtime in post_snapshot.items()
        if pre_snapshot.get(p) != mtime
    ]
    log.info("Ingest done (rc=%d, %d pages changed)", proc.returncode, len(changed))

    if proc.returncode != 0:
        return IngestResult(
            ok=False,
            pages_changed=changed,
            stdout=stdout,
            stderr=stderr,
            error=f"compiler exited with code {proc.returncode}",
        )
    return IngestResult(
        ok=True,
        pages_changed=changed,
        stdout=stdout,
        stderr=stderr,
        error=None,
    )


def _snapshot_mtimes(root: Path) -> dict[str, float]:
    """Map of relative path -> mtime for all *.md files under root."""
    if not root.is_dir():
        return {}
    out: dict[str, float] = {}
    for md in root.rglob("*.md"):
        try:
            out[str(md.relative_to(root))] = md.stat().st_mtime
        except OSError:
            continue
    return out
```

- [ ] **Step 3: Create `services/orchestrator/orchestrator/routes/ingest.py`**

```python
"""POST /v1/ingest — workshop attendees drop a file, agent compiles it into the wiki.

Plan #6 ships synchronous compilation — the request blocks until the
compiler finishes or aborts. Plan #10 may add async polling if needed.

Request: multipart/form-data with a single `file` part.
Response (200): {ok: true, pages_changed: [...], summary: "..."}
Response (4xx): {error: "..."}
Response (5xx): {error: "..."}
"""
import logging
import re

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from orchestrator.ingest.runner import RAW_DIR, IngestResult, ingest_file

log = logging.getLogger("orchestrator.routes.ingest")

router = APIRouter()


_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@router.post("/v1/ingest")
async def ingest(file: UploadFile) -> JSONResponse:
    if not file.filename:
        return JSONResponse({"error": "missing filename"}, status_code=400)

    safe_name = _SAFE_FILENAME_RE.sub("_", file.filename).strip("._")
    if not safe_name:
        return JSONResponse({"error": "filename produced empty safe form"}, status_code=400)

    target_dir = RAW_DIR / "uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name

    # Save the upload to disk
    try:
        contents = await file.read()
        target.write_bytes(contents)
        size = len(contents)
    except Exception as e:
        log.warning("failed to write upload: %s", e)
        return JSONResponse({"error": f"failed to save upload: {e}"}, status_code=500)

    log.info("Ingest received %s (%d bytes) → %s", file.filename, size, target)

    result: IngestResult = await ingest_file(target)

    payload = {
        "ok": result.ok,
        "pages_changed": result.pages_changed,
        "source_path": str(target),
        "stdout_tail": result.stdout[-1000:] if result.stdout else "",
    }
    if not result.ok:
        payload["error"] = result.error or "compile failed"
        payload["stderr_tail"] = result.stderr[-1000:] if result.stderr else ""
        return JSONResponse(payload, status_code=500)

    return JSONResponse(payload, status_code=200)
```

- [ ] **Step 4: Modify `services/orchestrator/orchestrator/main.py`** — register the new router.

Find the line `from orchestrator.routes import chat, health, models` and replace it with:

```python
from orchestrator.routes import chat, health, ingest, models
```

Find the line `app.include_router(chat.router)` and INSERT this line AFTER it:

```python
    app.include_router(ingest.router)
```

- [ ] **Step 5: Create `services/orchestrator/tests/test_routes_ingest.py`**

```python
"""Tests for the /v1/ingest route.

We can't run the real compiler in unit tests (it needs an API key and
takes minutes). So we patch the runner's `ingest_file` to a fast fake
and verify the route's wrap behavior — file save, response shape, error
mapping — works correctly.
"""
import io
import pytest

from orchestrator.ingest.runner import IngestResult


async def test_ingest_writes_file_and_runs_compiler(app_client, monkeypatch, tmp_path):
    """Happy path: file gets saved to raw/uploads/, runner is invoked,
    response contains pages_changed."""
    # Point RAW_DIR at a tmp_path for this test
    from orchestrator.ingest import runner as runner_module
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)

    captured: dict = {}

    async def fake_ingest(source_path):
        captured["source_path"] = source_path
        return IngestResult(
            ok=True,
            pages_changed=["concepts/new-page.md"],
            stdout="compiled 1 page",
            stderr="",
            error=None,
        )

    # The route imports `ingest_file` at module load time — patch it there.
    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(ingest_route, "ingest_file", fake_ingest)

    files = {"file": ("notes.md", io.BytesIO(b"# Some notes\nHello world."), "text/markdown")}
    resp = await app_client.post("/v1/ingest", files=files)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "concepts/new-page.md" in body["pages_changed"]
    assert body["stdout_tail"] == "compiled 1 page"

    # File was written to raw/uploads/
    target = tmp_path / "uploads" / "notes.md"
    assert target.is_file()
    assert target.read_bytes() == b"# Some notes\nHello world."

    # Runner was called with the right path
    assert captured["source_path"] == target


async def test_ingest_sanitizes_unsafe_filename(app_client, monkeypatch, tmp_path):
    """Filenames like '../../etc/passwd' get sanitized — written to a
    safe-renamed file under raw/uploads/ (not the original path)."""
    from orchestrator.ingest import runner as runner_module
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)

    async def fake_ingest(source_path):
        return IngestResult(ok=True, pages_changed=[], stdout="", stderr="", error=None)

    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(ingest_route, "ingest_file", fake_ingest)

    files = {
        "file": ("../../etc/passwd", io.BytesIO(b"sensitive"), "text/plain"),
    }
    resp = await app_client.post("/v1/ingest", files=files)
    assert resp.status_code == 200

    # The target file should be under raw/uploads/ with a sanitized name
    saved = list((tmp_path / "uploads").iterdir())
    assert len(saved) == 1
    saved_path = saved[0]
    # Sanitized name should NOT be ../../etc/passwd
    assert "passwd" in saved_path.name or "etc" in saved_path.name
    assert ".." not in saved_path.name
    assert "/" not in saved_path.name
    # And the file is under raw/uploads (no path escape)
    assert saved_path.is_relative_to(tmp_path / "uploads")


async def test_ingest_compiler_failure_returns_500(app_client, monkeypatch, tmp_path):
    """If the runner reports ok=False, the route returns 500 with error details."""
    from orchestrator.ingest import runner as runner_module
    monkeypatch.setattr(runner_module, "RAW_DIR", tmp_path)

    async def fake_ingest(source_path):
        return IngestResult(
            ok=False,
            pages_changed=[],
            stdout="",
            stderr="ANTHROPIC_API_KEY env var not set",
            error="compiler exited with code 2",
        )

    from orchestrator.routes import ingest as ingest_route
    monkeypatch.setattr(ingest_route, "ingest_file", fake_ingest)

    files = {"file": ("notes.md", io.BytesIO(b"x"), "text/plain")}
    resp = await app_client.post("/v1/ingest", files=files)
    assert resp.status_code == 500
    body = resp.json()
    assert body["ok"] is False
    assert "compiler exited" in body["error"]
    assert "ANTHROPIC_API_KEY" in body["stderr_tail"]
```

- [ ] **Step 6: Install `python-multipart`** (required by FastAPI for `UploadFile`):

```bash
cd services/orchestrator
source .venv/bin/activate
pip install "python-multipart>=0.0.9,<1.0"
```

Add it to `requirements.txt` permanently. Open `services/orchestrator/requirements.txt` and append a new line:

```
python-multipart>=0.0.9,<1.0
```

- [ ] **Step 7: Run the tests**

```bash
pytest tests/test_routes_ingest.py -v
```

Expected: 3 tests pass. Cumulative suite count remains green.

- [ ] **Step 8: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): POST /v1/ingest — upload + synchronous wiki compile"
```

---

## Task 5: Docker integration for the ingest pipeline

**Files:**
- Modify: `services/orchestrator/Dockerfile`
- Modify: `docker-compose.yml`

The orchestrator container needs:
1. Access to `services/wiki-compiler/` (COPY in the image)
2. `python-multipart` available (Task 4 step 6 added it to requirements.txt — the rebuild picks it up)
3. The `raw/` directory mounted writable (Plan #3 ignored raw/* in gitignore but the directory exists on disk)
4. The wiki-compiler's deps (litellm, pyyaml) installed alongside the orchestrator's

The simplest approach: COPY the compiler into the orchestrator image AND install its deps into the same venv. This means changing the Docker build context from `./services/orchestrator` to `./services` so both `orchestrator/` and `wiki-compiler/` are visible.

- [ ] **Step 1: Read the current Dockerfile**

```bash
cat services/orchestrator/Dockerfile
```

- [ ] **Step 2: Update `services/orchestrator/Dockerfile`** — replace it entirely with:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Build context is ./services (per docker-compose). Layout inside:
#   orchestrator/  → the orchestrator app
#   wiki-compiler/ → the wiki compiler invoked by /v1/ingest
COPY orchestrator/requirements.txt orchestrator/pyproject.toml ./
COPY orchestrator/orchestrator/ ./orchestrator/

# Copy the wiki-compiler so the ingest pipeline can invoke it.
# Plan #6: the compiler is a separate Python project; it lives at
# /app/wiki-compiler inside the container and shares the orchestrator's
# venv. The orchestrator's ingest runner shells out to compile_wiki.py.
COPY wiki-compiler/ /app/wiki-compiler/

# Combined install: orchestrator deps + compiler deps + editable install.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r /app/wiki-compiler/requirements.txt \
    && pip install --no-cache-dir -e .

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

CMD ["python", "-m", "orchestrator.main"]
```

- [ ] **Step 3: Update `docker-compose.yml`** — change the orchestrator service's `build.context` to `./services` (so both `orchestrator/` and `wiki-compiler/` are available).

Find the orchestrator service block. The current `build:` section should look like:

```yaml
  orchestrator:
    build:
      context: ./services/orchestrator
      dockerfile: Dockerfile
```

Replace with:

```yaml
  orchestrator:
    build:
      context: ./services
      dockerfile: orchestrator/Dockerfile
```

ALSO: the orchestrator service needs the raw/ directory mounted writable. Find the existing `volumes:` block in the orchestrator service:

```yaml
    volumes:
      - ./wiki:/app/wiki:ro
```

Add a second mount for the raw directory:

```yaml
    volumes:
      - ./wiki:/app/wiki:ro
      - ./raw:/app/raw:rw
```

ALSO add `RAW_DIR=/app/raw` and `WIKI_COMPILER_PATH=/app/wiki-compiler/compile_wiki.py` to the existing `environment:` block (next to `WIKI_DIR=/app/wiki` from Plan #3):

```yaml
    environment:
      - LLAMA_URL=http://llm:8080
      - REQUEST_TIMEOUT=300
      - BIND_HOST=0.0.0.0
      - BIND_PORT=8082
      - WIKI_DIR=/app/wiki
      - RAW_DIR=/app/raw
      - WIKI_COMPILER_PATH=/app/wiki-compiler/compile_wiki.py
```

**ANTHROPIC_API_KEY is NOT in docker-compose** — it's per-user. The user sets it before bringing up the stack:

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up -d orchestrator
```

Document this in the next task (README).

- [ ] **Step 4: Rebuild the orchestrator container**

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml build orchestrator
```

Expected: clean build. The wiki-compiler is now inside the image.

- [ ] **Step 5: Smoke test the ingest container path**

```bash
docker run --rm \
  -v $(pwd)/wiki:/app/wiki:ro \
  -v $(pwd)/raw:/app/raw:rw \
  nodeava-orch:latest \
  python /app/wiki-compiler/compile_wiki.py --dry-run
```

Expected: the dry-run lists the 20 topics. No errors.

- [ ] **Step 6: Commit**

```bash
git add services/orchestrator/Dockerfile docker-compose.yml
git commit -m "feat(orch): bundle wiki-compiler into orchestrator image + ingest mounts"
```

---

## Task 6: Documentation + CLAUDE.md update

**Files:**
- Modify: `services/wiki-compiler/README.md` (add deployment + cost notes)
- Modify: `services/orchestrator/README.md` (document /v1/ingest)
- Modify: `CLAUDE.md` (Plan #6 note)

- [ ] **Step 1: Append a "Deployment" section to `services/wiki-compiler/README.md`**

```markdown
## Deployment (Plan #6 Docker integration)

The compiler is bundled into the orchestrator container image so the
`POST /v1/ingest` endpoint can invoke it via subprocess. The container
expects:

- `/app/wiki/` — read-write mount of the host `wiki/` directory
- `/app/raw/` — read-write mount of the host `raw/` directory (uploads land here)
- `ANTHROPIC_API_KEY` env var — pass in at `docker compose up` time:

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up -d orchestrator
```

If `ANTHROPIC_API_KEY` is missing, ingest requests fail with HTTP 500 and
an explicit error message. The compiler also fails out the same way when
invoked directly.

## Cost notes

Per-compilation: ~$0.60 with Anthropic Sonnet 4.6 (20 pages, ~30K tokens
out total). Per-ingest: typically ~$0.05 (one new source = one new
sources/ page + ~3 updated concept pages). Plan #10 may add a per-user
cost limiter.
```

- [ ] **Step 2: Insert an "Ingest endpoint" section into `services/orchestrator/README.md`**

Find the existing "Tools" section and insert this NEW section right BEFORE the "Run locally (dev)" section:

```markdown
## Ingest endpoint (Plan #6)

```
POST /v1/ingest
Content-Type: multipart/form-data
Body: file=<binary>
```

Saves the upload to `/app/raw/uploads/<sanitized-name>`, invokes the
wiki-compiler against it, and returns the list of wiki pages that changed.

**Synchronous.** The request blocks until the compile finishes (~10-30s
for typical sources). Plan #10 may add async polling.

Example:

```bash
curl http://localhost:8082/v1/ingest \
  -F file=@README.md
```

Response (success):

```json
{
  "ok": true,
  "pages_changed": ["sources/readme-md.md", "concepts/pipeline-architecture.md"],
  "source_path": "/app/raw/uploads/README.md",
  "stdout_tail": "..."
}
```

Response (compiler failure):

```json
{
  "ok": false,
  "error": "compiler exited with code 2",
  "stderr_tail": "ANTHROPIC_API_KEY env var not set"
}
```

**Required**: `ANTHROPIC_API_KEY` env var on the orchestrator container.
See the wiki-compiler README for setup.
```

- [ ] **Step 3: Append to `CLAUDE.md`**

Append a new section at the end:

```markdown
## Plan #6 — preloaded wiki + ingest

- `wiki/` is pre-populated with 20 pages of NodeAva self-knowledge,
  compiled via `services/wiki-compiler/compile_wiki.py` using
  Anthropic Sonnet 4.6. The compiler reads `services/wiki-compiler/manifest.yml`
  (a list of topics → source files) and emits markdown into `wiki/concepts/`,
  `wiki/entities/`, `wiki/faqs/`.
- `POST /v1/ingest` accepts a multipart file upload, saves it to
  `/app/raw/uploads/`, invokes the compiler with `--ingest <path>`,
  returns the list of pages changed. Requires `ANTHROPIC_API_KEY` env var.
  Subprocess invocation uses `asyncio.create_subprocess_exec` (argv-style,
  no shell — user-supplied filenames cannot inject).
- The compiler is bundled into the orchestrator image (Dockerfile COPYs
  `wiki-compiler/`); docker-compose mounts `./wiki:/app/wiki:ro` and
  `./raw:/app/raw:rw`.
- The `wiki.list` tool now returns a useful index (10 concepts +
  5 entities + 5 FAQs); `wiki.search` finds matches across all pages;
  `wiki.open` retrieves any individual page. Workshop attendees with
  the 📚 Wiki toggle can ask "What is NodeAva?" and get a coherent
  answer from the agentic loop.
```

- [ ] **Step 4: Commit**

```bash
git add services/wiki-compiler/README.md services/orchestrator/README.md CLAUDE.md
git commit -m "docs: document wiki preload + /v1/ingest endpoint"
```

---

## Final verification (manual)

Before declaring Plan #6 complete:

- [ ] **A1. Wiki content quality.** Open these pages directly and read them. Each should answer its title clearly and concretely:
  - `wiki/concepts/nodeava-overview.md` — does it explain what NodeAva is in one paragraph?
  - `wiki/concepts/pipeline-architecture.md` — does it describe the STT → LLM → TTS flow?
  - `wiki/concepts/agentic-loop.md` — does it describe how tool calls cascade?
  - `wiki/entities/qwen3-4b.md` — does it name Qwen3-4B specifically and its role?
  - `wiki/faqs/system-requirements.md` — does it cite the 8 GB GPU floor?
  - `wiki/index.md` — does it list all 20+ pages organized by category?

- [ ] **A2. Wiki tool round-trip via the orchestrator + agentic loop.** Bring up the stack with the API key:

```bash
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml \
  up -d llm orchestrator searxng

# Wait for healthy
until [ "$(docker inspect nodeava-orch --format '{{.State.Health.Status}}')" = "healthy" ]; do sleep 2; done

# Ask the wiki
curl -N -X POST http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is NodeAva and how does it work? Use the wiki, be brief."}],"wiki":true,"stream":true,"max_tokens":400}' \
  > /tmp/wiki-qa.txt

# Check for tool calls
grep "event: tool_call_start" /tmp/wiki-qa.txt
# Check for final content
grep -A 1 "content" /tmp/wiki-qa.txt | tail -20
```

Expected: at least one `tool_call_start` with `wiki.list` or `wiki.search`, and the final synthesized response should reference real NodeAva facts (Qwen3, Kokoro, etc.).

- [ ] **A3. Ingest endpoint smoke test.** Drop a small file in:

```bash
cat > /tmp/notes.md <<'EOF'
# My Own Notes

NodeAva is awesome. The avatar's name is Ava and she uses Kokoro for TTS.
EOF

curl -X POST http://localhost:8082/v1/ingest -F file=@/tmp/notes.md
```

Expected: `{"ok": true, "pages_changed": [...]}` after ~10-30s. Inspect `wiki/sources/` — there should be a new `notes-md.md` page (or similar).

- [ ] **A4. Tear down**

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml down
```

If anything in A1-A3 fails, that's a real bug. Fix before declaring complete.

---

## What comes next (Plan #7)

Plan #7 adds the **command center backend + CLI parity scripts** — the workshop's "spinal cord" for letting attendees swap models, voices, avatars, and presets either through a UI (Plan #8) or shell scripts (Plan #7). Plan #7 ships the API routes + the matching `scripts/swap-*.sh` so attendees can choose their own track (UI or CLI) for the workshop.
