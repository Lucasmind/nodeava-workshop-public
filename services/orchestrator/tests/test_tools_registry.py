"""Tests for the Tool ABC and the registry."""
import pytest

from orchestrator.tools.base import Tool, ToolError


class _Echo(Tool):
    name = "test.echo"
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, args: dict) -> str:
        return f"echo: {args.get('text', '')}"


async def test_tool_subclass_concrete_executes():
    """A concrete subclass with name+schema+execute can be instantiated and run."""
    t = _Echo()
    out = await t.execute({"text": "hello"})
    assert out == "echo: hello"
    assert t.name == "test.echo"
    assert t.schema["properties"]["text"]["type"] == "string"


def test_tool_subclass_without_execute_raises():
    """ABC enforces execute() — concrete class missing it can't instantiate."""

    class _Bad(Tool):
        name = "test.bad"
        schema = {}

    with pytest.raises(TypeError):
        _Bad()  # type: ignore[abstract]


def test_tool_error_is_an_exception():
    """ToolError is an Exception that tools raise on user-fixable failures."""
    e = ToolError("bad input")
    assert isinstance(e, Exception)
    assert str(e) == "bad input"


def test_to_openai_function_shape():
    """to_openai_function() renders the OpenAI tools format Plan #4 uses
    to inject tools into chat completions requests."""

    class _Docced(Tool):
        """Search the web for cats."""

        name = "test.docced"
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}

        async def execute(self, args):
            return "ok"

    spec = _Docced().to_openai_function()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "test.docced"
    assert spec["function"]["description"] == "Search the web for cats."
    assert spec["function"]["parameters"]["properties"]["q"]["type"] == "string"


from orchestrator.tools import register, get, list_tools, _clear_registry_for_tests


@pytest.fixture(autouse=True)
def _reset_registry():
    """Each test runs against a fresh registry."""
    _clear_registry_for_tests()
    yield
    _clear_registry_for_tests()


def test_register_and_get():
    tool = _Echo()
    register(tool)
    assert get("test.echo") is tool


def test_get_unknown_raises_tool_error():
    with pytest.raises(ToolError) as exc:
        get("does.not.exist")
    assert "does.not.exist" in str(exc.value)


def test_list_tools_returns_all_registered():
    register(_Echo())

    class _Other(Tool):
        name = "test.other"
        schema = {"type": "object"}

        async def execute(self, args):
            return "ok"

    register(_Other())
    names = sorted(t.name for t in list_tools())
    assert names == ["test.echo", "test.other"]


def test_register_duplicate_replaces():
    """Registering the same name twice replaces — useful for tests/hot-reload."""
    register(_Echo())
    second = _Echo()
    register(second)
    assert get("test.echo") is second
