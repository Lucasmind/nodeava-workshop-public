"""Tests for orchestrator.system.residency."""
import httpx
import pytest
import respx

from orchestrator.system.residency import OllamaResidency, residency_label


def test_residency_label_gpu():
    assert residency_label(size_bytes=1000, size_vram_bytes=1000) == "gpu"


def test_residency_label_split():
    assert residency_label(size_bytes=1000, size_vram_bytes=400) == "split"


def test_residency_label_cpu():
    assert residency_label(size_bytes=1000, size_vram_bytes=0) == "cpu"


def test_residency_label_size_zero_returns_cpu():
    assert residency_label(size_bytes=0, size_vram_bytes=0) == "cpu"


@respx.mock
async def test_query_returns_normalized_loaded_models():
    respx.get("http://test-ollama:11434/api/ps").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen3:4b", "size": 1000, "size_vram": 1000},
                    {"name": "qwen3:7b", "size": 4000, "size_vram": 2500},
                ]
            },
        )
    )
    r = OllamaResidency(base_url="http://test-ollama:11434")
    result = await r.query()
    assert result["reachable"] is True
    assert len(result["loaded"]) == 2
    assert result["loaded"][0]["residency"] == "gpu"
    assert result["loaded"][1]["residency"] == "split"


@respx.mock
async def test_query_unreachable_returns_empty():
    respx.get("http://test-ollama:11434/api/ps").mock(
        side_effect=httpx.ConnectError("nope")
    )
    r = OllamaResidency(base_url="http://test-ollama:11434")
    result = await r.query()
    assert result["reachable"] is False
    assert result["loaded"] == []


@respx.mock
async def test_query_http_error_returns_empty():
    respx.get("http://test-ollama:11434/api/ps").mock(
        return_value=httpx.Response(500, text="boom")
    )
    r = OllamaResidency(base_url="http://test-ollama:11434")
    result = await r.query()
    assert result["reachable"] is False
    assert result["loaded"] == []
