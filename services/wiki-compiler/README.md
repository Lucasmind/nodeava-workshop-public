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
2. Re-run `python compile_wiki.py`.
3. Review the generated page in `wiki/<category>/<slug>.md`.
4. Commit if happy.

## Ingest pipeline

`POST /v1/ingest` (multipart upload of a file) → the orchestrator writes
it to `raw/uploads/<filename>` → invokes the compiler as a subprocess
via `asyncio.create_subprocess_exec` (NOT shell-string exec — filenames
are passed as a list element so user-supplied names can't inject) → the
compiler writes a new summary page to `wiki/sources/<slug>.md` and
regenerates `wiki/index.md`. Existing concept pages are not modified.

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
out total). Per-ingest: typically ~$0.05 (one new sources/ page + one
regenerated index). Plan #10 may add a per-user cost limiter.
