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
