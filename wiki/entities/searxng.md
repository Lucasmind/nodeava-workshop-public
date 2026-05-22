# SearXNG (Search Engine)

SearXNG is an open-source meta-search engine that aggregates results from multiple upstream search providers without tracking users or logging queries. In NodeAva, it runs as a bundled Docker service and acts as the backend for the [[browser-tools]] `browser.search` tool, giving the agentic loop access to live web search results without requiring any external API keys.

## Role in NodeAva

The [[orchestrator]] calls SearXNG whenever the model invokes `browser.search` during an agentic tool loop. The orchestrator is configured with `SEARXNG_URL=http://searxng:8080`, resolved via Docker internal DNS. SearXNG is not exposed to the host machine — it binds to `0.0.0.0` inside the container but remains on the internal Docker network only. The `browser.search` tool queries the JSON endpoint and returns the top results as numbered text back into the conversation.

## Configuration

The workshop configuration lives at `configs/searxng/settings.yml`. Key settings:

- **Instance name:** NodeAva Workshop SearXNG
- **Internal URL:** `http://searxng:8080/`
- **Formats enabled:** `html` and `json`. The `json` format is required by `browser.search`; default SearXNG installations enable only `html`, so this override is critical.
- **Safe search:** disabled (`safe_search: 0`)
- **Image proxy:** disabled
- **Request timeout:** 10 seconds, hard cap at 15 seconds
- **Metrics:** disabled
- **Limiter:** enabled

The `secret_key` in the shipped config is `workshop-default-secret-please-rotate`. For any deployment beyond a local workshop machine, generate a replacement with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

and substitute it in `configs/searxng/settings.yml`. See the [[orchestrator]] deployment notes for context on why the risk is low for localhost-only use.

## Relationship to Other Services

SearXNG is consumed exclusively by the orchestrator's browser tool family. The [[orchestrator]] also hosts `browser.open` and `browser.find`, which operate on fetched page content rather than search results. SearXNG handles only the initial query step. The [[llm-backend]] and [[avatar]] have no direct connection to SearXNG.

## Upstream

SearXNG is maintained at `https://github.com/searxng/searxng` under the AGPL-3.0 license. NodeAva uses the official Docker image without modification; all NodeAva-specific behavior is expressed through `settings.yml` overrides.
