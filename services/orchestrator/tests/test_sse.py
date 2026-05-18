"""Tests for the SSE encoder."""
import json

from orchestrator.events import TokenEvent, ThinkingTokenEvent, FinalDoneEvent, ErrorEvent
from orchestrator.sse import encode_sse, encode_openai_chunk, encode_openai_done


def test_encode_sse_token_event():
    """Token events are emitted on the default SSE event stream
    so that OpenAI-compatible clients receive them as plain `data:` chunks."""
    out = encode_sse(TokenEvent(delta="Hi"))
    # The OpenAI client expects no `event:` prefix for content chunks.
    assert out.startswith("data: ")
    payload = json.loads(out.removeprefix("data: ").strip())
    assert payload == {"type": "token", "delta": "Hi"}
    assert out.endswith("\n\n")


def test_encode_sse_named_event():
    """Non-token events get a named SSE event line so the frontend can route them."""
    out = encode_sse(ErrorEvent(message="boom"))
    lines = out.splitlines()
    assert lines[0] == "event: error"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload == {"type": "error", "message": "boom"}
    assert out.endswith("\n\n")


def test_encode_sse_final_done():
    out = encode_sse(FinalDoneEvent())
    lines = out.splitlines()
    assert lines[0] == "event: final_done"


def test_encode_openai_chunk():
    """Emit a standard OpenAI streaming chunk (used to wrap TokenEvents
    for compatibility with the official openai SDK)."""
    out = encode_openai_chunk(delta_content="Hi", finish_reason=None)
    assert out.startswith("data: ")
    payload = json.loads(out.removeprefix("data: ").strip())
    assert payload["choices"][0]["delta"]["content"] == "Hi"
    assert payload["choices"][0]["finish_reason"] is None
    assert payload["object"] == "chat.completion.chunk"


def test_encode_openai_done():
    """The OpenAI streaming convention terminates the stream with `data: [DONE]`."""
    out = encode_openai_done()
    assert out == "data: [DONE]\n\n"


def test_encode_sse_thinking_token_event():
    """Thinking tokens MUST go on the named SSE channel — never on the
    default `data:` stream, so they can't contaminate user-visible content."""
    out = encode_sse(ThinkingTokenEvent(delta="reasoning..."))
    lines = out.splitlines()
    assert lines[0] == "event: thinking_token"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1].removeprefix("data: "))
    assert payload == {"type": "thinking_token", "delta": "reasoning..."}
    assert out.endswith("\n\n")
