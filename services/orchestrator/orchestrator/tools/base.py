"""Tool abstract base class.

A Tool has:
  - `name` (class attr): the dotted identifier the agent / route uses (e.g. "browser.search")
  - `schema` (class attr): JSON-Schema object describing the args
  - `execute(args)`: async method that does the work and returns a string

Tools should raise `ToolError` on user-fixable failures (bad URL, missing
file, etc.) — the route layer catches these and returns a 400 with the
message. Anything else propagates as a 500.
"""
from abc import ABC, abstractmethod
from typing import Any, ClassVar


class ToolError(Exception):
    """Raised when a tool fails due to bad input or expected runtime conditions
    (e.g. site returned 403, wiki page not found). The route layer translates
    this into a 400 response with the error message in the body."""


class Tool(ABC):
    """Abstract pluggable tool."""

    # Each subclass MUST override both of these as class attributes.
    name: ClassVar[str] = ""
    schema: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    async def execute(self, args: dict[str, Any]) -> str:
        """Run the tool and return a string result."""
        ...

    def to_openai_function(self) -> dict[str, Any]:
        """Render this tool as an OpenAI-tools function definition.

        Plan #4 will use this to inject the tools into chat completions
        requests. Plan #3 doesn't call this — but having it ready keeps
        the contract explicit.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (self.__class__.__doc__ or "").strip().split("\n")[0],
                "parameters": self.schema,
            },
        }
