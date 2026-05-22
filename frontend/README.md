## Tool toggles (Plan #5)

Two checkboxes in the control panel opt into agentic features served by
the orchestrator (Plan #4):

- **🔍 Web search** — when enabled, the orchestrator's chat route runs an
  agentic loop with `browser.*` tools. The avatar may search the web, fetch
  pages, and synthesize an answer. Tool execution surfaces via:
  - State machine: `TOOL_CALLING` (or `WIKI_QUERY` for wiki tools)
  - Filler speech: "Let me look that up." after 800ms of tool execution
  - SSE events (consumed by `LLMClient.js`): `tool_call_start`, `tool_call_end`, `stage_timing`, `thinking_token`

- **📚 Wiki** — same shape, but injects `wiki.*` tools (read-only access to
  the on-disk wiki at `wiki/` in the repo). Useful for asking about NodeAva
  itself once Plan #6 fills in self-knowledge content.

Both toggles persist to `localStorage` (`nodeava.toggle.web_search`,
`nodeava.toggle.wiki`). Plan #8 will replace these with a proper command
center; Plan #5 keeps the UI minimal.

## State machine (Plan #5)

The full state list (`frontend/src/app/state.js`):

| State | When |
|---|---|
| `IDLE` | nothing happening |
| `LISTENING` | mic active, capturing audio |
| `TRANSCRIBING` | audio → text via STT |
| `THINKING` | LLM is computing |
| `TOOL_CALLING` | agentic loop executing a browser.* tool |
| `WIKI_QUERY` | agentic loop executing a wiki.* tool |
| `SPEAKING` | TTS audio playing through avatar lip-sync |

Transitions:

```
IDLE → LISTENING → TRANSCRIBING → THINKING
THINKING ↔ TOOL_CALLING ↔ WIKI_QUERY    (back-and-forth during a tool round)
THINKING → SPEAKING → IDLE
```
