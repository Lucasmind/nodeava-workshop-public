"""Provider abstract base class.

A Provider is a chat backend (local llama-server, Anthropic, OpenAI, ...).
Implementations are async generators that yield typed Events.

  Plan #1: TokenEvent, FinalDoneEvent, ErrorEvent
  Plan #2: ThinkingTokenEvent (Anthropic extended thinking surface)
  Plan #4: tools=[...] parameter + ToolCallRequestEvent when model emits tool_calls
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from orchestrator.events import Event


class Provider(ABC):
    """Abstract chat provider — yields a stream of typed Events."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Event]:
        """Run a chat completion. Returns an async iterator of Events.

        Parameters
        ----------
        messages
            OpenAI-format message list.
        stream
            If True, emit TokenEvents as tokens arrive. If False, the provider
            may still emit a single TokenEvent containing the full response
            followed by FinalDoneEvent — callers should buffer either way.
        tools
            OpenAI tool-function definitions to inject into the request. When
            non-empty and the model emits a `tool_calls` array in its response,
            the provider yields a `ToolCallRequestEvent` before any
            FinalDoneEvent. The agentic loop catches this, executes the tools,
            and re-invokes chat() with the tool results appended to messages.
        """
        ...
