"""Tests for orchestrator.providers.dispatcher."""
import pytest

from orchestrator.catalog import BrainEntry
from orchestrator.providers.dispatcher import dispatch_for_brain
from orchestrator.providers.ollama import OllamaProvider
from orchestrator.providers.litellm_provider import LiteLLMProvider


def test_dispatch_ollama_brain_returns_ollama_provider():
    brain = BrainEntry(id="q", label="Q", kind="ollama", model="qwen3:4b")
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
    assert isinstance(p, OllamaProvider)


def test_dispatch_cloud_litellm_requires_api_key():
    brain = BrainEntry(
        id="c", label="C", kind="cloud-litellm",
        model="anthropic/claude-3", requires_key="ANTHROPIC_API_KEY",
    )
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
    assert hasattr(p, "_missing_key_brain_id")


def test_dispatch_cloud_litellm_with_key_returns_litellm():
    brain = BrainEntry(
        id="c", label="C", kind="cloud-litellm",
        model="anthropic/claude-3", requires_key="ANTHROPIC_API_KEY",
    )
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key="sk-x")
    assert isinstance(p, LiteLLMProvider)


def test_dispatch_openai_compatible_returns_ollama_shaped_provider():
    """openai-compatible reuses OllamaProvider since the wire format is the same."""
    brain = BrainEntry(
        id="ex", label="EX", kind="openai-compatible",
        model="some-model", url="http://my-llama:8081/v1",
    )
    p = dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
    assert isinstance(p, OllamaProvider)
    assert p._base_url == "http://my-llama:8081/v1"


def test_dispatch_unknown_kind_raises():
    brain = BrainEntry(id="?", label="?", kind="weird", model="x")
    with pytest.raises(ValueError):
        dispatch_for_brain(brain, ollama_url="http://o:11434", request_timeout=10.0, api_key=None)
