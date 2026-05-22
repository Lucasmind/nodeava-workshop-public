# Text-to-Speech (TTS)

Text-to-speech is the stage in NodeAva's pipeline that converts the LLM's text output into audio that the avatar can speak. NodeAva uses Kokoro-82M, a lightweight neural TTS model, served by the Kokoro-FastAPI container on port 8880. The frontend communicates with this service through nginx at the `/api/tts/` path, keeping all audio synthesis local with no cloud dependency.

## Role in the Pipeline

The [[orchestrator]] splits the LLM's streaming output into sentences and feeds each sentence to `TTSManager` (located at `frontend/src/tts/TTSManager.js`). `TTSManager` maintains an internal queue and processes one sentence at a time, sending each to the Kokoro-FastAPI endpoint as a POST request. When audio is ready, it fires an `onAudioReady` callback that passes the result to [[avatar]] for lip-synced playback.

## Request Format

Each synthesis request sends a JSON body specifying the model (`kokoro`), the input text, the selected voice, playback speed, and two important flags: `response_format: "pcm"` and `return_timestamps: true`. The PCM format delivers raw audio that TalkingHead can process directly. The timestamp data maps each word to a start time and duration in seconds, which `TTSManager` converts to milliseconds and passes to TalkingHead for lip synchronization.

## Audio Data Transform

The Kokoro-FastAPI response returns base64-encoded PCM audio alongside word-level timestamps. `TTSManager._transformResponse()` decodes the base64 string into an `ArrayBuffer` and restructures the timestamp data into three parallel arrays — `words`, `wtimes`, and `wdurations` — matching the format that TalkingHead expects. TalkingHead then concatenates and converts the PCM data during playback.

## Filler Audio

When an agentic tool call takes longer than the filler-grace window (800ms), the [[orchestrator]] calls `TTSManager.synthesizeFiller()` with a short phrase such as "let me look that up." This method prepends the phrase to the front of the queue rather than appending it, so it plays as soon as the current sentence finishes. If the same filler text is already queued, the call is silently ignored to prevent repetition during rapid successive tool calls.

## Voice and Speed

The active voice and speed are set via `config.ttsDefaultVoice` and `config.ttsDefaultSpeed` in `frontend/src/app/config.js`. Both can be changed at runtime through `TTSManager.setVoice()` and `TTSManager.setSpeed()`. On NVIDIA hardware, the Kokoro container runs with CUDA acceleration. On AMD hardware, it uses ROCm via a custom image built from `docker/kokoro-rocm/Dockerfile`. On Apple Silicon, Kokoro-FastAPI runs natively via `uv` with `DEVICE_TYPE=mps`, cloned to `~/.nodeava/kokoro-fastapi/`.

## Error Handling

If the Kokoro service is unreachable or returns an error, `TTSManager` fires `onAudioReady(null)`, which signals the [[avatar]] that the sentence failed and allows the queue to continue processing. A 503 response is classified as the service being busy; 5xx responses indicate a server-side fault; network errors indicate the container is not running.

## Related Pages

- [[orchestrator]] — controls sentence splitting and feeds text to TTS
- [[avatar]] — receives audio data and word timestamps for lip sync
- [[speech-to-text]] — the input side of the voice pipeline
