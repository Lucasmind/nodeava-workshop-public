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


@respx.mock
async def test_chat_runtime_availability_block_when_websearch_off(app_client, orch_app):
    """Regression: when web_search is OFF but wiki is ON, the personality system
    prompt must carry a runtime "browser.* DISABLED" note. Otherwise the model
    keeps emitting browser.search per the trigger map and hits the unknown-tool
    loop for 8 rounds (~24s) before the forced final answer.
    """
    orch_app.state.state_store.set_tool("wiki", True)
    orch_app.state.state_store.set_tool("web_search", False)

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
        json={"messages": [{"role": "user", "content": "what's the latest news"}],
              "stream": False},
    )
    assert resp.status_code == 200

    sent_messages = captured["body"]["messages"]
    sys_prompt = sent_messages[0]["content"]

    # The runtime availability block must be present
    assert "RUNTIME TOOL AVAILABILITY" in sys_prompt
    # Wiki is ON
    assert "wiki.* tools are ENABLED" in sys_prompt
    # browser is OFF — explicit "do not try" wording
    assert "browser.* tools are DISABLED" in sys_prompt
    assert "Do not attempt browser.search" in sys_prompt
    # And the user-facing fallback phrasing is included so the model knows what to say
    assert "web search is currently turned off" in sys_prompt


@respx.mock
async def test_chat_runtime_availability_block_when_both_on(app_client, orch_app):
    """Both toggles on → both families marked ENABLED in the runtime block."""
    orch_app.state.state_store.set_tool("wiki", True)
    orch_app.state.state_store.set_tool("web_search", True)

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

    await app_client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    sys_prompt = captured["body"]["messages"][0]["content"]
    assert "wiki.* tools are ENABLED" in sys_prompt
    assert "browser.* tools are ENABLED" in sys_prompt
    assert "DISABLED" not in sys_prompt.split("RUNTIME TOOL AVAILABILITY")[-1]


@respx.mock
async def test_chat_runtime_availability_block_when_both_off(app_client, orch_app):
    """Both off → both DISABLED. Model should answer from memory with no tool attempts."""
    orch_app.state.state_store.set_tool("wiki", False)
    orch_app.state.state_store.set_tool("web_search", False)

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

    await app_client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    sys_prompt = captured["body"]["messages"][0]["content"]
    assert "wiki.* tools are DISABLED" in sys_prompt
    assert "browser.* tools are DISABLED" in sys_prompt
