"""State store — read/write the active selections (brain/voice/avatar/personality/tools).

Single user, single dashboard, single laptop. No locks. Atomic write
(tempfile + rename) guarantees concurrent reads see either the old or new
file, never a half-written one.

Invalid ids (e.g. the catalog removed an entry while state.json still
references it) fall back to the catalog default on load. set_state validates
the target id against the catalog and refuses unknown values.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from orchestrator.catalog import Catalog

log = logging.getLogger("orchestrator.state")

_DEFAULT_TOOLS = {"web_search": False, "wiki": True}
_VALID_KINDS = {"brain", "voice", "avatar", "personality"}


class StateStore:
    def __init__(self, *, path: Path | str, catalog: Catalog) -> None:
        self._path = Path(path)
        self._catalog = catalog
        self._cache: dict[str, Any] | None = None

    def get_state(self) -> dict[str, Any]:
        if self._cache is None:
            self._cache = self._load_or_default()
        return dict(self._cache, tools=dict(self._cache["tools"]))

    def set_state(self, kind: str, id_: str) -> dict[str, Any]:
        if kind not in _VALID_KINDS:
            raise ValueError(f"unknown kind '{kind}' (valid: {sorted(_VALID_KINDS)})")
        lookup = {
            "brain": self._catalog.brain,
            "voice": self._catalog.voice,
            "avatar": self._catalog.avatar,
            "personality": self._catalog.personality,
        }[kind]
        try:
            lookup(id_)
        except Exception as e:
            raise ValueError(f"unknown {kind} id '{id_}': {e}") from e
        state = self.get_state()
        state[kind] = id_
        self._write(state)
        return state

    def set_tool(self, name: str, value: bool) -> dict[str, Any]:
        if name not in _DEFAULT_TOOLS:
            raise ValueError(f"unknown tool '{name}' (valid: {sorted(_DEFAULT_TOOLS)})")
        if not isinstance(value, bool):
            raise ValueError(f"tool '{name}' value must be a bool, got {type(value).__name__}")
        state = self.get_state()
        state["tools"][name] = value
        self._write(state)
        return state

    def _defaults(self) -> dict[str, Any]:
        return {
            "brain": self._catalog.default_brain().id,
            "voice": self._catalog.default_voice().id,
            "avatar": self._catalog.default_avatar().id,
            "personality": self._catalog.default_personality().id,
            "tools": dict(_DEFAULT_TOOLS),
        }

    def _load_or_default(self) -> dict[str, Any]:
        if not self._path.is_file():
            log.info("state file %s missing; using catalog defaults", self._path)
            return self._defaults()
        try:
            on_disk = json.loads(self._path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("state file %s unreadable (%s); using defaults", self._path, e)
            return self._defaults()
        defaults = self._defaults()
        patched: dict[str, Any] = {}
        for kind in ("brain", "voice", "avatar", "personality"):
            stored = on_disk.get(kind)
            try:
                lookup = {
                    "brain": self._catalog.brain,
                    "voice": self._catalog.voice,
                    "avatar": self._catalog.avatar,
                    "personality": self._catalog.personality,
                }[kind]
                if stored:
                    lookup(stored)
                    patched[kind] = stored
                else:
                    patched[kind] = defaults[kind]
            except Exception:
                log.warning(
                    "state %s='%s' not in catalog; falling back to default '%s'",
                    kind, stored, defaults[kind],
                )
                patched[kind] = defaults[kind]
        stored_tools = on_disk.get("tools") or {}
        patched["tools"] = {
            k: bool(stored_tools.get(k, defaults["tools"][k]))
            for k in _DEFAULT_TOOLS
        }
        return patched

    def _write(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".state-", suffix=".tmp", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        self._cache = dict(state, tools=dict(state["tools"]))
