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
