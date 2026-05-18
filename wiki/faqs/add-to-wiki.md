# How do I add my own knowledge to the wiki?

NodeAva's wiki is compiled from a manifest file, and adding a new topic means registering it there and re-running the compiler.

1. Open `services/wiki-compiler/manifest.yml` and add an entry under the appropriate category (`concepts`, `entities`, or `faqs`):

```yaml
- slug: my-new-topic
  title: My New Topic
  sources:
    - path/to/source/file.js
    - docs/relevant-notes.md
```

2. Run the compiler from the repo root:

```bash
export ANTHROPIC_API_KEY=...
cd services/wiki-compiler
python compile_wiki.py
```

3. Review the generated page at `wiki/<category>/my-new-topic.md`.

4. Commit the file if the output looks correct.

The compiler reads the listed source files, sends them to Anthropic Sonnet 4.6 via LiteLLM, and writes the resulting page. It also regenerates `wiki/index.md` so the agent's `wiki.list` tool reflects the new entry immediately.

To add knowledge at runtime without editing the manifest, use the ingest endpoint: `POST /v1/ingest` with a multipart file upload. The orchestrator writes the file to `raw/uploads/` and invokes the compiler as a subprocess, which creates a summary page and updates any concept pages that reference the uploaded content.

See [[wiki-compiler]] for full compilation options and [[orchestrator]] for details on the ingest endpoint.
