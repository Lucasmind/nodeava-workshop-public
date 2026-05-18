"""FastAPI app entry point for nodeava-orch."""
import logging
from pathlib import Path

from fastapi import FastAPI

from orchestrator.catalog import load_catalog, CatalogError
from orchestrator.config import Settings
from orchestrator.providers.ollama import OllamaProvider
from orchestrator.routes import catalog as catalog_route
from orchestrator.routes import chat, health, ingest, models
from orchestrator.routes import personality as personality_routes
from orchestrator.routes import state as state_route
from orchestrator.routes import swap as swap_route
from orchestrator.state import StateStore
from orchestrator.system.residency import OllamaResidency
from orchestrator import tools as tool_registry
from orchestrator.tools.browser import BrowserFind, BrowserOpen, BrowserSearch
from orchestrator.tools.cache import PageCache
from orchestrator.tools.wiki import WikiList, WikiOpen, WikiSearch

log = logging.getLogger("orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _register_builtin_tools(settings: Settings) -> None:
    """Register the Plan #3 built-in tools against the module-level registry.

    Browser tools share a single PageCache. Wiki tools point at
    settings.wiki_dir. The agentic loop (Plan #4) consumes from this registry.
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


# Resolve catalog path: env var > /app/configs (container mount) > repo-root dev path.
def _resolve_catalog_path() -> Path:
    import os
    env_path = os.environ.get("CATALOG_PATH")
    if env_path:
        return Path(env_path)
    # Container layout: /app/configs/catalog.yml (mounted via docker-compose volume)
    container_path = Path("/app/configs/catalog.yml")
    if container_path.exists():
        return container_path
    # Development layout: services/orchestrator/orchestrator/main.py → 3 levels up = repo root
    try:
        return Path(__file__).resolve().parents[3] / "configs" / "catalog.yml"
    except IndexError:
        return container_path

_REPO_CATALOG = _resolve_catalog_path()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Sets `app.state.local_provider` — the always-available local backend.
    Cloud providers are constructed per-request by
    `orchestrator.providers.pick_provider`.

    Built-in tools are registered against the module-level registry. The
    agentic loop in `routes/chat.py` consumes them when body toggles
    `web_search` or `wiki` are set.

    Plan #7: also wires app.state.catalog, app.state.state_store, and
    app.state.residency for per-request provider dispatch.
    """
    settings = settings or Settings()
    app = FastAPI(title="nodeava-orch", version="0.4.0")
    app.state.settings = settings
    # Plan #7: default Ollama provider with the default brain from catalog.
    # Per-request dispatch (Task 7) overrides this based on state.brain.
    app.state.local_provider = OllamaProvider(
        base_url=settings.ollama_url,
        model="qwen3:4b",
        timeout=settings.request_timeout,
    )

    # Plan #7: catalog + state store + residency
    try:
        catalog = load_catalog(_REPO_CATALOG)
    except CatalogError as e:
        log.warning("catalog load failed (%s); using minimal in-memory catalog", e)
        from orchestrator.catalog import (
            Catalog, BrainEntry, VoiceEntry, AvatarEntry, PersonalityEntry,
        )
        catalog = Catalog(
            brains=[BrainEntry(id="local", label="Local Ollama", kind="ollama", model="qwen3:4b", default=True)],
            voices=[VoiceEntry(id="default", label="Default", kokoro_voice="af_bella", default=True)],
            avatars=[AvatarEntry(id="default", label="Default", glb_path="default-avatar.glb", default=True)],
            personalities=[PersonalityEntry(
                id="default", label="Default",
                system_prompt="You are Ava, a helpful assistant.",
                default=True,
            )],
        )
    app.state.catalog = catalog
    app.state.state_store = StateStore(path=settings.state_path, catalog=catalog)
    app.state.residency = OllamaResidency(base_url=settings.ollama_url)

    _register_builtin_tools(settings)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    app.include_router(ingest.router)
    app.include_router(catalog_route.router)
    app.include_router(state_route.router)
    app.include_router(swap_route.router)
    app.include_router(personality_routes.router)
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
