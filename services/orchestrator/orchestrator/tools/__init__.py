"""Tool abstraction — pluggable functions the agent can call.

Plan #3 introduces:
  - Tool ABC + registry (this package)
  - Browser tools (browser.py)
  - Wiki tools (wiki.py)

Plan #4 will consume the registry from the agentic loop in the chat
completions route. Until then, tools are callable in isolation via
the test endpoint at POST /v1/tools/{name}.
"""
from orchestrator.tools.base import Tool, ToolError

__all__ = ["Tool", "ToolError", "register", "get", "list_tools"]


_registry: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Register a tool, replacing any previous tool of the same name.

    Replacement-on-conflict is intentional — it supports test reset and
    swap-at-runtime patterns that Plan #4's agentic loop relies on.
    """
    if not tool.name:
        raise ToolError("Tool.name must be non-empty")
    _registry[tool.name] = tool


def get(name: str) -> Tool:
    """Return the tool registered under `name`, or raise ToolError if absent."""
    if name not in _registry:
        raise ToolError(f"unknown tool: {name!r}")
    return _registry[name]


def list_tools() -> list[Tool]:
    """Return all registered tools in arbitrary order. Callers sort if needed."""
    return list(_registry.values())


def _clear_registry_for_tests() -> None:
    """Test helper — never call from production code."""
    _registry.clear()
