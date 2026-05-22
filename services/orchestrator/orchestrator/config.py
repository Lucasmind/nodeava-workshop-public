"""Runtime settings loaded from env vars."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Orchestrator runtime settings.

    Default `bind_host` is 127.0.0.1 (localhost-only) — see the workshop
    MVP spec for the security rationale. LAN exposure requires explicit
    BIND_HOST=0.0.0.0 plus auth (added in a later plan).

    Provider defaults (`provider`, `provider_model`) are the DEPLOY-TIME
    default. Per-request body fields (`provider`, `model`) and headers
    (`X-Provider-Key`) override these — see orchestrator.providers.pick_provider.

    Tool defaults (`searxng_url`, `wiki_dir`) — Plan #3. SearXNG default
    points at the bundled container's Docker DNS name. Wiki dir is the
    on-disk Karpathy-style wiki the agent reads.
    """

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    ollama_url: str = "http://host.docker.internal:11434"
    request_timeout: float = 300.0
    bind_host: str = "127.0.0.1"
    bind_port: int = 8082

    # Provider selection — Plan #2
    provider: str = "local"
    provider_model: str = ""

    # Tools — Plan #3
    searxng_url: str = "http://searxng:8080"
    wiki_dir: str = "wiki"

    # State persistence — Plan #7 fix
    # The docker-compose.yml mounts ./state:/app/state:rw, so this path
    # survives container restarts. Override via STATE_PATH env var for tests.
    state_path: str = "/app/state/current.json"
