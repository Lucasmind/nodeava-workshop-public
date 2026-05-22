"""Tests for POST /v1/personality/custom."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrator.config import Settings
from orchestrator.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("NODEAVA_STATE_DIR", str(tmp_path))
    settings = Settings(state_path=str(tmp_path / "state.json"))
    app = create_app(settings=settings)
    return TestClient(app)


def test_post_custom_persists_to_disk_and_activates(client: TestClient, tmp_path: Path):
    resp = client.post(
        "/v1/personality/custom",
        json={"system_prompt": "You are a pirate. Arr."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["active"]["personality"] == "custom"

    saved = json.loads((tmp_path / "custom-personality.json").read_text())
    assert saved["system_prompt"] == "You are a pirate. Arr."


def test_get_catalog_after_post_includes_custom_personality(client: TestClient):
    client.post(
        "/v1/personality/custom",
        json={"system_prompt": "You are a pirate. Arr."},
    )
    catalog = client.get("/v1/catalog").json()
    ids = [p["id"] for p in catalog["personalities"]]
    assert "custom" in ids


def test_post_rejects_empty_prompt(client: TestClient):
    resp = client.post("/v1/personality/custom", json={"system_prompt": "   "})
    assert resp.status_code == 422


def test_post_rejects_missing_field(client: TestClient):
    resp = client.post("/v1/personality/custom", json={})
    assert resp.status_code == 422


def test_catalog_personalities_include_system_prompt(client: TestClient):
    """Plan #10 — system_prompt must be in /v1/catalog so the
    Personality Editor (Task 7) can pre-fill its textarea."""
    resp = client.get("/v1/catalog")
    assert resp.status_code == 200
    personalities = resp.json()["personalities"]
    assert personalities, "catalog has no personalities"
    for p in personalities:
        assert "system_prompt" in p, f"personality {p['id']} missing system_prompt"
        assert p["system_prompt"], f"personality {p['id']} has empty system_prompt"


def test_post_custom_response_shape_matches_state_endpoint(client: TestClient):
    """Plan #10 — POST /v1/personality/custom response must mirror /v1/state.
    The dashboard's setServerState reads serverState.system.ollama for GPU chips."""
    resp = client.post(
        "/v1/personality/custom",
        json={"system_prompt": "You are a pirate. Arr."},
    )
    body = resp.json()
    assert "active" in body
    assert "system" in body
    assert "ollama" in body["system"]
