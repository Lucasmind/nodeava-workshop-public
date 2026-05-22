"""Catalog — single source of truth for swappable brains / voices / avatars
/ personalities. Parsed once from configs/catalog.yml at orchestrator startup.

Validation is strict: missing fields, unknown kinds, or no `default: true` in
a section all raise CatalogError at startup. The catalog is foundational; we
want fail-fast, not silent fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CatalogError(Exception):
    """Raised on any catalog-validation problem."""


_VALID_BRAIN_KINDS = {"ollama", "cloud-litellm", "openai-compatible", "lmstudio"}


@dataclass
class BrainEntry:
    id: str
    label: str
    kind: str
    model: str
    default: bool = False
    requires_key: str | None = None
    url: str | None = None
    # True if this model emits reasoning (<think> blocks or thinking-finetune
    # output). The dashboard / frontend uses this to decide whether to wait
    # for </think> before streaming, vs. stream tokens immediately.
    thinks: bool = False
    # True for brains injected at runtime from LM Studio discovery (Plan #11).
    # These are replaced wholesale on each catalog refresh, never persisted to
    # configs/catalog.yml.
    dynamic: bool = False


@dataclass
class VoiceEntry:
    id: str
    label: str
    kokoro_voice: str
    default: bool = False


@dataclass
class AvatarEntry:
    id: str
    label: str
    glb_path: str
    default: bool = False
    body: str = "F"  # Plan #10 — 'F' or 'M', passed to TalkingHead showAvatar


@dataclass
class PersonalityEntry:
    id: str
    label: str
    system_prompt: str
    default: bool = False


@dataclass
class Catalog:
    brains: list[BrainEntry] = field(default_factory=list)
    voices: list[VoiceEntry] = field(default_factory=list)
    avatars: list[AvatarEntry] = field(default_factory=list)
    personalities: list[PersonalityEntry] = field(default_factory=list)

    def brain(self, id_: str) -> BrainEntry:
        return _get_or_raise(self.brains, id_, "brain")

    def voice(self, id_: str) -> VoiceEntry:
        return _get_or_raise(self.voices, id_, "voice")

    def avatar(self, id_: str) -> AvatarEntry:
        return _get_or_raise(self.avatars, id_, "avatar")

    def personality(self, id_: str) -> PersonalityEntry:
        return _get_or_raise(self.personalities, id_, "personality")

    def default_brain(self) -> BrainEntry:
        return _default_or_raise(self.brains, "brain")

    def default_voice(self) -> VoiceEntry:
        return _default_or_raise(self.voices, "voice")

    def default_avatar(self) -> AvatarEntry:
        return _default_or_raise(self.avatars, "avatar")

    def default_personality(self) -> PersonalityEntry:
        return _default_or_raise(self.personalities, "personality")

    def sync_dynamic_brains(self, models: list[dict]) -> list[BrainEntry]:
        """Plan #11 — replace LM Studio-discovered brains with the current set.

        `models` is LMStudioBackend.list_models() output. Existing dynamic
        entries are dropped and rebuilt so unload/rename in LM Studio is
        reflected. Loaded models sort first (zero load latency). Returns the new
        dynamic entries so the catalog route can annotate availability without
        re-probing. Static (catalog.yml) brains are never touched.
        """
        self.brains = [b for b in self.brains if not b.dynamic]
        added: list[BrainEntry] = []
        for m in sorted(
            models, key=lambda x: (not x.get("loaded"), str(x.get("id", "")).lower())
        ):
            mid = m["id"]
            entry = BrainEntry(
                id=f"lmstudio:{mid}",
                label=mid + ("  (loaded)" if m.get("loaded") else ""),
                kind="lmstudio",
                model=mid,
                thinks=bool(m.get("thinks", False)),
                dynamic=True,
            )
            self.brains.append(entry)
            added.append(entry)
        return added

    def register_custom_personality(self, system_prompt: str) -> None:
        """Plan #10 — register or overwrite the 'custom' personality entry."""
        entry = PersonalityEntry(
            id="custom",
            label="My Personality (custom)",
            system_prompt=system_prompt,
            default=False,
        )
        for i, p in enumerate(self.personalities):
            if p.id == "custom":
                self.personalities[i] = entry
                return
        self.personalities.append(entry)


def _get_or_raise(items, id_: str, label: str):
    for item in items:
        if item.id == id_:
            return item
    raise CatalogError(f"no {label} with id '{id_}'")


def _default_or_raise(items, label: str):
    for item in items:
        if item.default:
            return item
    raise CatalogError(f"no default {label} (one entry must set default: true)")


def load_catalog(path: Path | str) -> Catalog:
    p = Path(path)
    if not p.is_file():
        raise CatalogError(f"catalog not found: {p}")

    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        raise CatalogError(f"catalog YAML parse error: {e}") from e

    if not isinstance(data, dict):
        raise CatalogError("catalog root must be a mapping")

    brains = [_parse_brain(b) for b in (data.get("brains") or [])]
    voices = [_parse_voice(v) for v in (data.get("voices") or [])]
    avatars = [_parse_avatar(a) for a in (data.get("avatars") or [])]
    personalities = [_parse_personality(p_) for p_ in (data.get("personalities") or [])]

    cat = Catalog(brains=brains, voices=voices, avatars=avatars, personalities=personalities)
    cat.default_brain()
    cat.default_voice()
    cat.default_avatar()
    cat.default_personality()

    # Plan #10 — restore custom personality from disk if present
    from orchestrator.routes.personality import read_custom_personality
    custom = read_custom_personality()
    if custom:
        cat.register_custom_personality(custom)

    return cat


def _require(d: dict, key: str, section: str) -> Any:
    if key not in d or d[key] in (None, ""):
        raise CatalogError(f"{section} entry missing '{key}': {d!r}")
    return d[key]


def _parse_brain(d: dict) -> BrainEntry:
    id_ = _require(d, "id", "brains")
    label = _require(d, "label", "brains")
    kind = _require(d, "kind", "brains")
    model = _require(d, "model", "brains")
    if kind not in _VALID_BRAIN_KINDS:
        raise CatalogError(
            f"brain '{id_}' has unknown kind '{kind}' "
            f"(valid: {sorted(_VALID_BRAIN_KINDS)})"
        )
    requires_key = d.get("requires_key")
    url = d.get("url")
    if kind == "cloud-litellm" and not requires_key:
        raise CatalogError(
            f"brain '{id_}' kind=cloud-litellm requires 'requires_key' field"
        )
    if kind == "openai-compatible" and not url:
        raise CatalogError(
            f"brain '{id_}' kind=openai-compatible requires 'url' field"
        )
    return BrainEntry(
        id=id_, label=label, kind=kind, model=model,
        default=bool(d.get("default", False)),
        requires_key=requires_key, url=url,
        thinks=bool(d.get("thinks", False)),
    )


def _parse_voice(d: dict) -> VoiceEntry:
    return VoiceEntry(
        id=_require(d, "id", "voices"),
        label=_require(d, "label", "voices"),
        kokoro_voice=_require(d, "kokoro_voice", "voices"),
        default=bool(d.get("default", False)),
    )


def _parse_avatar(d: dict) -> AvatarEntry:
    return AvatarEntry(
        id=_require(d, "id", "avatars"),
        label=_require(d, "label", "avatars"),
        glb_path=_require(d, "glb_path", "avatars"),
        default=bool(d.get("default", False)),
        body=d.get("body", "F"),
    )


def _parse_personality(d: dict) -> PersonalityEntry:
    return PersonalityEntry(
        id=_require(d, "id", "personalities"),
        label=_require(d, "label", "personalities"),
        system_prompt=_require(d, "system_prompt", "personalities"),
        default=bool(d.get("default", False)),
    )
