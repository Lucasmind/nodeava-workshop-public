"""POST /v1/personality/custom — set a custom personality system prompt."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("orchestrator.routes.personality")
router = APIRouter()


class CustomPersonalityIn(BaseModel):
    system_prompt: str = Field(..., min_length=1)

    @field_validator("system_prompt")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("system_prompt must not be blank")
        return v


def _state_dir() -> Path:
    return Path(os.environ.get("NODEAVA_STATE_DIR", "state"))


def _custom_path() -> Path:
    return _state_dir() / "custom-personality.json"


def write_custom_personality(prompt: str) -> None:
    """Persist the custom prompt atomically (tempfile + rename)."""
    target = _custom_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"system_prompt": prompt}
    with tempfile.NamedTemporaryFile(
        "w", dir=target.parent, delete=False, encoding="utf-8"
    ) as tf:
        json.dump(payload, tf)
        tmp_path = Path(tf.name)
    tmp_path.replace(target)
    log.info("custom personality written (%d chars)", len(prompt))


def read_custom_personality() -> str | None:
    """Return the saved custom prompt, or None if no file exists."""
    p = _custom_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("system_prompt")
    except (OSError, json.JSONDecodeError) as e:
        log.warning("custom-personality.json unreadable: %s", e)
        return None


@router.post("/v1/personality/custom")
async def post_custom(payload: CustomPersonalityIn, request: Request) -> dict:
    write_custom_personality(payload.system_prompt)

    catalog = request.app.state.catalog
    catalog.register_custom_personality(payload.system_prompt)

    store = request.app.state.state_store
    store.set_state("personality", "custom")

    residency = request.app.state.residency
    return {
        "active": store.get_state(),
        "system": {"ollama": await residency.query()},
    }
