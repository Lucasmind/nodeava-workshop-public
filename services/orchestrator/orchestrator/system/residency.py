"""Ollama residency probe — single source of truth for what's in VRAM right now.

Queries Ollama's GET /api/ps. Output is normalized into a dict that the
dashboard can render directly. No native GPU libraries; Ollama is canonical.
"""
import logging
from typing import Any

import httpx

log = logging.getLogger("orchestrator.system.residency")


def residency_label(*, size_bytes: int, size_vram_bytes: int) -> str:
    """Categorize a model's memory residency.

    - 'gpu'   : fully in VRAM (size_vram == size)
    - 'split' : partially in VRAM (0 < size_vram < size)
    - 'cpu'   : fully in system memory (size_vram == 0, including edge size==0)
    """
    if size_bytes <= 0 or size_vram_bytes <= 0:
        return "cpu"
    if size_vram_bytes >= size_bytes:
        return "gpu"
    return "split"


class OllamaResidency:
    def __init__(self, *, base_url: str, timeout: float = 1.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def query(self) -> dict[str, Any]:
        """Return {reachable: bool, loaded: [...]}. Never raises."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/api/ps")
                if resp.status_code >= 400:
                    log.warning("ollama /api/ps HTTP %d", resp.status_code)
                    return {"reachable": False, "loaded": []}
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.info("ollama /api/ps unreachable: %s", e)
            return {"reachable": False, "loaded": []}

        loaded = []
        for m in (data.get("models") or []):
            size_bytes = int(m.get("size") or 0)
            size_vram_bytes = int(m.get("size_vram") or 0)
            loaded.append({
                "model": m.get("name") or m.get("model") or "",
                "size_bytes": size_bytes,
                "size_vram_bytes": size_vram_bytes,
                "residency": residency_label(
                    size_bytes=size_bytes,
                    size_vram_bytes=size_vram_bytes,
                ),
            })
        return {"reachable": True, "loaded": loaded}
