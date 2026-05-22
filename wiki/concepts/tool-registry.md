# The Tool Registry

The tool registry is a runtime dictionary inside the [[orchestrator]] service that maps string names to callable `Tool` objects, giving the language model a controlled set of actions it can invoke during a conversation. When the agentic loop in the chat completions route receives a `tool_calls` response from the model, it looks up each requested tool by name in this registry, executes it, and feeds the result back into the conversation — repeating until the model produces a plain content response or the round limit of eight is reached.

## Structure

The registry lives in `services/orchestrator/orchestrator/tools/__init__.py` as a module-level dictionary `_registry: dict[str, Tool]`. Three functions form its public interface:

- `register(tool)` — adds or replaces a tool by its `name` attribute. Replacement on conflict is intentional: it supports test resets and runtime swaps that the agentic loop relies on.
- `get(name)` — returns the tool or raises `ToolError` if the name is absent.
- `list_tools()` — returns all registered tools in arbitrary order.

Every tool is a subclass of the abstract base class `orchestrator.tools.base.Tool`, defined in `services/orchestrator/orchestrator/tools/base.py`. Each subclass must declare two class attributes — `name` (a dotted string identifier such as `browser.search`) and `schema` (a JSON Schema object describing its arguments) — and implement an async `execute(args)` method that returns a string. The base class also provides `to_openai_function()`, which renders the tool as an OpenAI function definition for injection into chat completions requests.

## Built-in tools

Two families of tools ship with NodeAva and are registered at startup in `orchestrator.main._register_builtin_tools`.

The [[browser-tools]] family (`browser.search`, `browser.open`, `browser.find`) connects to the bundled SearXNG instance at `http://searxng:8080` and provides web search, page fetching with SSRF protection, and in-page text search.

The [[wiki-tools]] family (`wiki.list`, `wiki.search`, `wiki.open`) reads the on-disk wiki directory configured by the `WIKI_DIR` environment variable (default: `wiki`) and lets the model inspect NodeAva's own documentation.

## Error handling

Tools raise `ToolError` for user-fixable failures such as a missing wiki page or a rejected URL. The route layer catches `ToolError` and returns an HTTP 400 with the message in the body. Any other exception propagates and surfaces as a `tool_call_end` SSE event carrying an `error` field.

## Testing tools in isolation

Before the agentic loop was wired up in Plan 4, tools were callable directly via `POST /v1/tools/{name}` on the orchestrator at port `8082`. This endpoint remains available for development and debugging.

## Adding a custom tool

Subclass `Tool` with a unique `name`, a valid JSON Schema in `schema`, and an async `execute` method. Register the instance in `orchestrator.main._register_builtin_tools`. Add tests under `tests/test_tools_<name>.py`. The tool becomes available to the agentic loop immediately on the next startup.
