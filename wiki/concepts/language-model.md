# The Language Model

The language model is the component responsible for generating NodeAva's responses. It receives a conversation history, reasons about a reply, and streams text back to the frontend. NodeAva runs Qwen3-4B locally via llama.cpp, served on port 8081, so no conversation data leaves the user's machine.

## Model and Runtime

The model is Qwen3-4B, a four-billion-parameter instruction-tuned model with built-in chain-of-thought reasoning. It runs inside llama.cpp, which exposes an OpenAI-compatible HTTP API at `http://localhost:8081`. On NVIDIA hardware, llama.cpp uses CUDA; on AMD hardware, it uses Vulkan. On Apple Silicon Macs, it runs natively via `llama-server` installed through Homebrew, with Metal GPU acceleration enabled automatically.

## Thinking Mode

Qwen3-4B is a thinking model. When it generates a response, it first produces an internal reasoning block wrapped in `<think>` tags before emitting the visible reply. The llama.cpp server is started with `--jinja --reasoning-format none` and `--temp 0.6`. Temperature must not be set to zero with thinking models, as that degrades output quality. The [[orchestrator]] buffers the first seven characters of each streamed response to detect the `<think>` opening tag. Thinking content is stripped before anything reaches the display or the conversation history. Emotion tags such as `[happy]` and `[neutral]` appear after the thinking block and are parsed separately to drive the [[avatar]].

## Where It Sits in the Pipeline

The frontend sends requests through the orchestrator service at port 8082, not directly to llama.cpp. The orchestrator at `services/orchestrator/` acts as an OpenAI-compatible proxy and is where the agentic tool loop lives. It forwards messages to llama.cpp via `LocalLlamaProvider`, defined in `services/orchestrator/orchestrator/providers/local.py`. Streaming responses arrive as server-sent events and are consumed by `frontend/src/llm/LLMClient.js`. The [[orchestrator]] can also route requests to cloud providers such as Anthropic or OpenAI when a `provider` field and `X-Provider-Key` header are supplied, leaving the local model as the default.

## Configuration

The system prompt and endpoint address are defined in `frontend/src/app/config.js`. The LLM endpoint is proxied through nginx at `/api/llm/` in Docker deployments, and through the Vite dev server proxy during local development. The orchestrator reads `LLAMA_URL` from its environment, defaulting to `http://localhost:8081`.

## Verifying the Model is Loaded

```bash
curl http://localhost:8081/v1/models
```

A successful response lists the loaded model. If the endpoint is unreachable, check that the `llm` Docker service is running or that `llama-server` is active on macOS.

## Related Pages

- [[orchestrator]] — the proxy layer between the frontend and llama.cpp
- [[speech-to-text]] — produces the transcribed user input that becomes a message
- [[text-to-speech]] — consumes the model's visible output to produce audio
- [[avatar]] — uses emotion tags from the model output to animate the face
