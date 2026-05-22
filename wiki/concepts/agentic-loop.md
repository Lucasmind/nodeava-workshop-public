# The Agentic Loop

The agentic loop is the multi-round conversation wrapper inside NodeAva's [[orchestrator]] that allows the language model to call tools, receive results, and continue reasoning before producing a final answer. Instead of returning the model's first response directly to the user, the loop intercepts tool call requests, executes the named tools, appends the results to the message history, and re-prompts the model — repeating until the model responds with plain content or the round limit is reached.

## How it works

The loop is implemented as an async generator in `services/orchestrator/orchestrator/agentic.py`. Each iteration is called a round. At the start of every round, the orchestrator calls `Provider.chat()` with `stream=False` and the current tool definitions. The provider's response falls into one of two cases:

- The response contains `tool_calls`. The loop executes each tool, appends an assistant message with the tool call and a tool-role message with the result, then begins the next round.
- The response contains no tool calls. The loop replays any buffered `TokenEvent` objects and emits a `FinalDoneEvent`, ending the stream.

The default maximum is 8 rounds (`DEFAULT_MAX_ROUNDS = 8`). If the loop exhausts all rounds without a clean exit, it appends a user-role message instructing the model to stop calling tools and makes one final call with `tools=None`, forcing a prose answer.

Tool results fed back to the model are truncated at 4000 characters to keep the context window manageable. The full result (up to 500 characters) is included in the `ToolCallEndEvent` sent to the frontend for display purposes.

## Events emitted

The loop emits a sequence of typed events onto the SSE wire that the frontend's visualizer panels consume:

- `StageTimingEvent` at the start and end of each round, carrying the round number and elapsed milliseconds.
- `ToolCallStartEvent` before each tool executes, with the tool name and parsed arguments.
- `ToolCallEndEvent` after each tool returns, with a result preview, duration, and any error message.
- `ThinkingTokenEvent` passed through from the provider as they arrive.
- `TokenEvent` objects buffered during tool-call rounds and replayed only on the final answer round.
- `FinalDoneEvent` once the loop exits cleanly.
- `ErrorEvent` if the provider signals a failure, which short-circuits the loop immediately.

`ToolCallRequestEvent` is an internal event consumed by the loop and never forwarded to the client.

## Tools available

The loop operates on whatever tools are injected at request time. Sending `"wiki": true` in the request body injects the `wiki.list`, `wiki.search`, and `wiki.open` tools, which read from the on-disk wiki directory (default path: `wiki/`). Sending `"web_search": true` injects `browser.search`, `browser.open`, and `browser.find`, which are backed by the bundled SearXNG instance. Both sets can be active simultaneously. If neither toggle is set, no tools are injected and the agentic loop is bypassed entirely, falling back to single-round behavior.

## Where it fits in the pipeline

The agentic loop sits between the chat route (`services/orchestrator/orchestrator/routes/chat.py`) and the provider abstraction. The route receives an HTTP request, selects a [[provider]] via `pick_provider`, and passes control to `agentic_loop()` if tools are enabled. The orchestrator listens on port `8082` by default. The [[llama-server]] backend runs on port `8081` and is addressed via the `LLAMA_URL` environment variable.

Tool failures raise `ToolError` for expected conditions such as unknown tool names or page-not-found responses. Unexpected exceptions are caught, logged, and surfaced as error strings in the tool result rather than crashing the loop.
