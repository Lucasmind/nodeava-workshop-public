"""Tests for state.py — atomic read/write of state/current.json."""
import json
from pathlib import Path

import pytest

from orchestrator.catalog import Catalog, AvatarEntry, BrainEntry, PersonalityEntry, VoiceEntry
from orchestrator.state import StateStore


def _make_catalog() -> Catalog:
    return Catalog(
        brains=[
            BrainEntry(id="qwen3-4b", label="Q", kind="ollama", model="qwen3:4b", default=True),
            BrainEntry(id="smollm2-360m", label="S", kind="ollama", model="smollm2:360m"),
        ],
        voices=[
            VoiceEntry(id="bella", label="B", kokoro_voice="af_bella", default=True),
            VoiceEntry(id="nova", label="N", kokoro_voice="af_nova"),
        ],
        avatars=[AvatarEntry(id="ava", label="A", glb_path="/x.glb", default=True)],
        personalities=[
            PersonalityEntry(id="default", label="D", system_prompt="x", default=True),
            PersonalityEntry(id="tutor", label="T", system_prompt="t"),
        ],
    )


def test_get_state_returns_defaults_when_file_missing(tmp_path):
    s = StateStore(path=tmp_path / "state.json", catalog=_make_catalog())
    state = s.get_state()
    assert state["brain"] == "qwen3-4b"
    assert state["voice"] == "bella"
    assert state["avatar"] == "ava"
    assert state["personality"] == "default"
    assert state["tools"] == {"web_search": False, "wiki": True}


def test_get_state_loads_from_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "brain": "smollm2-360m",
        "voice": "nova",
        "avatar": "ava",
        "personality": "tutor",
        "tools": {"web_search": True, "wiki": False},
    }))
    s = StateStore(path=path, catalog=_make_catalog())
    state = s.get_state()
    assert state["brain"] == "smollm2-360m"
    assert state["voice"] == "nova"
    assert state["personality"] == "tutor"
    assert state["tools"]["web_search"] is True


def test_set_state_writes_atomically(tmp_path):
    path = tmp_path / "state.json"
    s = StateStore(path=path, catalog=_make_catalog())
    new_state = s.set_state("brain", "smollm2-360m")
    assert new_state["brain"] == "smollm2-360m"
    on_disk = json.loads(path.read_text())
    assert on_disk["brain"] == "smollm2-360m"


def test_set_tool_uses_value_param(tmp_path):
    path = tmp_path / "state.json"
    s = StateStore(path=path, catalog=_make_catalog())
    new_state = s.set_tool("web_search", True)
    assert new_state["tools"]["web_search"] is True
    assert new_state["tools"]["wiki"] is True


def test_invalid_id_falls_back_to_default_on_load(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "brain": "deleted-from-catalog",
        "voice": "bella", "avatar": "ava", "personality": "default",
        "tools": {"web_search": False, "wiki": True},
    }))
    s = StateStore(path=path, catalog=_make_catalog())
    state = s.get_state()
    assert state["brain"] == "qwen3-4b"


def test_set_state_unknown_kind_raises(tmp_path):
    s = StateStore(path=tmp_path / "state.json", catalog=_make_catalog())
    with pytest.raises(ValueError):
        s.set_state("not-a-kind", "qwen3-4b")


def test_set_state_unknown_id_raises(tmp_path):
    s = StateStore(path=tmp_path / "state.json", catalog=_make_catalog())
    with pytest.raises(ValueError) as exc:
        s.set_state("brain", "no-such-brain")
    assert "no-such-brain" in str(exc.value)
