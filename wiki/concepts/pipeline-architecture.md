# The NodeAva Pipeline

The NodeAva pipeline is the end-to-end chain of services that converts a user's spoken words into an animated avatar response, running entirely on the user's local machine without any cloud API calls. Audio captured in the browser travels through speech recognition, language model inference, and speech synthesis before returning as lip-synced audio on the Three.js avatar — all coordinated by a browser-side orchestrator that manages state, streaming, and error recovery.

## Services and Ports

The pipeline consists of five Docker services (or native processes on macOS) sitting behind an nginx reverse proxy, exposed on the following ports:

| Service | Technology | External Port | Nginx Path |
|---|---|---|---|
| Frontend / nginx | Vite + Three.js | 3000 | — |
| STT | whisper.cpp (base.en) | 8080 | /api/stt/ |
| LLM | llama.cpp (Qwen3-4B) | 8081 | /api/llm/ |
| TTS | Kokoro-FastAPI (Kokoro-82M) | 8880 | /api/tts/ |
| Orchestrator | nodeava-orch | 8082 | internal |

The orchestrator service at port 8082 handles tool calls such as wiki lookups and web search. It is not exposed to the browser directly; the frontend LLM client communicates with llama.cpp at port 8081, and the orchestrator sits between llama.cpp and downstream tools like SearXNG and the wiki directory mounted at `/app/wiki`.

## Data Flow

1. The browser's [[speech-to-text]] subsystem runs Silero VAD to detect speech boundaries, then POSTs the audio segment to whisper.cpp at port 8080, which returns a transcript.
2. The transcript is handed to `Orchestrator.js` (`frontend/src/pipeline/Orchestrator.js`), which adds it to the conversation history and sends the full message list to llama.cpp at port 8081 via an OpenAI-compatible streaming endpoint.
3. The [[llm]] response streams back as server-sent events. The Orchestrator buffers the first seven characters to detect whether the model has emitted a `<think>` tag. If it has, all tokens inside `<think>...</think>` are filtered out and never sent to [[text-to-speech]] or stored in history. Emotion tags such as `[happy]` are parsed from the beginning of the visible response and forwarded to the [[avatar]].
4. Visible tokens accumulate in a buffer. Each time a sentence boundary is detected (a period, exclamation mark, or question mark following a word character), that sentence is cleaned of markdown and emoji and enqueued to Kokoro-FastAPI at port 8880, which returns raw PCM audio plus word timestamps.
5. The PCM audio and timestamps drive lip sync on the Three.js avatar via TalkingHead. The avatar speaks each sentence as it arrives, so speech begins before the LLM has finished generating.

## State Machine

The Orchestrator tracks seven states defined in `frontend/src/app/state.js`: IDLE, LISTENING, TRANSCRIBING, THINKING, TOOL_CALLING, WIKI_QUERY, and SPEAKING. State transitions are strict — for example, a new user utterance detected during SPEAKING triggers an interrupt that aborts the LLM stream, clears the TTS queue, and stops the avatar mid-sentence before the pipeline restarts from LISTENING.

## Tool Calls and Filler Audio

When the LLM invokes a tool, the Orchestrator transitions to TOOL_CALLING or WIKI_QUERY and arms an 800-millisecond timer. If the tool round takes longer than 800ms, the [[text-to-speech]] system prepends a filler phrase ("Let me look that up." or "Let me check the wiki.") to the audio queue so the avatar does not fall silent. Only one filler phrase plays per user turn regardless of how many tool rounds occur.

## macOS Native Mode

On Apple Silicon, all five services run as native processes rather than Docker containers, using the same port assignments. `llama-server` and `whisper-server` are installed via Homebrew with Metal GPU acceleration. Kokoro-FastAPI runs via `uv` from `~/.nodeava/kokoro-fastapi/` with `DEVICE_TYPE=mps`. See [[macos-setup]] for the startup scripts.
