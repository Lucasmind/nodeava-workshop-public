"""Tests for the Provider abstract base class."""
import pytest

from orchestrator.events import TokenEvent, FinalDoneEvent
from orchestrator.providers.base import Provider


class StubProvider(Provider):
    """Yields a fixed event sequence — used to test the ABC contract."""

    async def chat(self, messages, *, stream=False, tools=None):
        # Echo whether tools were passed so we can assert.
        marker = f"tools={'yes' if tools else 'no'}"
        yield TokenEvent(delta=marker)
        yield FinalDoneEvent()


async def test_provider_is_async_iterable():
    """A Provider's `chat` method returns an async iterator of Events."""
    provider = StubProvider()
    events = [e async for e in provider.chat([{"role": "user", "content": "hi"}])]
    assert [e.type for e in events] == ["token", "final_done"]


async def test_provider_subclass_must_implement_chat():
    """Instantiating a Provider that didn't override chat raises TypeError."""

    class BadProvider(Provider):
        pass

    with pytest.raises(TypeError):
        BadProvider()  # type: ignore[abstract]


async def test_provider_chat_accepts_tools_kwarg():
    """The new `tools` parameter is optional and defaults to None.
    Subclasses receive it via the chat signature."""
    provider = StubProvider()
    events_no_tools = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hi"}]
        )
    ]
    events_with_tools = [
        e async for e in provider.chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "x", "parameters": {}}}],
        )
    ]
    assert events_no_tools[0].delta == "tools=no"
    assert events_with_tools[0].delta == "tools=yes"
