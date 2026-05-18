"""Tests for the agentic loop — the multi-round tool-execution wrapper."""
from typing import Any

import pytest

from orchestrator.agentic import agentic_loop
from orchestrator.events import (
    ErrorEvent,
    FinalDoneEvent,
    StageTimingEvent,
    ThinkingTokenEvent,
    TokenEvent,
    ToolCallEndEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
)
from orchestrator.providers.base import Provider
from orchestrator.tools.base import Tool, ToolError


class _ScriptedProvider(Provider):
    """A provider that yields a pre-canned event sequence per chat() invocation.

    Each call dequeues the next sequence from `self._sequences`. Used to
    simulate multi-round agentic conversations without a real LLM."""

    def __init__(self, sequences: list[list]) -> None:
        self._sequences = list(sequences)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages, *, stream=False, tools=None):
        self.calls.append(
            {"messages": list(messages), "stream": stream, "tools": tools}
        )
        if not self._sequences:
            raise AssertionError(
                "_ScriptedProvider exhausted: agentic_loop called chat() more times than expected"
            )
        sequence = self._sequences.pop(0)
        for event in sequence:
            yield event


class _Echo(Tool):
    name = "test.echo"
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, args):
        return f"echo: {args.get('text', '')}"


class _Boom(Tool):
    name = "test.boom"
    schema = {"type": "object"}

    async def execute(self, args):
        raise ToolError("kaboom")


async def test_no_tool_calls_yields_buffered_tokens_then_done():
    """Single-round case: model returns content, no tool calls.
    The loop yields the buffered TokenEvents and a FinalDoneEvent."""
    provider = _ScriptedProvider(
        sequences=[
            [TokenEvent(delta="Hello"), TokenEvent(delta=" world"), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "hi"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]
    token_deltas = [e.delta for e in events if isinstance(e, TokenEvent)]
    assert token_deltas == ["Hello", " world"]
    assert isinstance(events[-1], FinalDoneEvent)
    # provider was called exactly once
    assert len(provider.calls) == 1


async def test_one_tool_call_then_final_answer():
    """Round 1: model emits tool_call. Round 2: model returns content using the result."""
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "test.echo", "arguments": '{"text":"foo"}'},
    }
    provider = _ScriptedProvider(
        sequences=[
            # Round 1 — model wants to call echo
            [ToolCallRequestEvent(tool_calls=[tool_call]), FinalDoneEvent()],
            # Round 2 — model returns its synthesis
            [TokenEvent(delta="The echo said: echo: foo"), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "echo foo"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]

    starts = [e for e in events if isinstance(e, ToolCallStartEvent)]
    ends = [e for e in events if isinstance(e, ToolCallEndEvent)]
    tokens = [e for e in events if isinstance(e, TokenEvent)]
    dones = [e for e in events if isinstance(e, FinalDoneEvent)]

    assert len(starts) == 1
    assert starts[0].id == "call_1"
    assert starts[0].name == "test.echo"
    assert starts[0].arguments == {"text": "foo"}

    assert len(ends) == 1
    assert ends[0].id == "call_1"
    assert ends[0].error is None
    assert ends[0].duration_ms >= 0

    assert [t.delta for t in tokens] == ["The echo said: echo: foo"]
    assert len(dones) == 1

    # provider called twice: round 1 + round 2
    assert len(provider.calls) == 2
    # round-2 messages include the tool result
    msgs_round2 = provider.calls[1]["messages"]
    tool_msg = next((m for m in msgs_round2 if m.get("role") == "tool"), None)
    assert tool_msg is not None
    assert tool_msg["tool_call_id"] == "call_1"
    assert tool_msg["content"] == "echo: foo"


async def test_tool_error_is_captured_in_tool_call_end():
    """When a tool raises ToolError, the agentic loop emits ToolCallEndEvent
    with `error` set, and the loop continues — the model gets the error
    as the tool result and can recover."""
    tool_call = {
        "id": "call_2",
        "type": "function",
        "function": {"name": "test.boom", "arguments": "{}"},
    }
    provider = _ScriptedProvider(
        sequences=[
            [ToolCallRequestEvent(tool_calls=[tool_call]), FinalDoneEvent()],
            [TokenEvent(delta="Recovered."), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "fail safely"}],
            tools=[_Boom()],
            max_rounds=3,
        )
    ]
    end_events = [e for e in events if isinstance(e, ToolCallEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].error == "kaboom"
    assert "kaboom" in end_events[0].result_preview.lower()


async def test_unknown_tool_is_captured_in_tool_call_end():
    """If the model invents a tool name that isn't registered, the loop emits a
    ToolCallEndEvent with an error — does NOT raise out."""
    tool_call = {
        "id": "call_3",
        "type": "function",
        "function": {"name": "no.such.tool", "arguments": "{}"},
    }
    provider = _ScriptedProvider(
        sequences=[
            [ToolCallRequestEvent(tool_calls=[tool_call]), FinalDoneEvent()],
            [TokenEvent(delta="Sorry, I made up a tool."), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[],
            max_rounds=3,
        )
    ]
    end_events = [e for e in events if isinstance(e, ToolCallEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].error is not None
    assert "no.such.tool" in end_events[0].error


async def test_max_rounds_forces_final_answer():
    """If the model keeps asking for tools past max_rounds, the loop appends
    a 'stop calling tools' message and makes one more call with tools=None."""
    repeated_tool_call = {
        "id": "call_x",
        "type": "function",
        "function": {"name": "test.echo", "arguments": "{}"},
    }
    # 2 rounds of tool calls + a final forced-answer round
    provider = _ScriptedProvider(
        sequences=[
            [ToolCallRequestEvent(tool_calls=[repeated_tool_call]), FinalDoneEvent()],
            [ToolCallRequestEvent(tool_calls=[repeated_tool_call]), FinalDoneEvent()],
            [TokenEvent(delta="Final answer."), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "loop forever"}],
            tools=[_Echo()],
            max_rounds=2,
        )
    ]
    # Three provider calls: rounds 1 + 2 + the forced-final
    assert len(provider.calls) == 3
    # Last call must NOT include tools (forced final)
    assert provider.calls[-1]["tools"] is None
    # Last call's messages include the "stop calling tools" instruction
    last_msgs = provider.calls[-1]["messages"]
    user_msgs = [m["content"] for m in last_msgs if m.get("role") == "user"]
    assert any("stop calling tools" in (m or "").lower() for m in user_msgs)
    # Final answer made it through
    assert any(
        isinstance(e, TokenEvent) and "Final answer" in e.delta for e in events
    )


async def test_thinking_tokens_pass_through_each_round():
    """ThinkingTokenEvents emitted during a round are forwarded immediately
    (not buffered) — the brain pane should reflect reasoning in real time."""
    tool_call = {
        "id": "call_t",
        "type": "function",
        "function": {"name": "test.echo", "arguments": "{}"},
    }
    provider = _ScriptedProvider(
        sequences=[
            [
                ThinkingTokenEvent(delta="planning..."),
                ToolCallRequestEvent(tool_calls=[tool_call]),
                FinalDoneEvent(),
            ],
            [
                ThinkingTokenEvent(delta="synthesizing..."),
                TokenEvent(delta="done"),
                FinalDoneEvent(),
            ],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]
    thinking = [e.delta for e in events if isinstance(e, ThinkingTokenEvent)]
    assert thinking == ["planning...", "synthesizing..."]


async def test_error_event_short_circuits_loop():
    """If a provider yields an ErrorEvent, the loop forwards it and ends —
    no more provider calls, no more tool execution."""
    provider = _ScriptedProvider(
        sequences=[
            [ErrorEvent(message="backend down"), FinalDoneEvent()],
        ]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[],
            max_rounds=3,
        )
    ]
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert errors[0].message == "backend down"
    assert isinstance(events[-1], FinalDoneEvent)
    assert len(provider.calls) == 1


async def test_stage_timing_events_emitted_per_round():
    """Each round emits round_start + round_end timing events for the visualizer."""
    provider = _ScriptedProvider(
        sequences=[[TokenEvent(delta="hi"), FinalDoneEvent()]]
    )
    events = [
        e
        async for e in agentic_loop(
            provider=provider,
            messages=[{"role": "user", "content": "x"}],
            tools=[_Echo()],
            max_rounds=3,
        )
    ]
    timings = [e for e in events if isinstance(e, StageTimingEvent)]
    stages = sorted({t.stage for t in timings})
    assert "round_start" in stages
    assert "round_end" in stages
    # All timings have a round number on intermediate stages
    round_starts = [t for t in timings if t.stage == "round_start"]
    assert all(t.round_num == 1 for t in round_starts)
