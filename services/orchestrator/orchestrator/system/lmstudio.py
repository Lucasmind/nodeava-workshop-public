"""LM Studio backend — model discovery + residency via the native /api/v0 API.

Parallels system/residency.py (OllamaResidency) so the dashboard's /v1/state +
/v1/swap responses are backend-agnostic. LM Studio's GET /api/v0/models returns
rich per-model info that Ollama's /api/tags + /api/ps cannot:

    {"data": [{"id", "type"("llm"|"vlm"|"embeddings"), "state"("loaded"|
               "not-loaded"), "arch", "quantization", "max_context_length"}, ...]}

Unlike Ollama, LM Studio does NOT report per-model VRAM bytes, so residency is
binary (loaded / not). Every method is best-effort and NEVER raises — a down or
absent LM Studio degrades to "unreachable", not a 500.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("orchestrator.system.lmstudio")

# Model types we surface as selectable chat brains. Embeddings models can't chat.
_CHAT_TYPES = {"llm", "vlm"}

# Substrings that mark a model as emitting <think>/reasoning output, so the
# frontend buffers until </think> instead of streaming tokens immediately.
_THINKS_HINTS = ("thinking", "reasoning", "deepseek-r1", "-r1", "magistral", "qwq")


def looks_like_thinker(model_id: str) -> bool:
    m = model_id.lower()
    return any(h in m for h in _THINKS_HINTS)


class LMStudioBackend:
    """Discovery + residency probe for a host-installed LM Studio server."""

    def __init__(self, *, base_url: str, timeout: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def list_models(self) -> list[dict[str, Any]]:
        """Chat-capable models (llm/vlm) with state. Empty list on any error."""
        data = await self._get_models()
        if not data:
            return []
        out: list[dict[str, Any]] = []
        for m in data:
            if m.get("type") not in _CHAT_TYPES:
                continue
            mid = m.get("id") or m.get("key") or ""
            if not mid:
                continue
            out.append(
                {
                    "id": mid,
                    "type": m.get("type"),
                    "state": m.get("state", "not-loaded"),
                    "arch": m.get("arch"),
                    "quant": m.get("quantization"),
                    "max_context_length": m.get("max_context_length"),
                    "loaded": m.get("state") == "loaded",
                    "thinks": looks_like_thinker(mid),
                }
            )
        return out

    async def query(self) -> dict[str, Any]:
        """Residency snapshot, shaped like OllamaResidency.query(). Never raises.

        Returns {"reachable": bool, "loaded": [{"model", "size_bytes",
        "size_vram_bytes", "residency"}]}. LM Studio gives no byte sizes, so
        those are 0 and residency is the literal "loaded" (the dashboard maps
        it to a green chip).
        """
        data = await self._get_models()
        if data is None:
            return {"reachable": False, "loaded": []}
        loaded: list[dict[str, Any]] = []
        for m in data:
            if m.get("state") != "loaded":
                continue
            mid = m.get("id") or m.get("key") or ""
            if not mid:
                continue
            loaded.append(
                {
                    "model": mid,
                    "size_bytes": 0,
                    "size_vram_bytes": 0,
                    "residency": "loaded",
                }
            )
        return {"reachable": True, "loaded": loaded}

    async def pick_model(self, *, fallback: str) -> str:
        """Resolve the "auto" brain to a concrete model id.

        Prefers a currently-loaded chat model (zero load latency); otherwise
        returns `fallback` (which JIT-loads on first chat request).
        """
        for m in await self.list_models():
            if m["loaded"]:
                return m["id"]
        return fallback

    async def _get_models(self) -> list[dict[str, Any]] | None:
        """GET /api/v0/models → list (possibly empty) or None when unreachable."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/api/v0/models")
                if resp.status_code >= 400:
                    log.warning("lmstudio /api/v0/models HTTP %d", resp.status_code)
                    return None
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.info("lmstudio /api/v0/models unreachable: %s", e)
            return None
        if isinstance(data, dict):
            return data.get("data") or []
        return data or []
