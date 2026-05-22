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
