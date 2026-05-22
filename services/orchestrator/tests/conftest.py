"""Shared pytest fixtures for orchestrator tests."""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def ollama_url() -> str:
    """Fixed mock URL used by tests so respx can match it."""
    return "http://host.docker.internal:11434"


@pytest.fixture
def orch_app(tmp_path):
    """A fresh FastAPI app instance with state_store/catalog/residency wired.

    Plan #7: each test gets its own app so state_store is isolated.
    Both tool toggles are disabled by default so tests that don't need
    the agentic loop don't accidentally hit it (wiki=True is the
    StateStore default, which breaks tests mocking only the streaming
    endpoint).

    Uses tmp_path for the state file so tests don't try to write to
    /app/state/ (which doesn't exist outside the container).
    """
    from orchestrator.config import Settings
    from orchestrator.main import create_app

    settings = Settings(state_path=str(tmp_path / "state.json"))
    app = create_app(settings=settings)
    app.state.state_store.set_tool("web_search", False)
    app.state.state_store.set_tool("wiki", False)
    return app


@pytest.fixture
async def app_client(orch_app):
    """An httpx AsyncClient mounted directly against the FastAPI app."""
    transport = ASGITransport(app=orch_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
