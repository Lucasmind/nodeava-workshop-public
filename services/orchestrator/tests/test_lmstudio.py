"""Tests for the LM Studio backend integration (Plan #11).

Covers: config flags, the native LMStudioProvider, model discovery + residency
(LMStudioBackend), dispatcher routing, dynamic catalog merge, and route-level
behavior (catalog discovery + chat "auto" model resolution) when
llm_backend == "lmstudio".
"""
import json

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from orchestrator.catalog import BrainEntry, Catalog
from orchestrator.config import Settings
from orchestrator.events import TokenEvent
from orchestrator.main import create_app
from orchestrator.providers.dispatcher import dispatch_for_brain
from orchestrator.providers.lmstudio import LMStudioProvider
from orchestrator.providers.ollama import OllamaProvider
from orchestrator.system.lmstudio import LMStudioBackend, looks_like_thinker

LMS = "http://lmstudio-test:1234"

_MODELS_JSON = {
    "data": [
        {"id": "qwen/qwen3-4b-2507", "type": "llm", "state": "loaded",
         "arch": "qwen3", "quantization": "Q4_K_M", "max_context_length": 128000},
        {"id": "google/gemma-4-31b-it", "type": "vlm", "state": "not-loaded",
         "max_context_length": 262144},
        {"id": "deepseek-r1-8b-thinking", "type": "llm", "state": "not-loaded"},
        {"id": "text-embedding-nomic", "type": "embeddings", "state": "not-loaded"},
    ]
}


# ─────────────────────────── config ───────────────────────────
def test_config_lmstudio_defaults(monkeypatch):
    for k in ("LLM_BACKEND", "LMSTUDIO_URL", "LMSTUDIO_DEFAULT_MODEL"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.llm_backend == "ollama"  # upstream default preserved
    assert s.lmstudio_url == "http://host.docker.internal:1234"
    assert s.lmstudio_default_model == "qwen/qwen3-4b-2507"


def test_config_lmstudio_env_override(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "lmstudio")
    monkeypatch.setenv("LMSTUDIO_URL", "http://box:4321")
    monkeypatch.setenv("LMSTUDIO_DEFAULT_MODEL", "foo/bar")
    s = Settings()
    assert s.llm_backend == "lmstudio"
    assert s.lmstudio_url == "http://box:4321"
    assert s.lmstudio_default_model == "foo/bar"


# ─────────────────────────── provider ───────────────────────────
def test_lmstudio_provider_targets_native_endpoint():
    p = LMStudioProvider(base_url=LMS, model="m")
    assert isinstance(p, OllamaProvider)  # reuses OpenAI-shaped parsing
    assert p._CHAT_PATH == "/api/v0/chat/completions"


@respx.mock
async def test_lmstudio_provider_chat_hits_api_v0():
    route = respx.post(f"{LMS}/api/v0/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
    )
    p = LMStudioProvider(base_url=LMS, model="qwen/qwen3-4b-2507")
    events = [e async for e in p.chat([{"role": "user", "content": "x"}], stream=False)]
    assert route.called
    assert any(isinstance(e, TokenEvent) and e.delta == "hi" for e in events)


# ─────────────────────── backend discovery ───────────────────────
@respx.mock
async def test_backend_list_models_filters_and_flags():
    respx.get(f"{LMS}/api/v0/models").mock(
        return_value=httpx.Response(200, json=_MODELS_JSON)
    )
    models = await LMStudioBackend(base_url=LMS).list_models()
    ids = {m["id"] for m in models}
    assert "text-embedding-nomic" not in ids  # embeddings filtered out
    assert {"qwen/qwen3-4b-2507", "google/gemma-4-31b-it"} <= ids
    q = next(m for m in models if m["id"] == "qwen/qwen3-4b-2507")
    assert q["loaded"] is True
    dr = next(m for m in models if m["id"] == "deepseek-r1-8b-thinking")
    assert dr["thinks"] is True


@respx.mock
async def test_backend_query_residency_shape():
    respx.get(f"{LMS}/api/v0/models").mock(
        return_value=httpx.Response(200, json=_MODELS_JSON)
    )
    snap = await LMStudioBackend(base_url=LMS).query()
    assert snap["reachable"] is True
    assert [m["model"] for m in snap["loaded"]] == ["qwen/qwen3-4b-2507"]
    assert snap["loaded"][0]["residency"] == "loaded"


@respx.mock
async def test_backend_query_unreachable():
    respx.get(f"{LMS}/api/v0/models").mock(side_effect=httpx.ConnectError("no"))
    snap = await LMStudioBackend(base_url=LMS).query()
    assert snap == {"reachable": False, "loaded": []}


@respx.mock
async def test_backend_pick_model_prefers_loaded():
    respx.get(f"{LMS}/api/v0/models").mock(
        return_value=httpx.Response(200, json=_MODELS_JSON)
    )
    picked = await LMStudioBackend(base_url=LMS).pick_model(fallback="fallback/x")
    assert picked == "qwen/qwen3-4b-2507"


@respx.mock
async def test_backend_pick_model_falls_back_when_none_loaded():
    j = {"data": [{"id": "a/b", "type": "llm", "state": "not-loaded"}]}
    respx.get(f"{LMS}/api/v0/models").mock(return_value=httpx.Response(200, json=j))
    picked = await LMStudioBackend(base_url=LMS).pick_model(fallback="fallback/x")
    assert picked == "fallback/x"


def test_looks_like_thinker():
    assert looks_like_thinker("deepseek-r1-8b")
    assert looks_like_thinker("qwen3-4b-thinking-2507")
    assert not looks_like_thinker("qwen/qwen3-4b-2507")


# ─────────────────────────── dispatcher ───────────────────────────
def test_dispatch_lmstudio_kind():
    brain = BrainEntry(id="x", label="X", kind="lmstudio", model="m")
    p = dispatch_for_brain(
        brain, ollama_url="http://o:11434", lmstudio_url=LMS,
        request_timeout=10.0, api_key=None,
    )
    assert isinstance(p, LMStudioProvider)
    assert p._base_url == LMS
    assert p._model == "m"


def test_dispatch_lmstudio_model_override():
    brain = BrainEntry(id="x", label="X", kind="lmstudio", model="auto")
    p = dispatch_for_brain(
        brain, ollama_url="http://o:11434", lmstudio_url=LMS,
        request_timeout=10.0, api_key=None, model_override="real/model",
    )
    assert p._model == "real/model"


# ──────────────────────── dynamic catalog merge ────────────────────────
def test_sync_dynamic_brains_adds_replaces_and_preserves_static():
    cat = Catalog(brains=[BrainEntry(id="static", label="S", kind="lmstudio", model="auto")])
    cat.sync_dynamic_brains([
        {"id": "a/b", "loaded": True, "thinks": False},
        {"id": "c/d-thinking", "loaded": False, "thinks": True},
    ])
    ids = [b.id for b in cat.brains]
    assert "static" in ids  # static (non-dynamic) preserved
    assert {"lmstudio:a/b", "lmstudio:c/d-thinking"} <= set(ids)
    dyn = [b for b in cat.brains if b.dynamic]
    assert dyn[0].id == "lmstudio:a/b"  # loaded sorts first
    assert cat.brain("lmstudio:c/d-thinking").thinks is True

    # re-sync REPLACES dynamic entries (no accumulation), keeps static
    cat.sync_dynamic_brains([{"id": "e/f", "loaded": False}])
    assert [b.id for b in cat.brains if b.dynamic] == ["lmstudio:e/f"]
    assert [b.id for b in cat.brains if not b.dynamic] == ["static"]


# ─────────────────────── route-level (backend=lmstudio) ───────────────────────
@pytest.fixture
def lmstudio_app(tmp_path):
    settings = Settings(
        state_path=str(tmp_path / "state.json"),
        llm_backend="lmstudio",
        lmstudio_url=LMS,
    )
    app = create_app(settings=settings)
    app.state.state_store.set_tool("web_search", False)
    app.state.state_store.set_tool("wiki", False)
    return app


@pytest.fixture
async def lmstudio_client(lmstudio_app):
    transport = ASGITransport(app=lmstudio_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_lmstudio_backend_promotes_default_brain(lmstudio_app):
    # When LM Studio is active, the boot default brain is the LM Studio "auto" one.
    assert lmstudio_app.state.catalog.default_brain().id == "lmstudio-auto"
    assert lmstudio_app.state.state_store.get_state()["brain"] == "lmstudio-auto"


@respx.mock
async def test_catalog_merges_lmstudio_library(lmstudio_client):
    respx.get(f"{LMS}/api/v0/models").mock(
        return_value=httpx.Response(200, json=_MODELS_JSON)
    )
    respx.get("http://host.docker.internal:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    resp = await lmstudio_client.get("/v1/catalog")
    assert resp.status_code == 200
    brains = resp.json()["brains"]
    ids = {b["id"] for b in brains}
    assert "lmstudio:qwen/qwen3-4b-2507" in ids
    assert "lmstudio:google/gemma-4-31b-it" in ids
    assert "lmstudio:text-embedding-nomic" not in ids  # embeddings excluded
    q = next(b for b in brains if b["id"] == "lmstudio:qwen/qwen3-4b-2507")
    assert q["available"] is True and q["loaded"] is True
    g = next(b for b in brains if b["id"] == "lmstudio:google/gemma-4-31b-it")
    assert g["available"] is True and g["loaded"] is False


@respx.mock
async def test_chat_auto_resolves_loaded_model_via_native_endpoint(lmstudio_client):
    respx.get(f"{LMS}/api/v0/models").mock(
        return_value=httpx.Response(200, json=_MODELS_JSON)
    )
    captured = {}

    def _cap(request):
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    respx.post(f"{LMS}/api/v0/chat/completions").mock(side_effect=_cap)

    resp = await lmstudio_client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    assert resp.status_code == 200
    # active brain is lmstudio-auto → resolved to the currently-loaded model,
    # and the request hit LM Studio's NATIVE endpoint.
    assert captured["body"]["model"] == "qwen/qwen3-4b-2507"
    assert "/api/v0/chat/completions" in captured["url"]
