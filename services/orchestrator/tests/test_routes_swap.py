"""Tests for /v1/swap."""
import httpx
import pytest
import respx


@respx.mock
async def test_swap_brain_updates_state(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "brain", "id": "smollm2-360m"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"]["brain"] == "smollm2-360m"


@respx.mock
async def test_swap_unknown_brain_returns_400(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "brain", "id": "no-such-brain"}
    )
    assert resp.status_code == 400
    assert "no-such-brain" in resp.json()["error"]


@respx.mock
async def test_swap_tools_requires_value(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "tools", "id": "web_search"}
    )
    assert resp.status_code == 400


@respx.mock
async def test_swap_tools_with_value_updates_state(app_client):
    respx.get("http://host.docker.internal:11434/api/ps").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await app_client.post(
        "/v1/swap", json={"kind": "tools", "id": "web_search", "value": True}
    )
    assert resp.status_code == 200
    assert resp.json()["active"]["tools"]["web_search"] is True


@respx.mock
async def test_swap_unknown_kind_returns_400(app_client):
    resp = await app_client.post(
        "/v1/swap", json={"kind": "weird", "id": "x"}
    )
    assert resp.status_code == 400
