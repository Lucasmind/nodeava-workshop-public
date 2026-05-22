# nodeava-orch Tools Registry Implementation Plan (Plan #3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pluggable tool registry to `nodeava-orch` and ship two tool families: **browser** tools (`browser.search`, `browser.open`, `browser.find`) backed by a bundled SearXNG container, and **wiki** tools (`wiki.list`, `wiki.search`, `wiki.open`) backed by a filesystem-only Karpathy-style wiki. Tools are callable in isolation via a new `POST /v1/tools/{name}` endpoint added strictly for testability — Plan #4 will delete that endpoint once the agentic loop consumes tools internally.

**Architecture:** Tools register against a module-level singleton registry. Each tool subclasses `Tool` (name + JSON-Schema + async `execute(args) -> str`). Browser tools share a single in-process LRU page cache so `browser.find` can operate on the most-recently-opened page from a prior `browser.open`. The wiki tools take a configurable wiki directory path (default: repo-root `wiki/`) and do pure filesystem operations — grep, paginated read, index lookup. No vector embeddings; this is **maintained-knowledge-base RAG**, not query-time-retrieval RAG, per the Karpathy design covered in the spec.

**Tech Stack:**
- New deps: `trafilatura>=2.0,<3.0` (page text extraction), `beautifulsoup4==4.13.*` (fallback HTML parser)
- New service: `searxng/searxng:latest` Docker container (no Redis for v1 — SearXNG's built-in limiter is fine at workshop scale)
- Everything else from Plans #1-#2

**Working directory:** `/media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec`. All paths repo-relative.

**Branch:** `worktree-workshop-mvp-spec` (now tracking `workshop/main`, the private repo).

---

## Task 1: Add `trafilatura` + `beautifulsoup4` deps

**Files:**
- Modify: `services/orchestrator/requirements.txt`

- [ ] **Step 1: Edit `services/orchestrator/requirements.txt`**

Replace entire contents with:

```
fastapi==0.115.*
uvicorn[standard]==0.34.*
httpx==0.28.*
pydantic==2.*
pydantic-settings==2.*
litellm>=1.50,<2.0
trafilatura>=2.0,<3.0
beautifulsoup4==4.13.*
```

- [ ] **Step 2: Install and verify Plan #1+#2 tests still pass**

```bash
cd services/orchestrator && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pytest -q
```

Expected: `40 passed`.

If trafilatura's transitive deps (lxml, justext) fail to install on this machine, BLOCK and report — they may need a system-level libxml2-dev package. We don't fix that here.

- [ ] **Step 3: Commit**

```bash
cd ../..
git add services/orchestrator/requirements.txt
git commit -m "feat(orch): add trafilatura + beautifulsoup4 deps"
```

---

## Task 2: Extend `Settings` with `searxng_url` + `wiki_dir`

**Files:**
- Modify: `services/orchestrator/orchestrator/config.py`
- Modify: `services/orchestrator/tests/test_config.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_config.py`**

```python
def test_tools_settings_defaults(monkeypatch):
    """SearXNG defaults to the Docker DNS name; wiki defaults to repo-root wiki/."""
    for k in ("SEARXNG_URL", "WIKI_DIR"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.searxng_url == "http://searxng:8080"
    assert s.wiki_dir == "wiki"


def test_tools_settings_env_override(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8888")
    monkeypatch.setenv("WIKI_DIR", "/var/lib/workshop/wiki")
    s = Settings()
    assert s.searxng_url == "http://localhost:8888"
    assert s.wiki_dir == "/var/lib/workshop/wiki"
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_config.py -v
```

Expected: AttributeError on missing fields.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/config.py` entirely with:**

```python
"""Runtime settings loaded from env vars."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orchestrator runtime settings.

    Default `bind_host` is 127.0.0.1 (localhost-only) — see the workshop
    MVP spec for the security rationale. LAN exposure requires explicit
    BIND_HOST=0.0.0.0 plus auth (added in a later plan).

    Provider defaults (`provider`, `provider_model`) are the DEPLOY-TIME
    default. Per-request body fields (`provider`, `model`) and headers
    (`X-Provider-Key`) override these — see orchestrator.providers.pick_provider.

    Tool defaults (`searxng_url`, `wiki_dir`) — Plan #3. SearXNG default
    points at the bundled container's Docker DNS name. Wiki dir is the
    on-disk Karpathy-style wiki the agent reads.
    """

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    llama_url: str = "http://localhost:8081"
    request_timeout: float = 300.0
    bind_host: str = "127.0.0.1"
    bind_port: int = 8082

    # Provider selection — Plan #2
    provider: str = "local"
    provider_model: str = ""

    # Tools — Plan #3
    searxng_url: str = "http://searxng:8080"
    wiki_dir: str = "wiki"
```

- [ ] **Step 4: Run all config tests**

```bash
pytest tests/test_config.py -v
```

Expected: 6 PASS (4 prior + 2 new).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): Settings.searxng_url + wiki_dir"
```

---

## Task 3: `Tool` ABC + `ToolError`

**Files:**
- Create: `services/orchestrator/orchestrator/tools/base.py`
- Create: `services/orchestrator/tests/test_tools_registry.py` *(yes, this filename — the next task adds the actual registry to it; we start the test file now with just the base-class tests)*

- [ ] **Step 1: Create `services/orchestrator/tests/test_tools_registry.py`**

```python
"""Tests for the Tool ABC and the registry."""
import pytest

from orchestrator.tools.base import Tool, ToolError


class _Echo(Tool):
    name = "test.echo"
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, args: dict) -> str:
        return f"echo: {args.get('text', '')}"


async def test_tool_subclass_concrete_executes():
    """A concrete subclass with name+schema+execute can be instantiated and run."""
    t = _Echo()
    out = await t.execute({"text": "hello"})
    assert out == "echo: hello"
    assert t.name == "test.echo"
    assert t.schema["properties"]["text"]["type"] == "string"


def test_tool_subclass_without_execute_raises():
    """ABC enforces execute() — concrete class missing it can't instantiate."""

    class _Bad(Tool):
        name = "test.bad"
        schema = {}

    with pytest.raises(TypeError):
        _Bad()  # type: ignore[abstract]


def test_tool_error_is_an_exception():
    """ToolError is an Exception that tools raise on user-fixable failures."""
    e = ToolError("bad input")
    assert isinstance(e, Exception)
    assert str(e) == "bad input"
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_tools_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator.tools'`.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/tools/__init__.py`**

```python
"""Tool abstraction — pluggable functions the agent can call.

Plan #3 introduces:
  - Tool ABC + registry (this package)
  - Browser tools (browser.py)
  - Wiki tools (wiki.py)

Plan #4 will consume the registry from the agentic loop in the chat
completions route. Until then, tools are callable in isolation via
the test endpoint at POST /v1/tools/{name}.
"""
```

Create `services/orchestrator/orchestrator/tools/base.py`:

```python
"""Tool abstract base class.

A Tool has:
  - `name` (class attr): the dotted identifier the agent / route uses (e.g. "browser.search")
  - `schema` (class attr): JSON-Schema object describing the args
  - `execute(args)`: async method that does the work and returns a string

Tools should raise `ToolError` on user-fixable failures (bad URL, missing
file, etc.) — the route layer catches these and returns a 400 with the
message. Anything else propagates as a 500.
"""
from abc import ABC, abstractmethod
from typing import Any, ClassVar


class ToolError(Exception):
    """Raised when a tool fails due to bad input or expected runtime conditions
    (e.g. site returned 403, wiki page not found). The route layer translates
    this into a 400 response with the error message in the body."""


class Tool(ABC):
    """Abstract pluggable tool."""

    # Each subclass MUST override both of these as class attributes.
    name: ClassVar[str] = ""
    schema: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    async def execute(self, args: dict[str, Any]) -> str:
        """Run the tool and return a string result."""
        ...

    def to_openai_function(self) -> dict[str, Any]:
        """Render this tool as an OpenAI-tools function definition.

        Plan #4 will use this to inject the tools into chat completions
        requests. Plan #3 doesn't call this — but having it ready keeps
        the contract explicit.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (self.__class__.__doc__ or "").strip().split("\n")[0],
                "parameters": self.schema,
            },
        }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools_registry.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): Tool ABC + ToolError"
```

---

## Task 4: Tool registry (register / get / list)

**Files:**
- Modify: `services/orchestrator/orchestrator/tools/__init__.py`
- Modify: `services/orchestrator/tests/test_tools_registry.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_tools_registry.py`**

```python
from orchestrator.tools import register, get, list_tools, _clear_registry_for_tests


@pytest.fixture(autouse=True)
def _reset_registry():
    """Each test runs against a fresh registry."""
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


def test_register_and_get():
    tool = _Echo()
    register(tool)
    assert get("test.echo") is tool


def test_get_unknown_raises_tool_error():
    with pytest.raises(ToolError) as exc:
        get("does.not.exist")
    assert "does.not.exist" in str(exc.value)


def test_list_tools_returns_all_registered():
    register(_Echo())

    class _Other(Tool):
        name = "test.other"
        schema = {"type": "object"}

        async def execute(self, args):
            return "ok"

    register(_Other())
    names = sorted(t.name for t in list_tools())
    assert names == ["test.echo", "test.other"]


def test_register_duplicate_replaces():
    """Registering the same name twice replaces — useful for tests/hot-reload."""
    register(_Echo())
    second = _Echo()
    register(second)
    assert get("test.echo") is second
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_tools_registry.py -v
```

Expected: ImportError on `register, get, list_tools, _clear_registry_for_tests`.

- [ ] **Step 3: Replace `services/orchestrator/orchestrator/tools/__init__.py` entirely:**

```python
"""Tool abstraction — pluggable functions the agent can call.

Plan #3 introduces:
  - Tool ABC + registry (this package)
  - Browser tools (browser.py)
  - Wiki tools (wiki.py)

Plan #4 will consume the registry from the agentic loop in the chat
completions route. Until then, tools are callable in isolation via
the test endpoint at POST /v1/tools/{name}.
"""
from orchestrator.tools.base import Tool, ToolError

__all__ = ["Tool", "ToolError", "register", "get", "list_tools"]


_registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Register a tool, replacing any previous tool of the same name.

    Replacement-on-conflict is intentional — it supports test reset and
    swap-at-runtime patterns that Plan #4's agentic loop relies on.
    """
    if not tool.name:
        raise ToolError("Tool.name must be non-empty")
    _registry[tool.name] = tool


def get(name: str) -> Tool:
    """Return the tool registered under `name`, or raise ToolError if absent."""
    if name not in _registry:
        raise ToolError(f"unknown tool: {name!r}")
    return _registry[name]


def list_tools() -> list[Tool]:
    """Return all registered tools in arbitrary order. Callers sort if needed."""
    return list(_registry.values())


def _clear_registry_for_tests() -> None:
    """Test helper — never call from production code."""
    _registry.clear()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools_registry.py -v
```

Expected: 7 PASS (3 base + 4 registry).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): tool registry (register/get/list)"
```

---

## Task 5: LRU page cache (in-process)

**Files:**
- Create: `services/orchestrator/orchestrator/tools/cache.py`
- Create: `services/orchestrator/tests/test_tools_cache.py`

The cache holds extracted pages so that `browser.find` can operate on a recently-opened page without re-fetching. LRU semantics — when full, drop the least-recently-used entry. Returns the URL of the most-recently-cached page for `browser.find` fallback.

- [ ] **Step 1: Create `services/orchestrator/tests/test_tools_cache.py`**

```python
"""Tests for the LRU page cache."""
import pytest

from orchestrator.tools.cache import PageCache


def test_put_and_get():
    c = PageCache(max_size=3)
    c.put("https://a.example", {"title": "A", "lines": ["a1", "a2"]})
    page = c.get("https://a.example")
    assert page["title"] == "A"


def test_get_unknown_returns_none():
    c = PageCache(max_size=3)
    assert c.get("https://missing.example") is None


def test_lru_eviction_drops_least_recently_used():
    c = PageCache(max_size=2)
    c.put("https://a.example", {"title": "A"})
    c.put("https://b.example", {"title": "B"})
    # Re-access "a" so "b" becomes LRU.
    c.get("https://a.example")
    c.put("https://c.example", {"title": "C"})
    assert c.get("https://b.example") is None
    assert c.get("https://a.example") is not None
    assert c.get("https://c.example") is not None


def test_most_recent_url_tracks_inserts():
    c = PageCache(max_size=3)
    assert c.most_recent_url() is None
    c.put("https://a.example", {"title": "A"})
    assert c.most_recent_url() == "https://a.example"
    c.put("https://b.example", {"title": "B"})
    assert c.most_recent_url() == "https://b.example"


def test_most_recent_url_tracks_gets():
    """Calling get() refreshes recency — most_recent_url reflects last access."""
    c = PageCache(max_size=3)
    c.put("https://a.example", {"title": "A"})
    c.put("https://b.example", {"title": "B"})
    c.get("https://a.example")
    assert c.most_recent_url() == "https://a.example"
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_tools_cache.py -v
```

Expected: ImportError on `orchestrator.tools.cache`.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/tools/cache.py`**

```python
"""LRU page cache shared by browser tools.

`browser.open` stores extracted pages here. `browser.find` consults the
most-recently-used entry when called without an explicit URL — that's
the common pattern from the LLMRunners orchestrator we're modeled on.

In-process and process-local. A future plan may move this to Redis for
cross-restart durability; not in scope here.
"""
from collections import OrderedDict
from typing import Any


class PageCache:
    """A bounded LRU cache of fetched-and-extracted web pages.

    Stored values are plain dicts with whatever shape browser.py wants
    (typically {"title": str, "url": str, "text": str, "lines": list[str]}).
    The cache itself only cares about LRU recency.
    """

    def __init__(self, max_size: int = 20) -> None:
        self._max_size = max_size
        self._store: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def put(self, url: str, page: dict[str, Any]) -> None:
        if url in self._store:
            del self._store[url]
        self._store[url] = page
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def get(self, url: str) -> dict[str, Any] | None:
        if url not in self._store:
            return None
        # refresh recency
        self._store.move_to_end(url)
        return self._store[url]

    def most_recent_url(self) -> str | None:
        if not self._store:
            return None
        return next(reversed(self._store))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools_cache.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): LRU page cache for browser tools"
```

---

## Task 6: `browser.search` (SearXNG JSON API)

**Files:**
- Create: `services/orchestrator/orchestrator/tools/browser.py`
- Create: `services/orchestrator/tests/test_tools_browser.py`

- [ ] **Step 1: Create `services/orchestrator/tests/test_tools_browser.py`**

```python
"""Tests for browser tools."""
import respx
from httpx import Response

from orchestrator.tools.browser import BrowserSearch
from orchestrator.tools.cache import PageCache


@respx.mock
async def test_search_returns_formatted_results():
    """browser.search hits SearXNG JSON API and formats top-N results
    as a numbered text block the LLM can read."""
    respx.get("http://searxng:8080/search").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "title": "Linux kernel 6.13 released",
                        "url": "https://example.com/a",
                        "content": "The Linux kernel team announced...",
                    },
                    {
                        "title": "Mainline merges new scheduler",
                        "url": "https://example.com/b",
                        "content": "EEVDF replaces CFS in v6.6+...",
                    },
                ]
            },
        )
    )

    tool = BrowserSearch(searxng_url="http://searxng:8080", cache=PageCache())
    out = await tool.execute({"query": "linux kernel", "topn": 5})
    assert "[1] Linux kernel 6.13 released" in out
    assert "https://example.com/a" in out
    assert "[2] Mainline merges new scheduler" in out


@respx.mock
async def test_search_empty_results():
    respx.get("http://searxng:8080/search").mock(
        return_value=Response(200, json={"results": []})
    )
    tool = BrowserSearch(searxng_url="http://searxng:8080", cache=PageCache())
    out = await tool.execute({"query": "asdfqwerzxcv12345"})
    assert "No results" in out


@respx.mock
async def test_search_backend_error_raises_tool_error():
    """A 5xx from SearXNG becomes a ToolError (becomes 400 in the route)."""
    import httpx
    from orchestrator.tools.base import ToolError

    respx.get("http://searxng:8080/search").mock(
        return_value=Response(500, text="oops")
    )
    tool = BrowserSearch(searxng_url="http://searxng:8080", cache=PageCache())
    import pytest

    with pytest.raises(ToolError):
        await tool.execute({"query": "anything"})


@respx.mock
async def test_search_truncates_to_topn():
    """topn arg caps the number of results returned."""
    results = [
        {"title": f"Title {i}", "url": f"https://example.com/{i}", "content": f"Snippet {i}"}
        for i in range(10)
    ]
    respx.get("http://searxng:8080/search").mock(
        return_value=Response(200, json={"results": results})
    )

    tool = BrowserSearch(searxng_url="http://searxng:8080", cache=PageCache())
    out = await tool.execute({"query": "x", "topn": 3})
    # Three result blocks → headers numbered 1, 2, 3 — no [4]
    assert "[1] Title 0" in out
    assert "[3] Title 2" in out
    assert "[4]" not in out
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_tools_browser.py -v
```

Expected: ImportError on `orchestrator.tools.browser`.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/tools/browser.py`** (this file will grow in Tasks 7 + 8 — start with just `BrowserSearch`):

```python
"""Browser tools — search/open/find against the live web via SearXNG + httpx.

Three tools share a PageCache so `browser.find` can target the last page
opened by `browser.open` without a re-fetch.
"""
import logging
from typing import Any

import httpx

from orchestrator.tools.base import Tool, ToolError
from orchestrator.tools.cache import PageCache

log = logging.getLogger("orchestrator.tools.browser")


class BrowserSearch(Tool):
    """Search the web via the bundled SearXNG meta-search engine."""

    name = "browser.search"
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "topn": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, searxng_url: str, cache: PageCache, timeout: float = 30.0) -> None:
        self._searxng_url = searxng_url.rstrip("/")
        self._cache = cache
        self._timeout = timeout

    async def execute(self, args: dict[str, Any]) -> str:
        query = args.get("query") or ""
        if not query:
            raise ToolError("browser.search requires a non-empty 'query'")
        try:
            topn = int(args.get("topn", 5))
        except (TypeError, ValueError):
            topn = 5
        topn = max(1, min(topn, 20))

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._searxng_url}/search",
                    params={"q": query, "format": "json", "pageno": 1},
                )
        except httpx.HTTPError as e:
            raise ToolError(f"SearXNG unreachable: {e}") from e

        if resp.status_code >= 400:
            raise ToolError(f"SearXNG returned HTTP {resp.status_code}")

        data = resp.json()
        results = data.get("results") or []
        if not results:
            return f"No results for: {query}"

        chunks: list[str] = []
        for i, r in enumerate(results[:topn], start=1):
            title = r.get("title") or "(no title)"
            url = r.get("url") or ""
            snippet = r.get("content") or "(no snippet)"
            chunks.append(f"[{i}] {title}\n    URL: {url}\n    {snippet}")
        return "\n\n".join(chunks)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): browser.search tool (SearXNG JSON API)"
```

---

## Task 7: `browser.open` (httpx fetch + trafilatura extract + cache)

**Files:**
- Modify: `services/orchestrator/orchestrator/tools/browser.py`
- Modify: `services/orchestrator/tests/test_tools_browser.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_tools_browser.py`**

```python
from orchestrator.tools.browser import BrowserOpen


@respx.mock
async def test_open_fetches_extracts_caches_and_paginates():
    """browser.open: GET the URL, run trafilatura, cache, return first
    `num_lines` lines with a Title/URL/range header."""
    html = """
    <html><head><title>About NodeAva</title></head>
    <body>
    <h1>NodeAva</h1>
    <p>NodeAva is a self-hosted digital human stack.</p>
    <p>It combines llama.cpp, Kokoro TTS, and Whisper STT.</p>
    <p>The avatar is rendered with TalkingHead and Three.js.</p>
    </body></html>
    """
    respx.get("https://example.com/nodeava").mock(
        return_value=Response(200, html=html, headers={"content-type": "text/html"})
    )

    cache = PageCache()
    tool = BrowserOpen(cache=cache)
    out = await tool.execute({"id": "https://example.com/nodeava", "num_lines": 10})
    assert "Title: About NodeAva" in out
    assert "URL: https://example.com/nodeava" in out
    assert "self-hosted digital human" in out
    # Caches by URL — subsequent get returns the parsed page.
    assert cache.get("https://example.com/nodeava") is not None


@respx.mock
async def test_open_paginates_via_cursor():
    """A subsequent call with cursor>0 returns the next slice without re-fetching."""
    long_html = "<html><body>" + "".join(f"<p>line {i}</p>" for i in range(50)) + "</body></html>"
    route = respx.get("https://example.com/long").mock(
        return_value=Response(200, html=long_html, headers={"content-type": "text/html"})
    )

    cache = PageCache()
    tool = BrowserOpen(cache=cache)
    page1 = await tool.execute({"id": "https://example.com/long", "num_lines": 5, "cursor": 0})
    page2 = await tool.execute({"id": "https://example.com/long", "num_lines": 5, "cursor": 5})

    # Only one upstream fetch — second call served from cache.
    assert route.call_count == 1
    assert "Lines 1-5 of" in page1
    assert "Lines 6-10 of" in page2


@respx.mock
async def test_open_http_error_raises_tool_error():
    """A 403/404/500 from the target site becomes a ToolError."""
    from orchestrator.tools.base import ToolError
    import pytest

    respx.get("https://blocked.example/page").mock(
        return_value=Response(403, text="forbidden")
    )
    tool = BrowserOpen(cache=PageCache())
    with pytest.raises(ToolError) as exc:
        await tool.execute({"id": "https://blocked.example/page"})
    assert "403" in str(exc.value)


async def test_open_requires_url_arg():
    from orchestrator.tools.base import ToolError
    import pytest

    tool = BrowserOpen(cache=PageCache())
    with pytest.raises(ToolError):
        await tool.execute({})
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: ImportError on `BrowserOpen`.

- [ ] **Step 3: Append to `services/orchestrator/orchestrator/tools/browser.py`** the `BrowserOpen` class. The full file should now be:

```python
"""Browser tools — search/open/find against the live web via SearXNG + httpx.

Three tools share a PageCache so `browser.find` can target the last page
opened by `browser.open` without a re-fetch.
"""
import logging
from typing import Any

import httpx
import trafilatura
from bs4 import BeautifulSoup

from orchestrator.tools.base import Tool, ToolError
from orchestrator.tools.cache import PageCache

log = logging.getLogger("orchestrator.tools.browser")


_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BrowserSearch(Tool):
    """Search the web via the bundled SearXNG meta-search engine."""

    name = "browser.search"
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "topn": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, searxng_url: str, cache: PageCache, timeout: float = 30.0) -> None:
        self._searxng_url = searxng_url.rstrip("/")
        self._cache = cache
        self._timeout = timeout

    async def execute(self, args: dict[str, Any]) -> str:
        query = args.get("query") or ""
        if not query:
            raise ToolError("browser.search requires a non-empty 'query'")
        try:
            topn = int(args.get("topn", 5))
        except (TypeError, ValueError):
            topn = 5
        topn = max(1, min(topn, 20))

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._searxng_url}/search",
                    params={"q": query, "format": "json", "pageno": 1},
                )
        except httpx.HTTPError as e:
            raise ToolError(f"SearXNG unreachable: {e}") from e

        if resp.status_code >= 400:
            raise ToolError(f"SearXNG returned HTTP {resp.status_code}")

        data = resp.json()
        results = data.get("results") or []
        if not results:
            return f"No results for: {query}"

        chunks: list[str] = []
        for i, r in enumerate(results[:topn], start=1):
            title = r.get("title") or "(no title)"
            url = r.get("url") or ""
            snippet = r.get("content") or "(no snippet)"
            chunks.append(f"[{i}] {title}\n    URL: {url}\n    {snippet}")
        return "\n\n".join(chunks)


class BrowserOpen(Tool):
    """Fetch a URL, extract readable text, cache the result, return a slice."""

    name = "browser.open"
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "URL to open"},
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to return",
                "default": 120,
            },
            "cursor": {
                "type": "integer",
                "description": "Line offset to start from (0 = top of page)",
                "default": 0,
            },
        },
        "required": ["id"],
    }

    def __init__(self, *, cache: PageCache, timeout: float = 30.0) -> None:
        self._cache = cache
        self._timeout = timeout

    async def execute(self, args: dict[str, Any]) -> str:
        url = args.get("id") or args.get("url") or ""
        if not url:
            raise ToolError("browser.open requires 'id' (the URL)")

        try:
            num_lines = int(args.get("num_lines", 120))
        except (TypeError, ValueError):
            num_lines = 120
        num_lines = max(1, min(num_lines, 500))

        try:
            cursor = int(args.get("cursor", 0))
        except (TypeError, ValueError):
            cursor = 0
        cursor = max(0, cursor)

        cached = self._cache.get(url)
        if cached is None:
            cached = await self._fetch_and_extract(url)
            self._cache.put(url, cached)

        lines: list[str] = cached["lines"]
        total = len(lines)
        end = min(cursor + num_lines, total)
        selected = lines[cursor:end]
        header = (
            f"Title: {cached['title']}\n"
            f"URL: {url}\n"
            f"Lines {cursor + 1}-{end} of {total}\n"
            f"---\n"
        )
        return header + "\n".join(selected)

    async def _fetch_and_extract(self, url: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=self._timeout
            ) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    },
                )
        except httpx.HTTPError as e:
            raise ToolError(f"failed to fetch {url}: {e}") from e

        if resp.status_code >= 400:
            log.warning("HTTP %d fetching %s", resp.status_code, url)
            raise ToolError(
                f"HTTP {resp.status_code} fetching {url}. "
                "The site may block automated access."
            )

        html = resp.text

        # Prefer trafilatura's reader-mode extraction; fall back to BS4 if it
        # returns nothing (rare, but trafilatura sometimes whiffs on tiny pages).
        text = trafilatura.extract(html) or ""
        if not text:
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)

        title = ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception:
            title = ""

        lines = [line for line in text.split("\n") if line.strip()]
        return {"title": title, "url": url, "text": text, "lines": lines}
```

- [ ] **Step 4: Run all browser tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: 8 PASS (4 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): browser.open tool (fetch + trafilatura + cache)"
```

---

## Task 8: `browser.find` (regex over most-recently-opened page)

**Files:**
- Modify: `services/orchestrator/orchestrator/tools/browser.py`
- Modify: `services/orchestrator/tests/test_tools_browser.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_tools_browser.py`**

```python
from orchestrator.tools.browser import BrowserFind


async def test_find_searches_most_recently_opened_page():
    """browser.find finds matching lines in the MRU page from the cache."""
    cache = PageCache()
    cache.put(
        "https://example.com/page",
        {
            "title": "Page",
            "url": "https://example.com/page",
            "text": "alpha\nbeta\ngamma\nalphabet",
            "lines": ["alpha", "beta", "gamma", "alphabet"],
        },
    )
    tool = BrowserFind(cache=cache)
    out = await tool.execute({"pattern": "alpha"})
    assert "Line 1:" in out
    assert "alpha" in out
    assert "alphabet" in out
    # Substring match catches both — count 2 matches.
    assert "2 matches" in out


async def test_find_specific_url_overrides_mru():
    """If `url` is provided in args, find searches that page instead of MRU."""
    cache = PageCache()
    cache.put(
        "https://a.example/",
        {"title": "A", "url": "https://a.example/", "lines": ["apple", "ant"]},
    )
    cache.put(
        "https://b.example/",
        {"title": "B", "url": "https://b.example/", "lines": ["banana", "bear"]},
    )
    # MRU is b.example, but we override to a.example
    tool = BrowserFind(cache=cache)
    out = await tool.execute({"pattern": "ant", "url": "https://a.example/"})
    assert "https://a.example/" in out
    assert "ant" in out


async def test_find_no_matches():
    cache = PageCache()
    cache.put(
        "https://example.com/page",
        {"title": "Page", "url": "https://example.com/page", "lines": ["one", "two"]},
    )
    tool = BrowserFind(cache=cache)
    out = await tool.execute({"pattern": "nothing"})
    assert "No matches" in out


async def test_find_raises_when_no_pages_cached():
    from orchestrator.tools.base import ToolError
    import pytest

    cache = PageCache()
    tool = BrowserFind(cache=cache)
    with pytest.raises(ToolError):
        await tool.execute({"pattern": "anything"})


async def test_find_handles_invalid_regex_as_literal():
    """A non-regex pattern (e.g. unbalanced bracket) falls back to substring match."""
    cache = PageCache()
    cache.put(
        "https://example.com/page",
        {"title": "Page", "url": "https://example.com/page", "lines": ["foo[bar", "baz"]},
    )
    tool = BrowserFind(cache=cache)
    out = await tool.execute({"pattern": "[bar"})
    assert "foo[bar" in out
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: ImportError on `BrowserFind`.

- [ ] **Step 3: Append the `BrowserFind` class to `services/orchestrator/orchestrator/tools/browser.py`** (after `BrowserOpen`):

```python


class BrowserFind(Tool):
    """Search a previously-opened page for a regex or substring pattern."""

    name = "browser.find"
    schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex or substring to find. Invalid regex falls back to substring.",
            },
            "url": {
                "type": "string",
                "description": (
                    "Optional — which cached page to search. "
                    "Default: the most recently opened page."
                ),
            },
            "max_matches": {
                "type": "integer",
                "description": "Cap matches returned",
                "default": 10,
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, *, cache: PageCache) -> None:
        self._cache = cache

    async def execute(self, args: dict[str, Any]) -> str:
        import re

        pattern = args.get("pattern")
        if not pattern:
            raise ToolError("browser.find requires a 'pattern'")

        url = args.get("url") or self._cache.most_recent_url()
        if url is None:
            raise ToolError(
                "browser.find: no page is currently cached. "
                "Call browser.open first or pass an explicit url."
            )

        page = self._cache.get(url)
        if page is None:
            raise ToolError(f"browser.find: no cached page for {url}")

        try:
            max_matches = int(args.get("max_matches", 10))
        except (TypeError, ValueError):
            max_matches = 10
        max_matches = max(1, min(max_matches, 50))

        # Try regex; on syntax error fall back to literal substring.
        try:
            compiled = re.compile(pattern, re.IGNORECASE)

            def predicate(line: str) -> bool:
                return bool(compiled.search(line))
        except re.error:
            needle = pattern.lower()

            def predicate(line: str) -> bool:
                return needle in line.lower()

        matches: list[str] = []
        for i, line in enumerate(page["lines"], start=1):
            if predicate(line):
                matches.append(f"Line {i}: {line}")
                if len(matches) >= max_matches:
                    break

        if not matches:
            return f"No matches for {pattern!r} in {url}"

        return f"Found {len(matches)} matches in {url}:\n" + "\n".join(matches)
```

- [ ] **Step 4: Run all browser tests**

```bash
pytest tests/test_tools_browser.py -v
```

Expected: 13 PASS (4 search + 4 open + 5 find).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): browser.find tool (regex over MRU page)"
```

---

## Task 9: Wiki skeleton on disk

**Files:**
- Create: `wiki/index.md`
- Create: `wiki/log.md`
- Create: `wiki/concepts/.gitkeep`
- Create: `wiki/entities/.gitkeep`
- Create: `wiki/sources/.gitkeep`
- Create: `wiki/comparisons/.gitkeep`
- Create: `raw/.gitkeep`
- Modify: `.gitignore` (gitignore `raw/*` except `.gitkeep`)

This task creates the directory layout the wiki tools will operate on. The actual NodeAva self-knowledge content gets compiled in Plan #6 — for now we ship a tiny stub `index.md` plus an empty `log.md` so the wiki tools have something to read.

- [ ] **Step 1: Create `wiki/index.md`** at repo root with this content:

```markdown
# Wiki Index

A Karpathy-style LLM-maintained wiki. This index lists every page in the
wiki so the agent can find what it needs without a vector store. The agent
reads this file first when answering questions.

This is the Plan #3 stub. Plan #6 will compile the NodeAva self-knowledge
wiki — architecture, pipeline stages, model choices, command-center usage,
"how do I…" FAQs.

## Categories

- `concepts/` — concept articles (e.g. "How TTS Works")
- `entities/` — people / projects / things (e.g. "Qwen3-4B")
- `sources/` — per-source summaries (one page per ingested doc)
- `comparisons/` — side-by-side comparisons

## Pages

(empty — Plan #6 fills this)
```

- [ ] **Step 2: Create `wiki/log.md`** at repo root with this content:

```markdown
# Wiki Activity Log

Append-only timeline of wiki operations (ingests, queries, lint passes).
Plan #6 will start writing entries here.

```

- [ ] **Step 3: Create the four category dirs with `.gitkeep` placeholders**

```bash
mkdir -p wiki/concepts wiki/entities wiki/sources wiki/comparisons raw
touch wiki/concepts/.gitkeep wiki/entities/.gitkeep wiki/sources/.gitkeep wiki/comparisons/.gitkeep
touch raw/.gitkeep
```

- [ ] **Step 4: Update `.gitignore`** to ignore everything in `raw/` except `.gitkeep`

Append to repo-root `.gitignore`:

```
# Plan #6 ingest target — sources dropped here at runtime
raw/*
!raw/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add wiki/ raw/.gitkeep .gitignore
git commit -m "feat(wiki): create wiki + raw skeleton (Plan #6 fills with content)"
```

---

## Task 10: `wiki.list` tool (read `wiki/index.md`)

**Files:**
- Create: `services/orchestrator/orchestrator/tools/wiki.py`
- Create: `services/orchestrator/tests/test_tools_wiki.py`

- [ ] **Step 1: Create `services/orchestrator/tests/test_tools_wiki.py`**

```python
"""Tests for wiki tools."""
from pathlib import Path

import pytest

from orchestrator.tools.base import ToolError
from orchestrator.tools.wiki import WikiList


@pytest.fixture
def wiki_dir(tmp_path: Path) -> Path:
    """A throwaway wiki directory laid out the same as the real one."""
    (tmp_path / "index.md").write_text("# Wiki Index\n\nFake index content.\n")
    (tmp_path / "log.md").write_text("# Log\n")
    for sub in ("concepts", "entities", "sources", "comparisons"):
        (tmp_path / sub).mkdir()
    return tmp_path


async def test_list_returns_index_verbatim(wiki_dir):
    tool = WikiList(wiki_dir=str(wiki_dir))
    out = await tool.execute({})
    assert out.startswith("# Wiki Index")
    assert "Fake index content." in out


async def test_list_missing_index_raises(tmp_path: Path):
    tool = WikiList(wiki_dir=str(tmp_path))
    with pytest.raises(ToolError) as exc:
        await tool.execute({})
    assert "index.md" in str(exc.value)
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_tools_wiki.py -v
```

Expected: ImportError on `orchestrator.tools.wiki`.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/tools/wiki.py`**

```python
"""Wiki tools — read-only operations on a Karpathy-style markdown wiki.

The wiki lives in a directory on disk (Settings.wiki_dir, default
repo-root `wiki/`). It has the layout:

  wiki/
    index.md            — catalog (one-line summary per page)
    log.md              — activity timeline
    concepts/
    entities/
    sources/
    comparisons/

The agent reads index.md first (via wiki.list), then opens specific
pages (via wiki.open) or greps across them (via wiki.search). No
vector embeddings, no chunking — the index is the retrieval mechanism.
"""
import logging
import re
from pathlib import Path
from typing import Any

from orchestrator.tools.base import Tool, ToolError

log = logging.getLogger("orchestrator.tools.wiki")


class WikiList(Tool):
    """Return the top-level wiki index (one-line summary of every page)."""

    name = "wiki.list"
    schema = {"type": "object", "properties": {}}

    def __init__(self, *, wiki_dir: str) -> None:
        self._wiki_root = Path(wiki_dir)

    async def execute(self, args: dict[str, Any]) -> str:
        index = self._wiki_root / "index.md"
        if not index.is_file():
            raise ToolError(
                f"wiki index.md not found at {index}. "
                "Has the wiki been initialized?"
            )
        return index.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools_wiki.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): wiki.list tool"
```

---

## Task 11: `wiki.search` (filesystem grep across .md files)

**Files:**
- Modify: `services/orchestrator/orchestrator/tools/wiki.py`
- Modify: `services/orchestrator/tests/test_tools_wiki.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_tools_wiki.py`**

```python
from orchestrator.tools.wiki import WikiSearch


@pytest.fixture
def populated_wiki(wiki_dir: Path) -> Path:
    """A wiki with a few real-looking pages we can grep against."""
    (wiki_dir / "concepts" / "tts.md").write_text(
        "# Text To Speech\n\nKokoro is a fast TTS engine used by NodeAva.\nIt emits PCM with word timestamps.\n"
    )
    (wiki_dir / "concepts" / "stt.md").write_text(
        "# Speech To Text\n\nWhisper transcribes audio to text. NodeAva uses base.en.\n"
    )
    (wiki_dir / "entities" / "kokoro.md").write_text(
        "# Kokoro\n\nKokoro-82M is the default TTS model.\n"
    )
    return wiki_dir


async def test_search_finds_matches_across_pages(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "Kokoro"})
    # The two pages that mention Kokoro should both appear in results.
    assert "concepts/tts.md" in out
    assert "entities/kokoro.md" in out


async def test_search_case_insensitive(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "kokoro"})
    assert "Kokoro" in out  # original case preserved in result lines


async def test_search_no_matches(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "zoological-asdf"})
    assert "No matches" in out


async def test_search_requires_query(populated_wiki):
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError):
        await tool.execute({})


async def test_search_skips_non_md_files(populated_wiki):
    """search should skip raw assets / images / etc."""
    (populated_wiki / "entities" / "logo.png").write_bytes(b"\x89PNG\x0d\x0a\x1a\x0a...")
    tool = WikiSearch(wiki_dir=str(populated_wiki))
    out = await tool.execute({"query": "Kokoro"})
    assert "logo.png" not in out
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_tools_wiki.py -v
```

Expected: ImportError on `WikiSearch`.

- [ ] **Step 3: Append the `WikiSearch` class to `services/orchestrator/orchestrator/tools/wiki.py`**

```python


class WikiSearch(Tool):
    """Grep across all .md files in the wiki for a query string."""

    name = "wiki.search"
    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Substring or regex to find (case-insensitive)",
            },
            "max_matches": {
                "type": "integer",
                "description": "Cap total matching lines returned",
                "default": 30,
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, wiki_dir: str) -> None:
        self._wiki_root = Path(wiki_dir)

    async def execute(self, args: dict[str, Any]) -> str:
        query = args.get("query") or ""
        if not query:
            raise ToolError("wiki.search requires a non-empty 'query'")

        try:
            max_matches = int(args.get("max_matches", 30))
        except (TypeError, ValueError):
            max_matches = 30
        max_matches = max(1, min(max_matches, 100))

        try:
            compiled = re.compile(query, re.IGNORECASE)

            def predicate(line: str) -> bool:
                return bool(compiled.search(line))
        except re.error:
            needle = query.lower()

            def predicate(line: str) -> bool:
                return needle in line.lower()

        matches: list[str] = []
        for path in sorted(self._wiki_root.rglob("*.md")):
            rel = path.relative_to(self._wiki_root)
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines, start=1):
                if predicate(line):
                    matches.append(f"{rel}:{i}: {line}")
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break

        if not matches:
            return f"No matches for: {query}"
        return "\n".join(matches)
```

- [ ] **Step 4: Run all wiki tests**

```bash
pytest tests/test_tools_wiki.py -v
```

Expected: 7 PASS (2 list + 5 search).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): wiki.search tool"
```

---

## Task 12: `wiki.open` (paginated read of a single page)

**Files:**
- Modify: `services/orchestrator/orchestrator/tools/wiki.py`
- Modify: `services/orchestrator/tests/test_tools_wiki.py`

- [ ] **Step 1: Append to `services/orchestrator/tests/test_tools_wiki.py`**

```python
from orchestrator.tools.wiki import WikiOpen


async def test_open_returns_page_with_header(populated_wiki):
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    out = await tool.execute({"path": "concepts/tts.md"})
    assert "Path: concepts/tts.md" in out
    assert "Kokoro is a fast TTS engine" in out


async def test_open_paginates(populated_wiki):
    """num_lines + cursor work like browser.open's pagination."""
    big = populated_wiki / "concepts" / "long.md"
    big.write_text("\n".join(f"line {i}" for i in range(50)))
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    out = await tool.execute({"path": "concepts/long.md", "num_lines": 5, "cursor": 10})
    assert "Lines 11-15 of 50" in out
    assert "line 10" in out
    assert "line 14" in out
    assert "line 20" not in out


async def test_open_missing_page_raises(populated_wiki):
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError) as exc:
        await tool.execute({"path": "does/not/exist.md"})
    assert "exist.md" in str(exc.value)


async def test_open_rejects_path_traversal(populated_wiki):
    """`../../../etc/passwd` must not escape the wiki root."""
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError) as exc:
        await tool.execute({"path": "../../../etc/passwd"})
    assert "outside the wiki" in str(exc.value).lower() or "outside" in str(exc.value).lower()


async def test_open_requires_path(populated_wiki):
    tool = WikiOpen(wiki_dir=str(populated_wiki))
    with pytest.raises(ToolError):
        await tool.execute({})
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_tools_wiki.py -v
```

Expected: ImportError on `WikiOpen`.

- [ ] **Step 3: Append the `WikiOpen` class to `services/orchestrator/orchestrator/tools/wiki.py`**

```python


class WikiOpen(Tool):
    """Read a single wiki page, paginated. Path is wiki-relative."""

    name = "wiki.open"
    schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Wiki-relative path, e.g. 'concepts/tts.md'. "
                    "Must not escape the wiki root."
                ),
            },
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to return",
                "default": 200,
            },
            "cursor": {
                "type": "integer",
                "description": "Line offset to start from",
                "default": 0,
            },
        },
        "required": ["path"],
    }

    def __init__(self, *, wiki_dir: str) -> None:
        self._wiki_root = Path(wiki_dir).resolve()

    async def execute(self, args: dict[str, Any]) -> str:
        path = args.get("path") or ""
        if not path:
            raise ToolError("wiki.open requires a 'path' argument")

        # Guard against path traversal — the resolved path must remain
        # under wiki_root after normalization.
        candidate = (self._wiki_root / path).resolve()
        try:
            candidate.relative_to(self._wiki_root)
        except ValueError:
            raise ToolError(
                f"refusing to open {path}: target resolves outside the wiki root"
            )

        if not candidate.is_file():
            raise ToolError(f"wiki page not found: {path}")

        try:
            num_lines = int(args.get("num_lines", 200))
        except (TypeError, ValueError):
            num_lines = 200
        num_lines = max(1, min(num_lines, 2000))

        try:
            cursor = int(args.get("cursor", 0))
        except (TypeError, ValueError):
            cursor = 0
        cursor = max(0, cursor)

        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ToolError(f"cannot read {path}: {e}") from e

        lines = text.splitlines()
        total = len(lines)
        end = min(cursor + num_lines, total)
        selected = lines[cursor:end]
        rel = candidate.relative_to(self._wiki_root)
        header = (
            f"Path: {rel}\n"
            f"Lines {cursor + 1}-{end} of {total}\n"
            f"---\n"
        )
        return header + "\n".join(selected)
```

- [ ] **Step 4: Run all wiki tests**

```bash
pytest tests/test_tools_wiki.py -v
```

Expected: 12 PASS (2 list + 5 search + 5 open).

- [ ] **Step 5: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): wiki.open tool (paginated, path-traversal-safe)"
```

---

## Task 13: `POST /v1/tools/{name}` test endpoint + register built-in tools

**Files:**
- Create: `services/orchestrator/orchestrator/routes/tools.py`
- Modify: `services/orchestrator/orchestrator/main.py` (register tools, include router)
- Create: `services/orchestrator/tests/test_routes_tools.py`

The test endpoint accepts `{ "args": { ... } }` in the body and dispatches to the registered tool. On `ToolError` returns 400. On unknown tool returns 404. This endpoint is **temporary** — Plan #4 deletes it once the agentic chat loop consumes tools internally.

- [ ] **Step 1: Create `services/orchestrator/tests/test_routes_tools.py`**

```python
"""Tests for POST /v1/tools/{name} — the per-tool test endpoint.

Plan #4 deletes this endpoint once tools are wired into the chat
completions loop. Until then, this is how we exercise tools through HTTP.
"""
import pytest


async def test_unknown_tool_returns_404(app_client):
    resp = await app_client.post("/v1/tools/does.not.exist", json={"args": {}})
    assert resp.status_code == 404


async def test_wiki_list_via_route(app_client, tmp_path, monkeypatch):
    """The built-in wiki.list tool is registered at app startup and works."""
    from pathlib import Path
    # Point app at a throwaway wiki for this test.
    (tmp_path / "index.md").write_text("# Test Wiki Index\n\nHello.\n")
    # Re-register wiki tools against the test wiki dir.
    from orchestrator import tools as tool_registry
    from orchestrator.tools.wiki import WikiList
    tool_registry.register(WikiList(wiki_dir=str(tmp_path)))

    resp = await app_client.post("/v1/tools/wiki.list", json={"args": {}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool"] == "wiki.list"
    assert "Test Wiki Index" in body["result"]


async def test_tool_error_returns_400(app_client):
    """A ToolError from execute() → 400 with the message in the response."""
    from orchestrator import tools as tool_registry
    from orchestrator.tools.base import Tool, ToolError

    class _Bad(Tool):
        name = "test.bad"
        schema = {"type": "object"}

        async def execute(self, args):
            raise ToolError("nope")

    tool_registry.register(_Bad())
    resp = await app_client.post("/v1/tools/test.bad", json={"args": {}})
    assert resp.status_code == 400
    assert "nope" in resp.json()["error"]


async def test_missing_args_treated_as_empty(app_client):
    """Calling with no body is OK — args defaults to {}."""
    from orchestrator import tools as tool_registry
    from orchestrator.tools.base import Tool

    class _Ping(Tool):
        name = "test.ping"
        schema = {"type": "object"}

        async def execute(self, args):
            return "pong"

    tool_registry.register(_Ping())
    resp = await app_client.post("/v1/tools/test.ping", json={})
    assert resp.status_code == 200
    assert resp.json()["result"] == "pong"
```

- [ ] **Step 2: Run failing tests**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest tests/test_routes_tools.py -v
```

Expected: 404 for all — tools router not registered.

- [ ] **Step 3: Create `services/orchestrator/orchestrator/routes/tools.py`**

```python
"""POST /v1/tools/{name} — execute a registered tool by name.

Plan #3 only. Plan #4 deletes this route once tools are consumed via
the agentic chat loop. The shape:

  Request:  POST /v1/tools/wiki.list
            { "args": { ... } }
  Response: 200 { "tool": "wiki.list", "result": "<string>" }
            400 { "error": "<ToolError message>" }   (bad args, expected failure)
            404 { "error": "unknown tool" }
            500 ... (unexpected — propagates)
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from orchestrator.tools import ToolError, get as get_tool

router = APIRouter()


@router.post("/v1/tools/{name}")
async def execute_tool(name: str, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    args = (body or {}).get("args") or {}

    try:
        tool = get_tool(name)
    except ToolError:
        return JSONResponse({"error": f"unknown tool: {name}"}, status_code=404)

    try:
        result = await tool.execute(args)
    except ToolError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    return JSONResponse({"tool": name, "result": result})
```

- [ ] **Step 4: Replace `services/orchestrator/orchestrator/main.py` ENTIRELY**

```python
"""FastAPI app entry point for nodeava-orch."""
import logging

from fastapi import FastAPI

from orchestrator.config import Settings
from orchestrator.providers.local import LocalLlamaProvider
from orchestrator.routes import chat, health, models, tools as tools_route
from orchestrator import tools as tool_registry
from orchestrator.tools.browser import BrowserFind, BrowserOpen, BrowserSearch
from orchestrator.tools.cache import PageCache
from orchestrator.tools.wiki import WikiList, WikiOpen, WikiSearch

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _register_builtin_tools(settings: Settings) -> None:
    """Register the Plan #3 built-in tools against the module-level registry.

    Browser tools share a single PageCache. Wiki tools point at
    settings.wiki_dir. Plan #4 may extend this with more tools.
    """
    page_cache = PageCache(max_size=20)
    tool_registry.register(
        BrowserSearch(searxng_url=settings.searxng_url, cache=page_cache)
    )
    tool_registry.register(BrowserOpen(cache=page_cache))
    tool_registry.register(BrowserFind(cache=page_cache))
    tool_registry.register(WikiList(wiki_dir=settings.wiki_dir))
    tool_registry.register(WikiSearch(wiki_dir=settings.wiki_dir))
    tool_registry.register(WikiOpen(wiki_dir=settings.wiki_dir))


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Sets `app.state.local_provider` — the always-available local backend.
    Cloud providers are constructed per-request by
    `orchestrator.providers.pick_provider`.

    Built-in tools are registered against the module-level registry.
    """
    settings = settings or Settings()
    app = FastAPI(title="nodeava-orch", version="0.3.0")
    app.state.settings = settings
    app.state.local_provider = LocalLlamaProvider(
        base_url=settings.llama_url, timeout=settings.request_timeout
    )
    _register_builtin_tools(settings)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    app.include_router(tools_route.router)
    return app


app = create_app()


def run() -> None:
    """Launch uvicorn honoring BIND_HOST / BIND_PORT settings."""
    import uvicorn

    settings: Settings = app.state.settings
    uvicorn.run(
        "orchestrator.main:app",
        host=settings.bind_host,
        port=settings.bind_port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
```

- [ ] **Step 5: Run all tests**

```bash
pytest -v
```

Expected: all tests pass. Cumulative tally (rough): Plan #1+#2 = 40, Plan #3 adds ~30 = ~70 total.

- [ ] **Step 6: Commit**

```bash
cd ../..
git add services/orchestrator/
git commit -m "feat(orch): /v1/tools/{name} route + register built-in tools at startup"
```

---

## Task 14: Bundle SearXNG container in docker-compose

**Files:**
- Create: `configs/searxng/settings.yml`
- Modify: `docker-compose.yml` (add `searxng` service, ensure orchestrator depends on it)

The bundled SearXNG container is the default backend for `browser.search`. JSON API must be enabled (off by default in SearXNG). No Redis — SearXNG's built-in limiter is sufficient at workshop scale.

- [ ] **Step 1: Create `configs/searxng/settings.yml`**

```yaml
# SearXNG minimal config for the workshop orchestrator.
# Default settings are inherited from SearXNG's bundled defaults.yml;
# we only override what we need.

use_default_settings: true

general:
  instance_name: "NodeAva Workshop SearXNG"
  contact_url: false
  privacypolicy_url: false
  donation_url: false
  enable_metrics: false

server:
  # The bind address inside the container — the entire container is on
  # the workshop Docker network; do not expose this to the host.
  bind_address: "0.0.0.0"
  base_url: "http://searxng:8080/"
  secret_key: "workshop-default-secret-please-rotate"
  limiter: true
  image_proxy: false
  default_locale: "en"

ui:
  default_theme: simple

search:
  # CRITICAL — the JSON format must be enabled for the orchestrator's
  # browser.search tool. Default SearXNG only enables 'html'.
  formats:
    - html
    - json
  safe_search: 0
  autocomplete: ""
  default_lang: "en"

outgoing:
  request_timeout: 10.0
  max_request_timeout: 15.0
```

- [ ] **Step 2: Edit `docker-compose.yml`** to add the `searxng` service. Insert this block at the same indentation level as the other services (e.g. right after the `orchestrator` service block):

```yaml
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    # Internal only — the workshop orchestrator reaches it via Docker DNS.
    # No host port mapping by default (do not expose meta-search to the LAN).
    expose:
      - "8080"
    volumes:
      - ./configs/searxng:/etc/searxng:ro
    environment:
      - SEARXNG_BASE_URL=http://searxng:8080/
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
```

Then modify the orchestrator service's `depends_on` block in the same file. Find the orchestrator service's `depends_on` (it currently lists `llm: service_healthy`) and replace it with:

```yaml
    depends_on:
      llm:
        condition: service_healthy
      searxng:
        condition: service_healthy
```

- [ ] **Step 3: Build + verify SearXNG container starts and JSON API works**

From the worktree root:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml up -d searxng
```

Wait for `searxng` to become healthy:

```bash
until [ "$(docker inspect searxng --format '{{.State.Health.Status}}' 2>/dev/null)" = "healthy" ]; do sleep 2; done
echo "searxng healthy"
```

Verify JSON API works via host-side curl (we don't normally expose the port to the host — for this manual check, exec into the container):

```bash
docker exec searxng wget -O- --quiet 'http://localhost:8080/search?q=linux+kernel&format=json' | head -c 400
```

Expected: JSON output starting with `{"query":"linux kernel"...` containing a `results` array. If the response is HTML or 403, the `formats: json` setting in `configs/searxng/settings.yml` wasn't picked up — re-check the volume mount.

Tear down again before commit:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml stop searxng
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml rm -f searxng
```

- [ ] **Step 4: Commit**

```bash
git add configs/searxng/ docker-compose.yml
git commit -m "feat(orch): bundle SearXNG service with JSON API enabled"
```

---

## Task 15: Document the registry + tools in the service README

**Files:**
- Modify: `services/orchestrator/README.md`

- [ ] **Step 1: Insert a new section in the README between the "Provider selection" section and the "Run locally (dev)" section. The new section is:**

```markdown
## Tools (Plan #3)

The orchestrator hosts a pluggable tool registry. Plan #3 ships two
families of built-in tools:

### Browser tools (backed by bundled SearXNG)

| Tool | Purpose |
|---|---|
| `browser.search` | Query the bundled SearXNG meta-search engine; returns top-N results as numbered text |
| `browser.open`   | Fetch a URL, extract readable text via trafilatura, return paginated lines; caches the page in an in-process LRU |
| `browser.find`   | Regex / substring search across the most-recently-opened page (or an explicit URL) |

### Wiki tools (filesystem-backed, Karpathy-style)

| Tool | Purpose |
|---|---|
| `wiki.list`   | Return `wiki/index.md` verbatim — the agent's first stop for "what do I have?" |
| `wiki.search` | Grep across all `.md` files in `wiki/` for a query |
| `wiki.open`   | Read a single wiki page, paginated. Path-traversal safe. |

### Calling a tool directly (Plan #3 test endpoint)

```bash
curl http://localhost:8082/v1/tools/browser.search \
  -H 'Content-Type: application/json' \
  -d '{"args":{"query":"Linux kernel release","topn":3}}'

curl http://localhost:8082/v1/tools/wiki.list \
  -H 'Content-Type: application/json' \
  -d '{"args":{}}'

curl http://localhost:8082/v1/tools/wiki.open \
  -H 'Content-Type: application/json' \
  -d '{"args":{"path":"concepts/tts.md","num_lines":50}}'
```

Response shape:
- `200 {"tool": "<name>", "result": "<string>"}` — success
- `400 {"error": "<msg>"}` — `ToolError` from the tool (bad input, page not found, etc.)
- `404 {"error": "unknown tool: <name>"}` — name not registered

The `/v1/tools/{name}` endpoint exists strictly for Plan #3 testing.
Plan #4 wires tools into the agentic chat-completion loop and deletes
this route.

### Adding a custom tool

1. Subclass `orchestrator.tools.base.Tool` with `name`, `schema`, and `execute(args)`.
2. Register it at startup in `orchestrator.main._register_builtin_tools`.
3. Write tests under `tests/test_tools_<name>.py`.

Tools raise `ToolError` for user-fixable failures (bad input, page-not-found, etc.).
Anything else propagates as a 500 from the test endpoint and (in Plan #4)
becomes a `ToolCallEndEvent` with an `error` field.
```

- [ ] **Step 2: Update the env-var table** to add the two new vars. Find the existing env-var table and add these rows at the end:

```markdown
| `SEARXNG_URL` | `http://searxng:8080` | URL of the bundled SearXNG service (Docker DNS) |
| `WIKI_DIR` | `wiki` | On-disk wiki directory the wiki.* tools read |
```

- [ ] **Step 3: Commit**

```bash
git add services/orchestrator/README.md
git commit -m "docs(orch): document the tool registry + browser + wiki tools"
```

---

## Final verification

- [ ] **Step 1: Full test suite passes**

```bash
cd services/orchestrator && source .venv/bin/activate
pytest -v
```

Expected: all tests pass. Rough tally additions in Plan #3:
- 4 new in `test_config.py` (was 4, now 6)
- 3 new in `test_tools_registry.py` (base) + 4 new (registry) = 7
- 5 in `test_tools_cache.py`
- 13 in `test_tools_browser.py` (search 4 + open 4 + find 5)
- 12 in `test_tools_wiki.py` (list 2 + search 5 + open 5)
- 4 in `test_routes_tools.py`

Plan #1+#2 had 40 tests. Plan #3 adds ~43. Final cumulative ~83.

- [ ] **Step 2: Docker build for the orchestrator still works**

```bash
cd ../..
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml build orchestrator searxng
```

Expected: both images build clean.

- [ ] **Step 3: Optional manual smoke test**

Bring up llm + orchestrator + searxng:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml -f docker-compose.test.yml up -d llm orchestrator searxng
```

Wait for all three healthy, then:

```bash
# Wiki tool (no network needed)
curl -s http://localhost:8082/v1/tools/wiki.list -H 'Content-Type: application/json' -d '{"args":{}}' | head -c 400

# Browser search (hits real SearXNG, which hits real Google/DuckDuckGo)
curl -s http://localhost:8082/v1/tools/browser.search -H 'Content-Type: application/json' -d '{"args":{"query":"linux kernel release","topn":3}}'

# Browser open + find chain
curl -s http://localhost:8082/v1/tools/browser.open -H 'Content-Type: application/json' -d '{"args":{"id":"https://kernel.org/","num_lines":20}}'
curl -s http://localhost:8082/v1/tools/browser.find -H 'Content-Type: application/json' -d '{"args":{"pattern":"6\\.\\d+"}}'
```

Each should return a meaningful response. Tear down with `docker compose ... down`.

---

## What comes next (Plan #4)

Plan #4 wires the registered tools into the chat completions flow:

1. Add `ToolCallStartEvent`, `ToolCallEndEvent`, and `StageTimingEvent` to the event union.
2. Build the **agentic loop** as a single async generator yielding typed events — replacing the simple `provider.chat(messages, stream=…)` call in the chat route with a tool-aware loop that:
   - Injects `to_openai_function()` from the registry into the request
   - When the model returns `tool_calls`, dispatches via `tool_registry.get(name).execute(args)`
   - Streams `tool_call_start` / `tool_call_end` SSE events to the frontend (this is what enables the Tier A "tool trace" panel in Plan #8)
   - Loops until the model returns content without tool calls, or a max-rounds cap is reached
3. Delete the temporary `POST /v1/tools/{name}` test route.
4. Add request-level toggles: `web_search: bool`, `wiki: bool` in the chat body (default false). Only inject the matching tools when these are enabled.
