"""Tests for /v1/catalog."""
import httpx
import pytest
import respx


@respx.mock
async def test_get_catalog_returns_4_sections(app_client, monkeypatch):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
    )
    resp = await app_client.get("/v1/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert {"brains", "voices", "avatars", "personalities"} <= set(body.keys())
    assert len(body["brains"]) >= 4


@respx.mock
async def test_get_catalog_marks_pulled_models_available(app_client, monkeypatch):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:4b-instruct"}]})
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = await app_client.get("/v1/catalog")
    body = resp.json()
    q = next(b for b in body["brains"] if b["id"] == "qwen3-4b-instruct")
    assert q["available"] is True
    claude = next(b for b in body["brains"] if b["id"] == "claude-sonnet")
    assert claude["available"] is False
    assert "ANTHROPIC_API_KEY" in claude["reason"]


@respx.mock
async def test_get_catalog_unpulled_model_unavailable(app_client):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.get("/v1/catalog")
    body = resp.json()
    q = next(b for b in body["brains"] if b["id"] == "qwen3-4b-instruct")
    assert q["available"] is False
    assert "ollama pull qwen3:4b-instruct" in q["reason"]


@respx.mock
async def test_get_catalog_ollama_unreachable_unavailable(app_client):
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        side_effect=httpx.ConnectError("nope")
    )
    resp = await app_client.get("/v1/catalog")
    body = resp.json()
    ollama_brains = [b for b in body["brains"] if b["kind"] == "ollama"]
    assert all(not b["available"] for b in ollama_brains)
