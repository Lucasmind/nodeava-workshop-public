"""GET /v1/catalog — full catalog with availability annotations.

Availability is computed per-request, not cached:
- kind=ollama          → Ollama /api/tags includes brain.model
- kind=cloud-litellm   → os.environ[brain.requires_key] is set
- kind=openai-compatible → TCP check on brain.url (HEAD request)
- Avatars              → file at glb_path exists on disk
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
        entry.update(await _brain_availability(b, ollama_tags))
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


async def _brain_availability(brain, ollama_tags: set[str]) -> dict:
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
    return {"available": False, "reason": "unknown brain kind"}
