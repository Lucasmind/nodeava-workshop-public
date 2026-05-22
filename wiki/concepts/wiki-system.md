# The Wiki System

NodeAva's wiki is a directory of plain Markdown files on disk that serves as the system's self-knowledge base — a structured record of what NodeAva is, how it works, and what it has ingested. The [[orchestrator]] reads from it at runtime to answer questions about the system, and workshop attendees read it directly as documentation.

## Directory Layout

The wiki lives at `wiki/` in the repository root, controlled by `Settings.wiki_dir`. Its structure is fixed:

```
wiki/
  index.md          — one-line summary of every page (the retrieval index)
  log.md            — activity timeline
  concepts/         — how things work (e.g. concepts/tts.md)
  entities/         — specific named things (models, services, people)
  sources/          — summaries of ingested source files
  comparisons/      — side-by-side analysis pages
```

Every page is a plain `.md` file. There are no vector embeddings and no chunking. The retrieval mechanism is `index.md`: the agent calls `wiki.list` to read the full index, then calls `wiki.open` to fetch a specific page or `wiki.search` to grep across all files by substring or regex.

## Tools

Three tools in `services/orchestrator/orchestrator/tools/wiki.py` expose the wiki to the agent:

- `wiki.list` — reads `wiki/index.md` and returns its full contents.
- `wiki.open` — reads a single page by wiki-relative path (e.g. `concepts/tts.md`), with pagination via `cursor` and `num_lines` parameters. Path traversal outside the wiki root is blocked at the tool level.
- `wiki.search` — greps all `.md` files for a case-insensitive substring or regex, returning up to 30 matching lines by default (capped at 100).

## Compilation

Wiki pages are generated, not hand-written. The `services/wiki-compiler` service reads `manifest.yml`, which lists topics under three categories — `concepts`, `entities`, and `faqs` — each with a slug, a title, and a list of source files. For each topic, the compiler reads those source files, formats them into a prompt from `prompts/concept_page.txt`, `entity_page.txt`, or `faq_page.txt`, calls Anthropic Claude Sonnet 4.6 via LiteLLM, and writes the result to the appropriate subdirectory. After all pages are written, it regenerates `wiki/index.md` so `wiki.list` reflects the current state.

Compilation runs offline before the workshop ships, and again at runtime when a file is uploaded via `POST /v1/ingest`. The ingest path writes the uploaded file to `raw/uploads/<filename>`, then invokes the compiler as a subprocess using `asyncio.create_subprocess_exec` with filenames passed as list elements to prevent shell injection. The compiler writes a new summary page to `wiki/sources/<slug>.md` and regenerates `wiki/index.md`. Existing concept pages are not modified.

A full compilation costs approximately $0.60 with Sonnet 4.6. The compiler supports a `--dry-run` flag that validates `manifest.yml` without making API calls.

## Relationship to the Agent

The wiki is the agent's primary source of ground truth about NodeAva itself. When a user asks how [[text-to-speech]] works or what models are in use, the [[orchestrator]] consults the wiki rather than relying on its training data. This keeps answers accurate to the actual local deployment rather than to some generic description of the system.
