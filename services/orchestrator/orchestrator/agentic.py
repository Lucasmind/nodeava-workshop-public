"""Agentic loop — the multi-round tool-execution wrapper.

The agentic loop is a single async generator that wraps `Provider.chat()`
in a multi-round conversation:

  Round 1: provider.chat(stream=False, tools=enabled)
    - If response includes tool_calls → execute them, append results, loop
    - Else → buffer TokenEvents, yield them, FinalDoneEvent, exit

  Round 2..N: same shape, with growing message history

  After MAX_TOOL_ROUNDS: append "stop calling tools" + one more call WITHOUT tools

Events emitted (to the SSE wire):
  - ThinkingTokenEvent     (pass-through, per round)
  - ToolCallStartEvent     (before each tool execution)
  - ToolCallEndEvent       (after each tool execution; `error` set if ToolError)
  - StageTimingEvent       (round_start, round_end per round)
  - TokenEvent             (buffered then replayed on the final-answer round)
  - FinalDoneEvent         (end of stream)
  - ErrorEvent             (provider error — short-circuits the loop)

Internal-only event (provider→agentic_loop):
  - ToolCallRequestEvent   (consumed; never forwarded)
"""
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import (
    ErrorEvent,
    Event,
    FinalDoneEvent,
    StageTimingEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
)
from orchestrator.providers.base import Provider
from orchestrator.tools import ToolError
from orchestrator.tools.base import Tool

log = logging.getLogger("orchestrator.agentic")

DEFAULT_MAX_ROUNDS = 8
RESULT_PREVIEW_CHARS = 500
TOOL_RESULT_TRUNCATE = 4000  # what we feed back to the model


async def agentic_loop(
    *,
    provider: Provider,
    messages: list[dict[str, Any]],
    tools: list[Tool],
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> AsyncIterator[Event]:
    """Run an agentic chat loop.

    Yields typed Events to the caller (route layer). Mutates `messages` —
    callers should pass a copy if they need to preserve the original.
    """
    tools_def: list[dict[str, Any]] | None = (
        [t.to_openai_function() for t in tools] if tools else None
    )
    tools_by_name: dict[str, Tool] = {t.name: t for t in tools}

    for round_num in range(1, max_rounds + 1):
        round_start = time.monotonic()
        yield StageTimingEvent(
            stage="round_start", duration_ms=0.0, round_num=round_num
        )

        tool_calls: list[dict[str, Any]] | None = None
        buffered_tokens: list[TokenEvent] = []
        error: ErrorEvent | None = None

        async for event in provider.chat(messages, stream=False, tools=tools_def):
            if isinstance(event, ToolCallRequestEvent):
                tool_calls = event.tool_calls
            elif isinstance(event, TokenEvent):
                buffered_tokens.append(event)
            elif isinstance(event, ThinkingTokenEvent):
                yield event  # pass-through
            elif isinstance(event, ErrorEvent):
                error = event
            elif isinstance(event, FinalDoneEvent):
                pass  # round terminator from the provider; loop handles outer FinalDoneEvent
            else:
                # Unknown event type from provider — log and drop.
                log.debug("agentic_loop: ignoring unexpected event %r", event)

        round_dur_ms = (time.monotonic() - round_start) * 1000.0
        yield StageTimingEvent(
            stage="round_end", duration_ms=round_dur_ms, round_num=round_num
        )

        if error is not None:
            yield error
            yield FinalDoneEvent()
            return

        if tool_calls is None:
            # Final answer in hand — replay buffered tokens
            for tok in buffered_tokens:
                yield tok
            yield FinalDoneEvent()
            return

        # Execute each tool call
        # Append the assistant's tool_calls message FIRST so the model history
        # is well-formed for the next round.
        messages.append(
            {"role": "assistant", "content": None, "tool_calls": tool_calls}
        )

        for tc in tool_calls:
            tc_id = tc.get("id") or ""
            fn = tc.get("function") or {}
            tc_name = fn.get("name") or ""
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}

            yield ToolCallStartEvent(id=tc_id, name=tc_name, arguments=args)

            t0 = time.monotonic()
            try:
                if tc_name not in tools_by_name:
                    # The user toggled this tool family off in the dashboard.
                    # Be explicit so the model stops retrying — otherwise we
                    # spin until max_rounds (8 rounds × ~3s = ~24s of "stuck")
                    # and the verbal filler fires repeatedly.
                    raise ToolError(
                        f"tool {tc_name!r} is unavailable (disabled by the "
                        "user's current settings). Do NOT try this tool again. "
                        "Produce your final answer to the user without it — "
                        "tell them the relevant toggle is off in the drawer."
                    )
                result = await tools_by_name[tc_name].execute(args)
                err_msg: str | None = None
            except ToolError as e:
                result = f"Error: {e}"
                err_msg = str(e)
            except Exception as e:
                log.warning("unexpected exception from tool %s: %s", tc_name, e)
                result = f"Error: {e}"
                err_msg = str(e)
            dur_ms = (time.monotonic() - t0) * 1000.0

            yield ToolCallEndEvent(
                id=tc_id,
                result_preview=result[:RESULT_PREVIEW_CHARS],
                duration_ms=dur_ms,
                error=err_msg,
            )

            # Truncate the result fed back to the model — keeps context manageable.
            truncated = result
            if len(result) > TOOL_RESULT_TRUNCATE:
                truncated = (
                    result[:TOOL_RESULT_TRUNCATE]
                    + f"\n\n[...truncated, original {len(result)} chars]"
                )
            messages.append(
                {"role": "tool", "tool_call_id": tc_id, "content": truncated}
            )

        # Continue to next round

    # Exhausted max_rounds — force a final answer with no tools
    log.warning("agentic_loop: hit max_rounds=%d, forcing final answer", max_rounds)
    messages.append(
        {
            "role": "user",
            "content": (
                "You have finished searching. Stop calling tools. Write your "
                "final answer now using the information you've gathered. "
                "Do not invoke any more tools."
            ),
        }
    )
    final_buffer: list[TokenEvent] = []
    async for event in provider.chat(messages, stream=False, tools=None):
        if isinstance(event, TokenEvent):
            final_buffer.append(event)
        elif isinstance(event, ThinkingTokenEvent):
            yield event
        elif isinstance(event, ErrorEvent):
            yield event
            yield FinalDoneEvent()
            return
    for tok in final_buffer:
        yield tok
    yield FinalDoneEvent()
