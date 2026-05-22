"""Tests for /v1/state."""
import httpx
import pytest
import respx


@respx.mock
async def test_get_state_returns_active_and_system(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(
            200,
            json={"models": [{"name": "qwen3:4b", "size": 100, "size_vram": 100}]},
        )
    )
    resp = await app_client.get("/v1/state")
    assert resp.status_code == 200
    body = resp.json()
    assert "active" in body
    assert "system" in body
    assert body["active"]["brain"] == "qwen3-4b-instruct"
    assert body["system"]["ollama"]["reachable"] is True
    assert body["system"]["ollama"]["loaded"][0]["residency"] == "gpu"


@respx.mock
async def test_get_state_when_ollama_unreachable(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        side_effect=httpx.ConnectError("nope")
    )
    resp = await app_client.get("/v1/state")
    body = resp.json()
    assert body["system"]["ollama"]["reachable"] is False
    assert body["system"]["ollama"]["loaded"] == []
    assert "brain" in body["active"]
