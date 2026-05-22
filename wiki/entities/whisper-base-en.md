# Whisper base.en (STT Model)

Whisper base.en is OpenAI's English-only speech recognition model at the base parameter scale, and it serves as NodeAva's speech-to-text engine, converting the user's microphone audio into text that the pipeline passes to the LLM.

## Role in NodeAva

The STT service runs as a Docker container built from `./stt-service/Dockerfile`. It exposes an OpenAI-compatible transcription endpoint at port 8080, reachable internally via nginx at `/api/stt/` and directly on the host at `localhost:8080`. The frontend's [[stt-manager]] sends audio blobs to `POST /v1/audio/transcriptions` with the field `model=base.en`. The service returns a transcript string, which the [[orchestrator]] forwards to the [[llm]] as the user's message.

On macOS, the equivalent is `whisper-server` installed via Homebrew with Metal GPU acceleration enabled automatically. The port and API surface are identical to the Docker setup.

## Key Facts

| Property | Value |
|----------|-------|
| Model variant | base.en (English-only) |
| Inference backend | whisper.cpp with Vulkan GPU acceleration |
| Internal port | 8080 |
| External port | 8080 |
| Docker image | Built locally from `./stt-service/Dockerfile` |
| Model file location | `./models/` (mounted read-only at `/models`) |
| Environment variable | `WHISPER_MODEL=base.en` |

## Why base.en

The base.en variant is chosen for latency. It is fast enough to return a transcript within the conversational turn budget on consumer hardware, and the English-only restriction removes the language-detection overhead present in multilingual Whisper variants. Accuracy is sufficient for clear microphone input in a workshop setting.

## Testing the Endpoint

```bash
curl -X POST http://localhost:8080/v1/audio/transcriptions \
  -F "file=@test.wav" \
  -F "model=base.en"
```

A healthy service returns JSON with a `text` field containing the transcript.

## Related Pages

- [[stt-manager]] — the frontend module that handles VAD gating and sends audio to this service
- [[vad-web]] — Silero VAD running in the browser that decides when to trigger transcription
- [[pipeline-overview]] — how the transcript moves from STT into the LLM and TTS stages

## Upstream

The inference server is whisper.cpp, maintained at `https://github.com/ggerganov/whisper.cpp`. The model weights originate from OpenAI's Whisper release.
