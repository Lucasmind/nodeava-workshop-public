"""Tests for HTTP routes."""
import respx
from httpx import Response


async def test_app_imports_and_serves_404_for_unknown_route(app_client):
    """Smoke test: the app boots and serves an unknown path with 404."""
    resp = await app_client.get("/does-not-exist")
    assert resp.status_code == 404


@respx.mock
async def test_health_ok_when_backend_healthy(app_client):
    # Health check probes Ollama root (GET /) — Ollama has no /health endpoint.
    respx.get("http://host.docker.internal:11434/").mock(return_value=Response(200))
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "backend": "http://host.docker.internal:11434"}


@respx.mock
async def test_health_503_when_backend_unhealthy(app_client):
    # Health check probes Ollama root (GET /) — Ollama has no /health endpoint.
    respx.get("http://host.docker.internal:11434/").mock(return_value=Response(500))
    resp = await app_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert "backend" in body


@respx.mock
async def test_models_proxies_backend_list(app_client):
    """GET /v1/models proxies the backend's /v1/models response."""
    respx.get("http://host.docker.internal:11434/v1/models").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [{"id": "qwen3-4b", "object": "model"}],
            },
        )
    )
    resp = await app_client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json()["data"][0]["id"] == "qwen3-4b"


@respx.mock
async def test_models_returns_empty_list_if_backend_down(app_client):
    """If the backend is unreachable we return an empty list, not 500."""
    import httpx

    respx.get("http://host.docker.internal:11434/v1/models").mock(
        side_effect=httpx.ConnectError("down")
    )
    resp = await app_client.get("/v1/models")
    assert resp.status_code == 200
    assert resp.json() == {"object": "list", "data": []}


@respx.mock
async def test_chat_non_streaming_returns_openai_shape(app_client):
    """Non-streaming chat returns an OpenAI-shaped JSON response with the
    full text in choices[0].message.content."""
    respx.post("http://host.docker.internal:11434/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Greetings."},
                        "finish_reason": "stop",
                    }
                ]
            },
        )
    )

    resp = await app_client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "Greetings."
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["object"] == "chat.completion"


import json


@respx.mock
async def test_chat_streaming_emits_openai_chunks_then_done(app_client):
    """Streaming chat: each TokenEvent → an OpenAI-shaped `data: {...}` chunk;
    FinalDoneEvent → `data: [DONE]`."""
    sse_body = (
        b'data: {"choices":[{"delta":{"role":"assistant"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"Hi"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"!"},"index":0,"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n'
        b'data: [DONE]\n\n'
    )
    respx.post("http://host.docker.internal:11434/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=sse_body,
            headers={"content-type": "text/event-stream"},
        )
    )

    async with app_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = (await resp.aread()).decode()

    # Parse the SSE body: collect content from data: chunks before [DONE].
    contents = []
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        chunk = json.loads(payload)
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta:
            contents.append(delta["content"])

    assert contents == ["Hi", "!"]
    assert body.rstrip().endswith("data: [DONE]")


def test_run_uses_settings_bind_host_and_port(monkeypatch):
    """`run()` must pass settings.bind_host / settings.bind_port to uvicorn —
    so the localhost-only default isn't silently bypassed."""
    from orchestrator import main as orch_main

    captured = {}

    def fake_run(app_target, *, host, port, log_level):  # noqa: ARG001
        captured["host"] = host
        captured["port"] = port
        captured["app_target"] = app_target

    monkeypatch.setattr("uvicorn.run", fake_run)
    orch_main.app.state.settings.bind_host = "203.0.113.4"
    orch_main.app.state.settings.bind_port = 9999
    try:
        orch_main.run()
    finally:
        orch_main.app.state.settings.bind_host = "127.0.0.1"
        orch_main.app.state.settings.bind_port = 8082

    assert captured["host"] == "203.0.113.4"
    assert captured["port"] == 9999
    assert captured["app_target"] == "orchestrator.main:app"


async def test_chat_provider_override_routes_to_litellm(orch_app, app_client, monkeypatch):
    """Plan #7: state brain="claude-sonnet" + X-Provider-Key header → LiteLLM,
    not the local llama-server. Verify by intercepting litellm.acompletion.

    Body fields (provider, model) are now ignored — state is canonical.
    """
    from types import SimpleNamespace
    import litellm

    # Set brain to the cloud-litellm entry in the catalog
    orch_app.state.state_store.set_state("brain", "claude-sonnet")

    captured = {}

    async def fake_acompletion(*, model, messages, stream, api_key, **kwargs):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["stream"] = stream
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="From cloud", role="assistant"),
                finish_reason="stop",
            )]
        )

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    resp = await app_client.post(
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"X-Provider-Key": "sk-ant-routed"},
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "From cloud"
    # catalog has model="anthropic/claude-sonnet-4-6" for the claude-sonnet brain
    assert captured["model"] == "anthropic/claude-sonnet-4-6"
    assert captured["api_key"] == "sk-ant-routed"
    assert captured["stream"] is False


async def test_chat_streaming_emits_thinking_on_named_channel(orch_app, app_client, monkeypatch):
    """Plan #7: state brain="claude-sonnet" (cloud-litellm) → streaming with
    thinking should send ThinkingTokenEvent on its named SSE channel — NEVER
    mixed into the OpenAI-style `data:` content stream.

    Body fields (provider, model) are now ignored — state is canonical.
    """
    from types import SimpleNamespace
    import json
    import litellm

    # Set brain to the cloud-litellm entry in the catalog
    orch_app.state.state_store.set_state("brain", "claude-sonnet")

    async def fake_acompletion(*, model, messages, stream, api_key, **kwargs):
        async def gen():
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    role="assistant",
                    thinking_blocks=[{"type": "thinking", "thinking": "hmm"}],
                ),
                finish_reason=None,
            )])
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content="Hello.", role=None),
                finish_reason=None,
            )])
            yield SimpleNamespace(choices=[SimpleNamespace(
                delta=SimpleNamespace(content=None, role=None),
                finish_reason="stop",
            )])
        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)

    async with app_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": "say hi"}],
            "stream": True,
        },
        headers={"X-Provider-Key": "sk-ant-stream"},
    ) as resp:
        assert resp.status_code == 200
        body = (await resp.aread()).decode()

    # Visible content (OpenAI chunks on default stream)
    visible_contents = []
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta and delta["content"]:
            visible_contents.append(delta["content"])

    assert visible_contents == ["Hello."]

    # Thinking events on the named SSE channel
    assert "event: thinking_token" in body
    # Each thinking event has its own data line with the delta
    assert '"delta": "hmm"' in body or '"delta":"hmm"' in body

    # Thinking content MUST NOT appear in any default-stream content chunk
    for c in visible_contents:
        assert "hmm" not in c


async def test_chat_with_web_search_toggle_runs_agentic_loop(orch_app, app_client, monkeypatch):
    """Plan #7: state.tools.web_search=True → tools injected; tool calls
    executed; tool_call_start and tool_call_end events appear on the SSE stream.

    Body field web_search is now ignored — state is canonical.
    """
    from types import SimpleNamespace
    import json
    import httpx
    import respx

    # Mock SearXNG so browser.search has something to return
    # Note: use the context manager object (mock) to register routes so they
    # are scoped to this router — calling the global respx.get/post inside a
    # `with respx.mock(...)` block registers on the global router, not the
    # context router, causing AllMockedAssertionError for other requests.
    # Enable web_search in state (body field is ignored in Plan #7)
    orch_app.state.state_store.set_tool("web_search", True)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("http://searxng:8080/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"title": "Foo", "url": "https://example.com/foo", "content": "bar"}
                    ]
                },
            )
        )

        # The local llm needs to (a) ask for the search tool, (b) return content next.
        # Sequence two responses:
        call_count = {"n": 0}

        def llm_responder(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "browser.search",
                                                "arguments": '{"query":"foo"}',
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Done."},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )

        mock.post("http://host.docker.internal:11434/v1/chat/completions").mock(
            side_effect=llm_responder
        )

        async with app_client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "search foo"}],
                "stream": True,
            },
        ) as resp:
            assert resp.status_code == 200
            body = (await resp.aread()).decode()

    # The stream should contain a named tool_call_start event for browser.search
    assert "event: tool_call_start" in body
    assert "browser.search" in body
    assert "event: tool_call_end" in body
    # The final visible content "Done." should appear on the default `data:` stream
    contents = []
    for line in body.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if "content" in delta and delta["content"]:
            contents.append(delta["content"])
    assert "Done." in "".join(contents)


async def test_chat_without_toggles_skips_agentic_loop(app_client, monkeypatch):
    """No web_search/wiki body field → direct provider.chat() path, no tool events."""
    import respx
    import httpx

    with respx.mock:
        respx.post("http://host.docker.internal:11434/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Plain."},
                            "finish_reason": "stop",
                        }
                    ]
                },
            )
        )
        resp = await app_client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "Plain."
