# How do I make the avatar search the web?

Web search is an opt-in agentic feature controlled by a checkbox in the control panel. When enabled, the [[orchestrator]] injects `browser.*` tools into the chat-completion request and runs an agentic loop that can search, fetch pages, and synthesize an answer before the avatar speaks.

To enable it:

1. Open the NodeAva control panel in the browser.
2. Check the "Web search" checkbox. This sets `nodeava.toggle.web_search` in `localStorage` and adds `"web_search": true` to every subsequent chat request sent to the orchestrator at `http://localhost:8082`.
3. Ask the avatar a question that requires current or external information. The orchestrator will call `browser.search` against the bundled SearXNG instance, optionally follow up with `browser.open` or `browser.find`, and return a synthesized answer.

While tools are executing, the avatar's state machine enters `TOOL_CALLING` and filler speech ("Let me look that up.") plays after 800 milliseconds. The toggle can be combined with the wiki checkbox to give the model access to both `browser.*` and `wiki.*` tools simultaneously.

Web search requires the SearXNG container to be running. If search returns no results, confirm the orchestrator's `SEARXNG_URL` environment variable points to the correct address (default: `http://searxng:8080` inside Docker).

See also: [[wiki-tools]], [[orchestrator]], [[state-machine]], [[text-to-speech]].
