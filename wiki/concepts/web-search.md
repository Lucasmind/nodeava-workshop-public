# How NodeAva Searches the Web

NodeAva performs live web searches through a three-tool browser pipeline backed by a bundled SearXNG meta-search engine, all running locally inside the Docker network. When a user's request requires current information, the [[orchestrator]] injects these tools into the model's context, and the agentic loop handles the back-and-forth between the model and the web automatically.

## The three browser tools

**browser.search** sends a query to the local SearXNG instance at `http://searxng:8080` and returns up to twenty numbered results, each containing a title, URL, and snippet. The default is five results. SearXNG must have the JSON format enabled in `configs/searxng/settings.yml` — the orchestrator calls the `/search` endpoint with `format=json`, which is not enabled by default in SearXNG and is explicitly added in NodeAva's config.

**browser.open** fetches a URL, extracts readable text, caches the result in an in-process LRU, and returns a paginated slice of lines. It uses `trafilatura` for reader-mode extraction, falling back to BeautifulSoup if trafilatura returns nothing. The tool streams the response body incrementally and enforces a 5 MB cap (`MAX_FETCH_BYTES`). Pages are returned in windows of up to 500 lines, with a `cursor` parameter to page through longer content.

**browser.find** searches a previously-opened page for a regex or substring pattern without re-fetching. It targets the most recently cached page by default, or an explicit URL if provided. Invalid regex patterns fall back to case-insensitive substring matching.

All three tools share a `PageCache` so `browser.find` can operate on whatever `browser.open` last fetched. The implementation lives in `services/orchestrator/orchestrator/tools/browser.py`.

## Security guards on browser.open

Two guards run before any HTTP request is made. First, an SSRF check resolves the target hostname and rejects it if the resulting IP falls in loopback (`127.0.0.0/8`), private (`10/8`, `172.16/12`, `192.168/16`), link-local (`169.254/16`), reserved, unspecified, or multicast ranges. This prevents the model from being directed at cloud-metadata endpoints or internal Docker services. Second, responses advertising a `Content-Length` above 5 MB are refused before downloading begins, and streaming reads are cut off if the body exceeds that limit mid-transfer.

## How the orchestrator triggers web search

Web search is opt-in per request. Sending `"web_search": true` in the request body to the orchestrator at `http://localhost:8082/v1/chat/completions` injects the `browser.*` tools into the model's tool list. The [[agentic-loop]] then runs: when the model emits tool calls, the orchestrator executes them, appends results to the conversation, and re-prompts until the model produces a final answer or the eight-round limit is reached.

## SearXNG configuration

SearXNG runs as a Docker service on the internal network at `http://searxng:8080` and is not exposed to the host. Its configuration is at `configs/searxng/settings.yml`. The `secret_key` field ships as `workshop-default-secret-please-rotate` and must be replaced before any non-localhost deployment. The `formats` list must include `json` or `browser.search` will fail.

## Related pages

- [[orchestrator]] — the service that hosts the browser tools and agentic loop
- [[agentic-loop]] — how the model and tools iterate toward a final answer
- [[wiki-tools]] — the filesystem-backed counterpart to browser tools
