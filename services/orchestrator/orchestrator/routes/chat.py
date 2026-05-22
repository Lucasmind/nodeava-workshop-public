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
from orchestrator.catalog import CatalogError
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
    settings = request.app.state.settings
    state = state_store.get_state()

    # Brain selection from state. Fall back to the catalog default if the
    # persisted brain id is gone (e.g. a dynamic LM Studio brain selected
    # before a restart, before the next /v1/catalog refresh re-adds it).
    try:
        brain = catalog.brain(state["brain"])
    except CatalogError:
        brain = catalog.default_brain()
        state_store.set_state("brain", brain.id)

    # Plan #11: the LM Studio "auto" brain resolves to a concrete model id at
    # request time — the currently-loaded model, else the configured fallback
    # (which LM Studio JIT-loads on first use).
    model_override = None
    if brain.kind == "lmstudio" and brain.model in ("auto", ""):
        lmstudio = getattr(request.app.state, "lmstudio", None)
        if lmstudio is not None:
            model_override = await lmstudio.pick_model(
                fallback=settings.lmstudio_default_model
            )
        else:
            model_override = settings.lmstudio_default_model

    api_key = (
        request.headers.get("X-Provider-Key")
        or request.headers.get("x-provider-key")
        or (os.environ.get(brain.requires_key, "") if brain.requires_key else "")
    )
    provider = dispatch_for_brain(
        brain,
        ollama_url=settings.ollama_url,
        lmstudio_url=settings.lmstudio_url,
        request_timeout=settings.request_timeout,
        api_key=api_key or None,
        model_override=model_override,
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
    # Tool selection from state.tools (resolved early so we can inject availability
    # into the personality system prompt — see the runtime preamble below).
    web_search_on = bool(state["tools"].get("web_search"))
    wiki_on = bool(state["tools"].get("wiki"))
    enabled_tools = _resolve_enabled_tools(web_search=web_search_on, wiki=wiki_on)

    personality = catalog.personality(state["personality"])

    # Runtime tool-availability preamble. Without this, a personality prompt
    # that says "for current events, call browser.search" would have the model
    # emit browser.search even when web_search is toggled OFF, hitting the
    # unknown-tool error loop until max_rounds. The preamble tells the model
    # which tool families are currently usable so it adapts its behavior.
    availability_lines = []
    if wiki_on:
        availability_lines.append(
            "- wiki.* tools are ENABLED. Use them for NodeAva project questions."
        )
    else:
        availability_lines.append(
            "- wiki.* tools are DISABLED. Do not attempt wiki.search / wiki.open / "
            "wiki.list. For NodeAva questions, answer from memory and add "
            '"(wiki lookup is disabled)" to the reply.'
        )
    if web_search_on:
        availability_lines.append(
            "- browser.* tools are ENABLED. Use them for current-event and "
            "general-web questions per the trigger map above."
        )
    else:
        availability_lines.append(
            "- browser.* tools are DISABLED. Do not attempt browser.search. "
            "For current-event or web-search questions, briefly tell the user "
            '"web search is currently turned off — enable it in the drawer to '
            'get a real answer", then answer from your training data if useful. '
            "Do NOT keep trying browser.* — the tool is unavailable."
        )
    availability_block = (
        "\n\nRUNTIME TOOL AVAILABILITY (this overrides the trigger map above):\n"
        + "\n".join(availability_lines)
    )

    personality_msg = {
        "role": "system",
        "content": personality.system_prompt + availability_block,
    }
    messages = list(body.get("messages") or [])
    if messages and messages[0].get("role") == "system":
        # Caller supplied a system message — personality goes FIRST (primary
        # identity + tool behavior), caller's system follows (output format).
        messages = [personality_msg, messages[0]] + messages[1:]
    else:
        messages = [personality_msg] + messages

    stream = bool(body.get("stream", False))

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
