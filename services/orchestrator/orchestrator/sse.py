"""Server-Sent Events encoding helpers.

We emit two flavors of SSE message:

1. **OpenAI-compatible chunks** (`encode_openai_chunk`, `encode_openai_done`) —
   so any OpenAI-SDK or fetch-based client can consume `/v1/chat/completions`
   without modification.

2. **NodeAva named events** (`encode_sse`) — typed Events serialized on
   named SSE event lines (`event: tool_call_start`, etc.) consumed by the
   Tier A visualizer panels via `EventSource.addEventListener('name', ...)`.

The two flavors share a single SSE stream. The OpenAI client is unaffected
by the extra named events because the EventSource default listener only
receives messages without an `event:` line.

Token content is emitted as BOTH a NodeAva TokenEvent (on the default
stream — which renders as a plain `data:` chunk and looks like an OpenAI
chunk) AND, in Plan #1, additionally wrapped in `encode_openai_chunk`
to match the exact OpenAI shape. Callers choose which to use.
"""
import json
import time
import uuid

from orchestrator.events import Event, TokenEvent


def encode_sse(event: Event) -> str:
    """Encode an Event as an SSE message.

    TokenEvent goes on the default stream (no `event:` line) so OpenAI
    clients can parse it as a chunk. All other events get a named
    `event:` line so the frontend's EventSource can route them.
    """
    payload = json.dumps(event.model_dump())
    if isinstance(event, TokenEvent):
        return f"data: {payload}\n\n"
    return f"event: {event.type}\ndata: {payload}\n\n"


def encode_openai_chunk(
    delta_content: str | None,
    *,
    finish_reason: str | None = None,
    role: str | None = None,
    model: str = "nodeava-orch",
) -> str:
    """Emit a single OpenAI-style streaming chunk."""
    delta: dict[str, object] = {}
    if role is not None:
        delta["role"] = role
    if delta_content is not None:
        delta["content"] = delta_content

    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


def encode_openai_done() -> str:
    """Emit the OpenAI streaming sentinel that closes a stream."""
    return "data: [DONE]\n\n"
