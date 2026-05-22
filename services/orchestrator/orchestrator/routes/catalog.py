"""GET /v1/catalog — full catalog with availability annotations.

Availability is computed per-request, not cached:
- kind=ollama          → Ollama /api/tags includes brain.model
- kind=cloud-litellm   → os.environ[brain.requires_key] is set
- kind=openai-compatible → TCP check on brain.url (HEAD request)
- kind=lmstudio        → LM Studio reachable (model JIT-loads on first use);
                         annotated with loaded-state from /api/v0/models
- Avatars              → file at glb_path exists on disk

Plan #11: when llm_backend == "lmstudio", the LM Studio library is discovered
and each model merged into the catalog as a selectable lmstudio:<id> brain
(see Catalog.sync_dynamic_brains). This is what makes the dashboard's brain
dropdown list every model the user has in LM Studio, with loaded ones first.
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Request

log = logging.getLogger("orchestrator.routes.catalog")
router = APIRouter()


@router.get("/v1/catalog")
async def get_catalog(request: Request) -> dict:
    catalog = request.app.state.catalog
    settings = request.app.state.settings
    ollama_tags = await _fetch_ollama_tags(settings.ollama_url)

    # Plan #11: discover the LM Studio library and merge it as dynamic brains.
    # Best-effort — a down/absent LM Studio just yields no dynamic brains and
    # marks the static lmstudio brains unavailable (no exception bubbles up).
    lmstudio_info = None
    if settings.llm_backend == "lmstudio":
        lmstudio = getattr(request.app.state, "lmstudio", None)
        reachable, loaded = False, set()
        if lmstudio is not None:
            models = await lmstudio.list_models()
            catalog.sync_dynamic_brains(models)
            if models:
                reachable = True
                loaded = {m["id"] for m in models if m.get("loaded")}
            else:
                snap = await lmstudio.query()
                reachable = bool(snap.get("reachable"))
        lmstudio_info = {"reachable": reachable, "loaded": loaded}

    brains_out = []
    for b in catalog.brains:
        entry = {
            "id": b.id, "label": b.label, "kind": b.kind, "model": b.model,
            "default": b.default, "thinks": b.thinks,
        }
        if b.requires_key:
            entry["requires_key"] = b.requires_key
        if b.url:
            entry["url"] = b.url
        if b.dynamic:
            entry["dynamic"] = True
        entry.update(await _brain_availability(b, ollama_tags, lmstudio_info))
        brains_out.append(entry)

    voices_out = [
        {"id": v.id, "label": v.label, "kokoro_voice": v.kokoro_voice,
         "default": v.default, "available": True}
        for v in catalog.voices
    ]

    avatars_out = [
        {"id": a.id, "label": a.label, "glb_path": a.glb_path,
         "default": a.default, "available": True}
        for a in catalog.avatars
    ]

    personalities_out = [
        {"id": p.id, "label": p.label, "system_prompt": p.system_prompt,
         "default": p.default, "available": True}
        for p in catalog.personalities
    ]

    return {
        "brains": brains_out,
        "voices": voices_out,
        "avatars": avatars_out,
        "personalities": personalities_out,
    }


async def _fetch_ollama_tags(ollama_url: str) -> set[str]:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{ollama_url.rstrip('/')}/api/tags")
            if resp.status_code != 200:
                return set()
            data = resp.json()
        return {m.get("name") or m.get("model") for m in (data.get("models") or [])}
    except (httpx.HTTPError, ValueError):
        return set()


async def _brain_availability(brain, ollama_tags: set[str], lmstudio_info: dict | None) -> dict:
    if brain.kind == "ollama":
        if brain.model in ollama_tags:
            return {"available": True}
        return {"available": False, "reason": f"run: ollama pull {brain.model}"}
    if brain.kind == "cloud-litellm":
        if brain.requires_key and os.environ.get(brain.requires_key):
            return {"available": True}
        return {"available": False, "reason": f"set env: {brain.requires_key}"}
    if brain.kind == "openai-compatible":
        try:
            async with httpx.AsyncClient(timeout=0.5) as client:
                resp = await client.get(f"{brain.url.rstrip('/')}/models")
                if resp.status_code < 500:
                    return {"available": True}
                return {"available": False, "reason": f"server HTTP {resp.status_code}"}
        except httpx.HTTPError:
            return {"available": False, "reason": f"unreachable at {brain.url}"}
    if brain.kind == "lmstudio":
        if lmstudio_info is None:
            return {"available": False, "reason": "LM Studio backend not active"}
        if not lmstudio_info["reachable"]:
            return {"available": False, "reason": "LM Studio unreachable"}
        # Reachable → available (LM Studio JIT-loads the model on first request).
        # "auto" follows whatever is loaded; concrete models report their state.
        if brain.model in ("auto", ""):
            return {"available": True, "loaded": False}
        return {"available": True, "loaded": brain.model in lmstudio_info["loaded"]}
    return {"available": False, "reason": "unknown brain kind"}
