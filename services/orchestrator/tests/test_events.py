"""Tests for the typed Event models."""
from orchestrator.events import Event, TokenEvent, FinalDoneEvent, ErrorEvent, ThinkingTokenEvent


def test_token_event_serialization():
    e = TokenEvent(delta="Hello")
    d = e.model_dump()
    assert d == {"type": "token", "delta": "Hello"}


def test_final_done_event_serialization():
    e = FinalDoneEvent()
    d = e.model_dump()
    assert d == {"type": "final_done"}


def test_error_event_serialization():
    e = ErrorEvent(message="backend unreachable")
    d = e.model_dump()
    assert d == {"type": "error", "message": "backend unreachable"}


def test_event_is_abstract_base_via_discriminator():
    """All concrete events should be assignable to the Event union type."""
    events: list[Event] = [
        TokenEvent(delta="x"),
        FinalDoneEvent(),
        ErrorEvent(message="boom"),
    ]
    types = [e.type for e in events]
    assert types == ["token", "final_done", "error"]


def test_thinking_token_event_serialization():
    e = ThinkingTokenEvent(delta="hmm let me think")
    assert e.model_dump() == {"type": "thinking_token", "delta": "hmm let me think"}


def test_thinking_token_event_in_union():
    """ThinkingTokenEvent is part of the Event union."""
    events: list[Event] = [
        TokenEvent(delta="visible"),
        ThinkingTokenEvent(delta="hidden"),
        FinalDoneEvent(),
    ]
    types = [e.type for e in events]
    assert types == ["token", "thinking_token", "final_done"]


from orchestrator.events import (
    ToolCallEndEvent,
    ToolCallRequestEvent,
    ToolCallStartEvent,
    StageTimingEvent,
)


def test_tool_call_request_event():
    """Internal event — provider emits this when the model wants tools."""
    e = ToolCallRequestEvent(
        tool_calls=[
            {"id": "call_1", "type": "function",
             "function": {"name": "browser.search", "arguments": '{"query":"x"}'}}
        ]
    )
    d = e.model_dump()
    assert d["type"] == "tool_call_request"
    assert d["tool_calls"][0]["id"] == "call_1"


def test_tool_call_start_event():
    e = ToolCallStartEvent(
        id="call_1",
        name="browser.search",
        arguments={"query": "kernel"},
    )
    d = e.model_dump()
    assert d == {
        "type": "tool_call_start",
        "id": "call_1",
        "name": "browser.search",
        "arguments": {"query": "kernel"},
    }


def test_tool_call_end_event_success():
    e = ToolCallEndEvent(
        id="call_1",
        result_preview="3 results",
        duration_ms=124.5,
        error=None,
    )
    d = e.model_dump()
    assert d == {
        "type": "tool_call_end",
        "id": "call_1",
        "result_preview": "3 results",
        "duration_ms": 124.5,
        "error": None,
    }


def test_tool_call_end_event_with_error():
    e = ToolCallEndEvent(
        id="call_1",
        result_preview="",
        duration_ms=5.0,
        error="HTTP 403 fetching example.com",
    )
    assert e.error == "HTTP 403 fetching example.com"


def test_stage_timing_event():
    e = StageTimingEvent(
        stage="round_end",
        duration_ms=2400.0,
        round_num=1,
    )
    d = e.model_dump()
    assert d["type"] == "stage_timing"
    assert d["stage"] == "round_end"
    assert d["round_num"] == 1


def test_all_new_events_are_in_union():
    events: list[Event] = [
        ToolCallRequestEvent(tool_calls=[]),
        ToolCallStartEvent(id="x", name="t", arguments={}),
        ToolCallEndEvent(id="x", result_preview="", duration_ms=1.0),
        StageTimingEvent(stage="round_start", duration_ms=0.0, round_num=1),
    ]
    types = [e.type for e in events]
    assert types == [
        "tool_call_request", "tool_call_start", "tool_call_end", "stage_timing"
    ]
