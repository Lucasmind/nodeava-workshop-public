# What is NodeAva?

NodeAva is a self-contained digital avatar that runs entirely on a single machine, combining speech recognition, language model reasoning, voice synthesis, and 3D facial animation into a real-time conversational pipeline with no cloud dependencies and no data leaving the user's hardware.

## Core Components

The system is built from four AI models, each serving a distinct role:

- **Qwen3-4B** (quantized to Q4_K_M, ~2.5 GB) handles conversation and reasoning via llama.cpp, exposed on port 8081.
- **Kokoro-82M** handles text-to-speech via Kokoro-FastAPI, returning PCM audio with word-level timestamps on port 8880.
- **Whisper base.en** (~142 MB) handles speech-to-text via whisper.cpp on port 8080.
- **TalkingHead** drives the 3D avatar in the browser, using the word timestamps from Kokoro to synchronize lip movements and facial expressions.

## How the Pipeline Works

The browser is the orchestrator. When a user speaks, Silero VAD (running in-browser via `vad-web`) detects voice activity and triggers transcription through Whisper. The resulting text is sent to the LLM, which streams tokens back. The [[orchestrator]] (`frontend/src/pipeline/Orchestrator.js`) filters out internal reasoning wrapped in `<think>` tags, splits the visible response at sentence boundaries, and dispatches each sentence to the TTS queue immediately — so audio begins playing before the LLM has finished generating. The avatar animates in sync with the audio using the timestamp data from Kokoro.

## Deployment

On Linux and Windows, the four services run as Docker containers behind nginx, which routes `/api/stt/`, `/api/tts/`, and `/api/llm/` to the appropriate backend. On macOS with Apple Silicon, the same services run as native processes using Metal and MPS acceleration, because Docker Desktop on macOS cannot pass through GPU access to its Linux VM. In both cases the frontend is served on port 3000 and the backend port assignments are identical.

## What Makes It Distinct

Every component runs locally. The LLM uses a thinking mode that produces internal reasoning before generating a visible response, improving answer quality without exposing that reasoning to the user. The browser orchestrates the full pipeline without a backend coordinator, keeping latency low and the architecture simple.

Related pages: [[orchestrator]], [[text-to-speech]], [[speech-to-text]], [[language-model]], [[avatar]]
