"""Typed event models emitted by Providers / the agentic loop / consumed
by the SSE encoder.

  Plan #1: TokenEvent, FinalDoneEvent, ErrorEvent
  Plan #2: ThinkingTokenEvent
  Plan #4: ToolCallRequestEvent (internal — provider→agentic_loop),
           ToolCallStartEvent, ToolCallEndEvent, StageTimingEvent
           (emitted by agentic_loop → SSE)
"""
from typing import Any, Literal, Union

from pydantic import BaseModel


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class ThinkingTokenEvent(BaseModel):
    """Reasoning content emitted by providers that expose it (e.g. Anthropic
    extended thinking). The frontend's brain-pane subscribes to these on
    a named SSE channel — they are NOT mixed into the user-visible content
    stream.
    """
    type: Literal["thinking_token"] = "thinking_token"
    delta: str


class ToolCallRequestEvent(BaseModel):
    """Internal — emitted by a Provider when the upstream model requested
    one or more tool calls in its response. The agentic loop consumes this,
    executes the tools, and feeds results back in. Never serialized to SSE.

    `tool_calls` is the model's `choices[0].message.tool_calls` payload
    (OpenAI tool-call shape): list of {id, type, function: {name, arguments}}.
    """
    type: Literal["tool_call_request"] = "tool_call_request"
    tool_calls: list[dict[str, Any]]


class ToolCallStartEvent(BaseModel):
    """Emitted by the agentic loop just before executing a tool. Surfaces to
    SSE on `event: tool_call_start` for the Tier A visualizer."""
    type: Literal["tool_call_start"] = "tool_call_start"
    id: str
    name: str
    arguments: dict[str, Any]


class ToolCallEndEvent(BaseModel):
    """Emitted by the agentic loop after a tool finishes. `error` is set
    when the tool raised `ToolError`. Surfaces to SSE on `event: tool_call_end`."""
    type: Literal["tool_call_end"] = "tool_call_end"
    id: str
    result_preview: str  # truncated for UI display
    duration_ms: float
    error: str | None = None


class StageTimingEvent(BaseModel):
    """Per-round / per-stage timing for the agentic loop. Surfaces to SSE on
    `event: stage_timing` for the Tier A pipeline-visualizer latency badges."""
    type: Literal["stage_timing"] = "stage_timing"
    stage: Literal["round_start", "round_end", "first_token", "final"]
    duration_ms: float
    round_num: int | None = None


class FinalDoneEvent(BaseModel):
    type: Literal["final_done"] = "final_done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


Event = Union[
    TokenEvent,
    ThinkingTokenEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
    ToolCallEndEvent,
    StageTimingEvent,
    FinalDoneEvent,
    ErrorEvent,
]
