"""Browser tools — search/open/find against the live web via SearXNG + httpx.

Three tools share a PageCache so `browser.find` can target the last page
opened by `browser.open` without a re-fetch.

Plan #4 added two security guards to `BrowserOpen`:
  - SSRF: reject non-http(s) schemes, reject hostnames that resolve to
    private / loopback / link-local / reserved IPs (cloud-metadata,
    internal Docker services, the orchestrator itself).
  - Fetch size cap: refuse pages larger than MAX_FETCH_BYTES.
"""
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

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

MAX_FETCH_BYTES = 5 * 1024 * 1024  # 5 MB cap for browser.open


def _validate_public_url(url: str) -> None:
    """Raise ToolError if `url` is not safe to fetch from the public internet.

    Rejects:
      - non-http(s) schemes
      - hostnames missing or empty
      - hostnames that resolve to: loopback (127.0.0.0/8), private
        (10/8, 172.16/12, 192.168/16), link-local (169.254/16), reserved
        / unspecified / multicast

    The check runs BEFORE any HTTP request, so SSRF attempts never reach
    the network layer.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ToolError(f"refusing to open {url}: unsupported scheme {scheme!r}")
    host = parsed.hostname
    if not host:
        raise ToolError(f"refusing to open {url}: no hostname")

    # Resolve to IP (literal IPs short-circuit). gethostbyname is sync but the
    # resolution is local + cached; not worth dragging in asyncio DNS for a guard.
    # If resolution fails (NXDOMAIN, no network), we let the request proceed —
    # the HTTP layer will fail anyway, and an unresolvable name is not
    # definitively private/internal (it could just be temporarily unavailable).
    try:
        ip_str = socket.gethostbyname(host)
    except OSError:
        return  # Cannot resolve → not obviously private; let HTTP fail naturally

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError as e:
        raise ToolError(f"refusing to open {url}: invalid resolved address {ip_str}") from e

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        raise ToolError(
            f"refusing to open {url}: host {host} resolves to {ip_str} "
            "(loopback / private / link-local / reserved)"
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
            # Validate BEFORE we even ask the cache — actually we validate
            # before fetching; the cache only ever holds previously-validated URLs.
            _validate_public_url(url)
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
                async with client.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                    },
                ) as resp:
                    if resp.status_code >= 400:
                        log.warning("HTTP %d fetching %s", resp.status_code, url)
                        raise ToolError(
                            f"HTTP {resp.status_code} fetching {url}. "
                            "The site may block automated access."
                        )
                    # Pre-check via Content-Length when present
                    cl = resp.headers.get("content-length")
                    if cl is not None:
                        try:
                            if int(cl) > MAX_FETCH_BYTES:
                                raise ToolError(
                                    f"refusing to open {url}: declared size "
                                    f"{cl} bytes > MAX_FETCH_BYTES ({MAX_FETCH_BYTES})"
                                )
                        except ValueError:
                            pass

                    # Stream-read with a running byte cap
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_FETCH_BYTES:
                            raise ToolError(
                                f"refusing to open {url}: body exceeded "
                                f"MAX_FETCH_BYTES ({MAX_FETCH_BYTES} bytes)"
                            )
                        chunks.append(chunk)
                    html = b"".join(chunks).decode("utf-8", errors="replace")
        except httpx.HTTPError as e:
            raise ToolError(f"failed to fetch {url}: {e}") from e

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
