"""Chat completions route — direct provider passthrough OR agentic loop.

The route layer is thin: parses the OpenAI request body, reads the active
brain and personality from app.state.state_store, picks a Provider via
`dispatch_for_brain(brain, ...)`, then either:

  - Calls `provider.chat()` directly (Plan #1+#2 behavior)
  - Wraps it in `agentic_loop()` (Plan #4) — multi-round, tool-executing

Streaming routing rules (both paths):
  - TokenEvent           → OpenAI streaming chunk on default `data:` stream
  - ThinkingTokenEvent   → encode_sse, named `event: thinking_token`
  - ToolCallStartEvent   → encode_sse, named `event: tool_call_start`
  - ToolCallEndEvent     → encode_sse, named `event: tool_call_end`
  - StageTimingEvent     → encode_sse, named `event: stage_timing`
  - ErrorEvent           → encode_sse, named `event: error`
  - FinalDoneEvent       → break loop, emit final OpenAI chunk + [DONE]
"""
import os
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from orchestrator.agentic import agentic_loop
from orchestrator.events import (
    ErrorEvent,
    FinalDoneEvent,
    StageTimingEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from orchestrator.providers.dispatcher import dispatch_for_brain
from orchestrator.sse import encode_openai_chunk, encode_openai_done, encode_sse
from orchestrator.tools import list_tools

router = APIRouter()


def _resolve_enabled_tools(*, web_search: bool, wiki: bool) -> list:
    """Return the subset of registered tools matching the request toggles."""
    if not (web_search or wiki):
        return []
    chosen = []
    for t in list_tools():
        if web_search and t.name.startswith("browser."):
            chosen.append(t)
        elif wiki and t.name.startswith("wiki."):
            chosen.append(t)
    return chosen


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    # Plan #7: tool toggles + brain selection live in server-side state now.
    # Body fields (web_search, wiki, provider, model) are accepted for backwards
    # compatibility but ignored — state is canonical.
    body.pop("web_search", None)
    body.pop("wiki", None)
    body.pop("provider", None)
    body.pop("model", None)

    state_store = request.app.state.state_store
    catalog = request.app.state.catalog
    state = state_store.get_state()

    # Brain selection from state
    brain = catalog.brain(state["brain"])
    api_key = (
        request.headers.get("X-Provider-Key")
        or request.headers.get("x-provider-key")
        or (os.environ.get(brain.requires_key, "") if brain.requires_key else "")
    )
    provider = dispatch_for_brain(
        brain,
        ollama_url=request.app.state.settings.ollama_url,
        request_timeout=request.app.state.settings.request_timeout,
        api_key=api_key or None,
    )

    # Personality system prompt at request time.
    #
    # The frontend (Plan #5 era) sends its own system message with TTS-friendly
    # speech rules and emotion-tag instructions. Both must be active, but the
    # catalog personality (identity, wiki-priming, tool-use behavior) needs
    # PRIMARY position — models give heaviest weight to the first system
    # message and the frontend prompt's "Your name is Ava" was drowning out
    # the catalog's "You are NodeAva, call wiki for project questions" when
    # ordered second.
    personality = catalog.personality(state["personality"])
    personality_msg = {"role": "system", "content": personality.system_prompt}
    messages = list(body.get("messages") or [])
    if messages and messages[0].get("role") == "system":
        # Caller supplied a system message — personality goes FIRST (primary
        # identity + tool behavior), caller's system follows (output format).
        messages = [personality_msg, messages[0]] + messages[1:]
    else:
        messages = [personality_msg] + messages

    stream = bool(body.get("stream", False))

    # Tool selection from state.tools
    enabled_tools = _resolve_enabled_tools(
        web_search=bool(state["tools"].get("web_search")),
        wiki=bool(state["tools"].get("wiki")),
    )

    async def event_source():
        if enabled_tools:
            async for event in agentic_loop(
                provider=provider,
                messages=list(messages),  # copy: agentic_loop mutates
                tools=enabled_tools,
            ):
                yield event
        else:
            async for event in provider.chat(messages, stream=stream):
                yield event

    if not stream:
        return await _non_streaming(event_source())
    return await _streaming(event_source())


async def _non_streaming(events) -> JSONResponse:
    parts: list[str] = []
    error: str | None = None
    async for event in events:
        if isinstance(event, TokenEvent):
            parts.append(event.delta)
        elif isinstance(event, (ThinkingTokenEvent, ToolCallStartEvent, ToolCallEndEvent, StageTimingEvent)):
            # Drop in non-streaming mode — no place to put them in OpenAI JSON.
            continue
        elif isinstance(event, ErrorEvent):
            error = event.message
        elif isinstance(event, FinalDoneEvent):
            break

    content = "".join(parts)
    finish_reason = "error" if error else "stop"
    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "nodeava-orch",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
    }
    if error:
        response["error"] = error
    return JSONResponse(response)


async def _streaming(events) -> StreamingResponse:
    async def gen():
        yield encode_openai_chunk(delta_content=None, role="assistant")

        async for event in events:
            if isinstance(event, TokenEvent):
                yield encode_openai_chunk(delta_content=event.delta)
            elif isinstance(
                event,
                (
                    ThinkingTokenEvent,
                    ToolCallStartEvent,
                    ToolCallEndEvent,
                    StageTimingEvent,
                    ErrorEvent,
                ),
            ):
                yield encode_sse(event)
            elif isinstance(event, FinalDoneEvent):
                break

        yield encode_openai_chunk(delta_content=None, finish_reason="stop")
        yield encode_openai_done()

    return StreamingResponse(gen(), media_type="text/event-stream")
