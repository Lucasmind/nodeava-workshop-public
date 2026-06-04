"""LMStudioProvider — chat client for LM Studio's NATIVE REST API.

LM Studio exposes two HTTP surfaces:
  - an OpenAI-compatible API at  <base>/v1/chat/completions
  - a NATIVE API at              <base>/api/v0/chat/completions

We deliberately target the native endpoint (Plan #11, at the user's request).
It speaks the SAME OpenAI-shaped wire format for streaming deltas and
`tool_calls` (both verified live against qwen3-4b-2507), so OllamaProvider's
parsing applies unchanged — we only override the path. The native endpoint
additionally returns `stats` (tokens_per_second, time_to_first_token),
`model_info`, and `runtime`; we don't surface those yet but they're available
on the non-streaming JSON for a future telemetry hook.

Error contract is inherited: HTTP/connection failures yield ErrorEvent +
FinalDoneEvent rather than raising out of the async generator.
"""
from orchestrator.providers.ollama import OllamaProvider


class LMStudioProvider(OllamaProvider):
    """OpenAI-shaped chat client pointed at LM Studio's native /api/v0 endpoint."""

    _CHAT_PATH = "/api/v0/chat/completions"
