"""Regression tests for chat route personality system_prompt injection.

Plan #7 Opus review fix: the chat route injects the active personality's
system_prompt when the caller does not supply a system message. This is the
load-bearing pedagogy of Plan #5/#6 (the workshop swaps personality mid-demo).
"""
import json

import httpx
import pytest
import respx


@respx.mock
async def test_chat_injects_personality_system_prompt(app_client):
    """No caller system message → personality system_prompt prepended."""
    captured = {}

    def _capture(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    respx.post("http://host.docker.internal:11434/v1/chat/completions").mock(
        side_effect=_capture
    )

    resp = await app_client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    assert resp.status_code == 200

    sent_messages = captured["body"]["messages"]
    assert len(sent_messages) >= 2
    # First message must be the injected personality system prompt
    assert sent_messages[0]["role"] == "system"
    # Default catalog personality mentions NodeAva
    assert "NodeAva" in sent_messages[0]["content"]
    # Original user message must be the last entry and unchanged
    assert sent_messages[-1] == {"role": "user", "content": "hi"}


@respx.mock
async def test_chat_appends_personality_after_caller_system_message(app_client):
    """When the caller supplies a system message (frontend's TTS-friendly speech rules),
    the orchestrator KEEPS it AND appends the personality system_prompt after it. Both
    are active — the frontend's output-format guidance + the catalog personality's
    behavior guidance (wiki-priming, persona flavor)."""
    captured = {}

    def _capture(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    respx.post("http://host.docker.internal:11434/v1/chat/completions").mock(
        side_effect=_capture
    )

    resp = await app_client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "system", "content": "You are a custom persona."},
                {"role": "user", "content": "hi"},
            ],
            "stream": False,
        },
    )
    assert resp.status_code == 200

    sent_messages = captured["body"]["messages"]
    # The catalog personality must come FIRST (primary identity + tool behavior).
    assert sent_messages[0]["role"] == "system"
    assert "NodeAva" in sent_messages[0]["content"]  # default personality references NodeAva
    # The caller's system message follows (output-format guidance).
    assert sent_messages[1]["role"] == "system"
    assert sent_messages[1]["content"] == "You are a custom persona."
    # User message preserved at end.
    assert sent_messages[-1] == {"role": "user", "content": "hi"}
