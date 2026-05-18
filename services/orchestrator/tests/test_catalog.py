"""Tests for the catalog loader."""
import textwrap
from pathlib import Path

import pytest

from orchestrator.catalog import Catalog, CatalogError, load_catalog


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "catalog.yml"
    p.write_text(textwrap.dedent(content))
    return p


def test_load_valid_catalog(tmp_path):
    path = _write(tmp_path, """
        brains:
          - id: qwen3-4b
            label: Q
            kind: ollama
            model: qwen3:4b
            default: true
        voices:
          - id: bella
            label: B
            kokoro_voice: af_bella
            default: true
        avatars:
          - id: ava
            label: A
            glb_path: /avatars/a.glb
            default: true
        personalities:
          - id: default
            label: D
            system_prompt: hi
            default: true
    """)
    c = load_catalog(path)
    assert isinstance(c, Catalog)
    assert c.brain("qwen3-4b").model == "qwen3:4b"


def test_default_brain_is_resolved(tmp_path):
    path = _write(tmp_path, """
        brains:
          - id: foo
            label: F
            kind: ollama
            model: foo:1b
            default: true
          - id: bar
            label: B
            kind: ollama
            model: bar:1b
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    c = load_catalog(path)
    assert c.default_brain().id == "foo"


def test_missing_default_in_a_section_raises(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: ollama, model: a:1b}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "default" in str(exc.value).lower()
    assert "brain" in str(exc.value).lower()


def test_unknown_brain_kind_raises(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: weird, model: a:1b, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "kind" in str(exc.value).lower()


def test_cloud_litellm_requires_requires_key(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: cloud-litellm, model: a/b, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "requires_key" in str(exc.value)


def test_openai_compatible_requires_url(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: a, label: A, kind: openai-compatible, model: a, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    with pytest.raises(CatalogError) as exc:
        load_catalog(path)
    assert "url" in str(exc.value).lower()


def test_lookup_unknown_id_raises(tmp_path):
    path = _write(tmp_path, """
        brains:
          - {id: qwen, label: Q, kind: ollama, model: qwen:1b, default: true}
        voices:
          - {id: v, label: V, kokoro_voice: af_x, default: true}
        avatars:
          - {id: a, label: A, glb_path: /a, default: true}
        personalities:
          - {id: d, label: D, system_prompt: x, default: true}
    """)
    c = load_catalog(path)
    with pytest.raises(CatalogError):
        c.brain("missing")
