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


@respx.mock
async def test_open_rejects_non_http_scheme():
    """file://, ftp://, gopher:// all rejected."""
    from orchestrator.tools.base import ToolError
    import pytest

    tool = BrowserOpen(cache=PageCache())
    for url in ("file:///etc/passwd", "ftp://example.com/", "gopher://x"):
        with pytest.raises(ToolError) as exc:
            await tool.execute({"id": url})
        assert "scheme" in str(exc.value).lower() or "http" in str(exc.value).lower()


async def test_open_rejects_private_ip_hostnames(monkeypatch):
    """Hostnames resolving to private / loopback / link-local addresses are rejected
    BEFORE any HTTP call is attempted."""
    from orchestrator.tools.base import ToolError
    import pytest

    # Patch socket.gethostbyname so we don't need real DNS. The guard uses
    # it to resolve the hostname before deciding whether to fetch.
    import socket
    original = socket.gethostbyname

    def fake_resolve(host: str) -> str:
        return {
            "metadata.example": "169.254.169.254",     # link-local
            "internal.example": "10.0.0.5",             # private
            "loopback.example": "127.0.0.1",            # loopback
        }.get(host, original(host))

    monkeypatch.setattr(socket, "gethostbyname", fake_resolve)

    tool = BrowserOpen(cache=PageCache())
    for host in ("metadata.example", "internal.example", "loopback.example"):
        with pytest.raises(ToolError) as exc:
            await tool.execute({"id": f"http://{host}/anything"})
        msg = str(exc.value).lower()
        assert (
            "private" in msg or "internal" in msg or "loopback" in msg
            or "metadata" in msg or "refus" in msg
        )


async def test_open_rejects_raw_private_ip():
    """Literal IPs in private ranges also rejected — no DNS needed."""
    from orchestrator.tools.base import ToolError
    import pytest

    tool = BrowserOpen(cache=PageCache())
    for url in (
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
    ):
        with pytest.raises(ToolError):
            await tool.execute({"id": url})


@respx.mock
async def test_open_size_cap_rejects_oversized_content_length():
    """If the server advertises content-length > 5MB, refuse before reading the body."""
    from orchestrator.tools.base import ToolError
    import pytest

    too_big = 6 * 1024 * 1024
    respx.get("https://example.com/huge").mock(
        return_value=Response(
            200,
            content=b"<html></html>",
            headers={"content-type": "text/html", "content-length": str(too_big)},
        )
    )

    tool = BrowserOpen(cache=PageCache())
    with pytest.raises(ToolError) as exc:
        await tool.execute({"id": "https://example.com/huge"})
    assert "size" in str(exc.value).lower() or "too large" in str(exc.value).lower()
