# Kokoro-82M (TTS Engine)

Kokoro-82M is a lightweight, open-weight text-to-speech model with 82 million parameters that NodeAva uses to synthesize all spoken audio output. It runs entirely on the user's machine with no cloud dependency, producing natural-sounding speech with low latency suitable for real-time conversational use.

## Role in NodeAva

Kokoro-82M is the TTS layer of the four-service pipeline. After the [[llm]] generates a response and the [[orchestrator]] splits it into sentences, each sentence is sent to Kokoro-82M for synthesis. The model returns raw PCM audio along with word-level timestamps, which [[text-to-speech]] uses to drive lip sync on the [[avatar]].

## Deployment

NodeAva runs Kokoro-82M through the Kokoro-FastAPI server, not the model directly. The Docker image is `ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4`. The service listens internally on port 8880 and is exposed to the host on the same port. Nginx routes browser requests from `/api/tts/` to this service.

On NVIDIA hardware, the service uses CUDA. On AMD hardware, a custom ROCm image is built from `docker/kokoro-rocm/Dockerfile` — the first build takes 20 to 30 minutes and produces an image around 22 GB. On Apple Silicon, Kokoro-FastAPI is cloned to `~/.nodeava/kokoro-fastapi/` and run natively via `uv` with `DEVICE_TYPE=mps` for PyTorch MPS acceleration, because Docker Desktop on macOS cannot pass through Metal GPU access.

## Key Facts

| Property | Value |
|----------|-------|
| Model parameters | 82 million |
| Serving layer | Kokoro-FastAPI v0.2.4 |
| Internal port | 8880 |
| External port | 8880 |
| GPU backends | CUDA (NVIDIA), ROCm (AMD), MPS (Apple Silicon) |
| Audio output | Raw PCM with word timestamps |
| Default voice | `af_bella` |

## API Usage

The [[tts-manager]] calls the `/dev/captioned_speech` endpoint with `return_timestamps: true`. A minimal test request:

```bash
curl -X POST http://localhost:8880/dev/captioned_speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"kokoro","input":"Hello","voice":"af_bella","response_format":"pcm","stream":false,"return_timestamps":true}'
```

Health can be checked at `http://localhost:8880/v1/models`, which is also the Docker healthcheck target.

## Relevant Files

- `frontend/src/tts/TTSManager.js` — client that calls Kokoro-FastAPI, decodes PCM, and maps word timestamps to avatar lip sync frames
- `docker-compose.yml` — base service definition for the `tts` container
- `docker-compose.gpu-nvidia.yml` — CUDA overrides
- `docker-compose.gpu-amd.yml` — ROCm overrides
- `docker/kokoro-rocm/Dockerfile` — AMD-specific image build

## Upstream

The Kokoro-FastAPI project is maintained by Remsky at `https://github.com/remsky/kokoro-fastapi`. The underlying Kokoro model weights are distributed separately under their own license terms.
