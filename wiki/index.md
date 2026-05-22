# Wiki Index

This index is the agent's first stop when answering questions about NodeAva. It lists every page currently in the wiki so the agent can identify which file to open for a given topic. Pages are grouped by type: concepts explain how NodeAva works, entities describe specific models and libraries, and FAQs give direct procedural answers. When a user question matches a topic here, open the relevant page before responding.

## Concepts

- [What is NodeAva?](concepts/nodeava-overview.md) — NodeAva is a self-contained digital avatar that runs entirely on a single machine, combining speech recognition, language model reasoning, voice synthesis, and 3D animation.
- [The NodeAva Pipeline](concepts/pipeline-architecture.md) — The end-to-end chain of services that converts a user's spoken words into an animated avatar response, running entirely on the user's local hardware.
- [The Agentic Loop](concepts/agentic-loop.md) — The multi-round conversation wrapper inside the orchestrator that allows the language model to call tools, receive results, and continue reasoning before replying.
- [The 3D Avatar](concepts/avatar-rendering.md) — A real-time animated head rendered in the browser using Three.js and the TalkingHead library, with lip sync and facial expression driven by audio output.
- [The Language Model](concepts/language-model.md) — The component responsible for generating NodeAva's responses, receiving conversation history and streaming text back through the pipeline.
- [Speech-to-Text (STT)](concepts/speech-to-text.md) — The pipeline stage that converts the user's spoken audio into a text string passed to the language model.
- [Text-to-Speech (TTS)](concepts/text-to-speech.md) — The stage that converts the language model's text output into audio the avatar can speak, using Kokoro-82M.
- [The Tool Registry](concepts/tool-registry.md) — A runtime dictionary inside the orchestrator that maps string names to callable Tool objects, giving the language model a controlled set of actions.
- [How NodeAva Searches the Web](concepts/web-search.md) — A three-tool browser pipeline backed by a bundled SearXNG meta-search engine, running locally inside the Docker network.
- [The Wiki System](concepts/wiki-system.md) — A directory of plain Markdown files on disk that serves as the system's self-knowledge base, readable by both the agent and human attendees.

## Entities

- [Kokoro-82M (TTS Engine)](entities/kokoro-tts.md) — A lightweight, open-weight text-to-speech model with 82 million parameters that synthesizes all of NodeAva's spoken audio output.
- [Qwen3-4B (Default LLM)](entities/qwen3-4b.md) — A 4-billion-parameter instruction-tuned language model by Alibaba's Qwen team, serving as NodeAva's default conversational brain via Ollama.
- [SearXNG (Search Engine)](entities/searxng.md) — An open-source meta-search engine that aggregates results from multiple upstream providers without tracking users or logging queries.
- [TalkingHead (Avatar Engine)](entities/talkinghead.md) — An open-source JavaScript library by Met4Citizen that renders a real-time 3D talking avatar in the browser using Three.js, handling lip sync and facial animation.
- [Whisper base.en (STT Model)](entities/whisper-base-en.md) — OpenAI's English-only speech recognition model at the base parameter scale, serving as NodeAva's speech-to-text engine.

## FAQs

- [How do I add my own knowledge to the wiki?](faqs/add-to-wiki.md) — Adding a new topic means registering it in the manifest file and re-running the compiler.
- [How do I change the avatar's voice?](faqs/change-voice.md) — Voice is controlled by a dropdown in the Control Panel UI and takes effect at runtime with no restart required.
- [How do I make the avatar search the web?](faqs/enable-web-search.md) — Web search is an opt-in feature enabled by a checkbox in the control panel, which injects browser tools into the agentic loop.
- [How do I swap the LLM model?](faqs/swap-model.md) — The orchestrator at port 8082 accepts a model field per request, so the model can be changed without restarting any service.
- [System Requirements](faqs/system-requirements.md) — NodeAva requires a dedicated GPU on every supported platform; there is no CPU-only mode.

## Sources

(empty — populated at runtime via /v1/ingest)
